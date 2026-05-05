import io
import httpx
import fitz
from bs4 import BeautifulSoup
import logging
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Upgrade-Insecure-Requests": "1"
}

MAX_PDF_SIZE_MB = 150

@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3), retry=retry_if_exception_type(httpx.HTTPStatusError))
async def _fetch_url_with_retry(url: str) -> httpx.Response:
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
        response = await client.get(url, headers=BROWSER_HEADERS)
        response.raise_for_status()
        return response


import hashlib

_DOCUMENT_CACHE = {}

async def _fetch_and_cache(url: str) -> tuple[bytes, str]:
    url_hash = hashlib.md5(url.encode()).hexdigest()
    if url_hash in _DOCUMENT_CACHE:
        return _DOCUMENT_CACHE[url_hash]
    
    response = await _fetch_url_with_retry(url)
    content_size_mb = len(response.content) / (1024 * 1024)
    if content_size_mb > MAX_PDF_SIZE_MB:
         raise ValueError(f"Document is too large ({content_size_mb:.1f}MB). Maximum allowed is {MAX_PDF_SIZE_MB}MB to prevent memory exhaustion.")
         
    content_type = response.headers.get("content-type", "").lower()
    
    _DOCUMENT_CACHE[url_hash] = (response.content, content_type)
    
    # Keep cache small (max 3 books)
    if len(_DOCUMENT_CACHE) > 3:
        first_key = next(iter(_DOCUMENT_CACHE))
        del _DOCUMENT_CACHE[first_key]
        
    return response.content, content_type

async def extract_text_from_pdf_url(url: str, max_chars: int = 50000, start_page: int = None, end_page: int = None) -> str:
    """Legacy wrapper for backward compatibility."""
    return await smart_extract_document(url, action="pages", start_page=start_page, end_page=end_page, max_chars=max_chars)

async def smart_extract_document(url: str, action: str = "pages", keyword: str = None, start_page: int = None, end_page: int = None, max_chars: int = 50000) -> str:
    """
    Smart extraction with caching.
    action="toc": Returns table of contents.
    action="search": Returns only pages matching 'keyword'.
    action="pages": Returns text from 'start_page' to 'end_page'.
    """
    try:
        content, content_type = await _fetch_and_cache(url)
    except Exception as e:
        logger.error(f"Failed to download/cache from {url}: {e}")
        return f"Error downloading document: {str(e)}"

    filetype = None
    is_pdf_or_epub = False
    
    # Detect via magic bytes first (most reliable for direct downloads)
    if content.startswith(b"%PDF"):
        is_pdf_or_epub = True
        filetype = "pdf"
    elif content.startswith(b"PK"):  # EPUB is a ZIP archive
        is_pdf_or_epub = True
        filetype = "epub"
    else:
        is_pdf_or_epub = "pdf" in content_type or "epub" in content_type or url.lower().endswith(".pdf") or url.lower().endswith(".epub")
        filetype = "epub" if "epub" in content_type or url.lower().endswith(".epub") else "pdf"
    
    if is_pdf_or_epub:
        try:
            with fitz.open(stream=content, filetype=filetype) as doc:
                total_pages = len(doc)
                
                if action == "toc":
                    toc = doc.get_toc()
                    if toc:
                        out = [f"Table of Contents (Total Pages: {total_pages}):"]
                        for lvl, title, page in toc:
                            indent = "  " * (lvl - 1)
                            out.append(f"{indent}- {title} (Page {page})")
                        return "\n".join(out)
                    else:
                        # Fallback: extract first 15 pages which usually contain TOC
                        action = "pages"
                        start_page = 1
                        end_page = min(15, total_pages)
                        
                if action == "search":
                    if not keyword:
                        return "Error: Keyword required for search action."
                    text_blocks = []
                    found_pages = 0
                    for i in range(total_pages):
                        page = doc.load_page(i)
                        rects = page.search_for(keyword)
                        if rects:
                            found_pages += 1
                            text_blocks.append(f"--- Page {i+1} (Match) ---\n" + page.get_text("text", sort=True))
                            if found_pages >= 20: # Limit matched pages to prevent overflow
                                text_blocks.append(f"\n[...Stopped searching after 20 matching pages]")
                                break
                    if not text_blocks:
                        return f"Keyword '{keyword}' not found in document."
                    full_text = f"Found '{keyword}' on {found_pages} pages:\n\n" + "\n\n".join(text_blocks)
                    if len(full_text) > max_chars:
                        return full_text[:max_chars] + f"\n\n[...truncated]"
                    return full_text
                    
                if action == "pages":
                    pg_start = max(0, (start_page or 1) - 1)
                    pg_end = min(total_pages, end_page or total_pages)

                    text_blocks = []
                    for i in range(pg_start, pg_end):
                        page = doc.load_page(i)
                        text_blocks.append(f"--- Page {i+1} ---\n" + page.get_text("text", sort=True))
                    full_text = "\n\n".join(text_blocks)

                    header = f"[Extracted pages {pg_start+1}-{pg_end} of {total_pages}]\n\n"
                    if len(full_text) > max_chars:
                        return header + full_text[:max_chars] + f"\n\n[...truncated, {len(full_text) - max_chars} characters omitted]"
                    return header + full_text
                    
        except Exception as e:
            logger.error(f"PyMuPDF failed to extract text from {url}: {e}")
            return f"Error extracting document via PyMuPDF: {str(e)}"

    elif "html" in content_type or "text" in content_type:
        soup = BeautifulSoup(content, "html.parser")
        for script_or_style in soup(["script", "style", "nav", "footer", "header"]):
            script_or_style.decompose()

        text = soup.get_text(separator='\n')
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)

        if len(text) > max_chars:
            return text[:max_chars] + f"\n\n[...truncated, {len(text) - max_chars} characters omitted]"
        return text

    else:
        return f"Unsupported content type for text extraction: {content_type}"


async def render_pdf_to_images_from_url(url: str, max_pages: int = 3) -> list:
    """
    Downloads a PDF and renders its first `max_pages` as raw PNG bytes.
    Useful for feeding into Vision Models.
    Safely manages PyMuPDF contexts and enforces size limits.
    """
    try:
        response = await _fetch_url_with_retry(url)
    except Exception as e:
        logger.error(f"Failed to download PDF for vision rendering from {url}: {e}")
        raise ValueError(f"Failed to download source document: {str(e)}")

    content_size_mb = len(response.content) / (1024 * 1024)
    if content_size_mb > MAX_PDF_SIZE_MB:
        raise ValueError(f"PDF is too large ({content_size_mb:.1f}MB). Maximum allowed: {MAX_PDF_SIZE_MB}MB to protect memory.")

    content_type = response.headers.get("content-type", "").lower()
    if "pdf" not in content_type and not url.endswith(".pdf"):
        raise ValueError(f"URL does not point to a valid PDF. Content-type was {content_type}")

    results = []
    
    try:
        with fitz.open(stream=response.content, filetype="pdf") as doc:
            num_pages = min(len(doc), max_pages)
            for i in range(num_pages):
                page = doc.load_page(i)
                mat = fitz.Matrix(1.5, 1.5)
                pix = page.get_pixmap(matrix=mat)
                png_bytes = pix.tobytes("png")
                results.append({
                    "page": i + 1,
                    "data": png_bytes
                })
    except Exception as e:
        logger.error(f"PyMuPDF rendering failed for {url}: {e}")
        raise ValueError(f"Failed to render PDF frames: {str(e)}")

    return results
