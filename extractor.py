import io
import httpx
from pypdf import PdfReader
from bs4 import BeautifulSoup

async def extract_text_from_pdf_url(url: str) -> str:
    """
    Downloads a PDF from a URL into memory and extracts text.
    Fallback to HTML text extraction if it isn't a PDF.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "").lower()
    
    if "pdf" in content_type or url.endswith(".pdf"):
        # Process as PDF
        pdf_file = io.BytesIO(response.content)
        try:
            reader = PdfReader(pdf_file)
            text_blocks = []
            for i, page in enumerate(reader.pages):
                text_blocks.append(f"--- Page {i+1} ---\n" + page.extract_text())
            full_text = "\n\n".join(text_blocks)
            return full_text
        except Exception as e:
            return f"Error extracting PDF: {str(e)}"
    
    elif "html" in content_type:
        # Process as HTML
        soup = BeautifulSoup(response.text, "html.parser")
        # Remove script and style elements
        for script_or_style in soup(["script", "style", "nav", "footer", "header"]):
            script_or_style.decompose()
        
        text = soup.get_text(separator='\n')
        # clean up empty lines
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text
    
    else:
        return f"Unsupported content type for text extraction: {content_type}"


async def render_pdf_to_images_from_url(url: str, max_pages: int = 3) -> list:
    """
    Downloads a PDF and renders its first `max_pages` as raw PNG bytes.
    Useful for feeding into Vision Models.
    Raises an error if not a PDF.
    """
    import fitz # PyMuPDF
    import io
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        
    content_type = response.headers.get("content-type", "").lower()
    if "pdf" not in content_type and not url.endswith(".pdf"):
        raise ValueError(f"URL does not point to a valid PDF. Content-type was {content_type}")
        
    doc = fitz.open(stream=response.content, filetype="pdf")
    results = []
    
    num_pages = min(len(doc), max_pages)
    for i in range(num_pages):
        page = doc.load_page(i)
        # Render page to an image (Scale by 1.5x for readability)
        mat = fitz.Matrix(1.5, 1.5)
        pix = page.get_pixmap(matrix=mat)
        png_bytes = pix.tobytes("png")
        results.append({
            "page": i + 1,
            "data": png_bytes
        })
        
    return results
