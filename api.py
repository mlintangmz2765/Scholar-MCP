import os
import httpx
import asyncio
from typing import Dict, Any, List, Optional, Union
import logging
from dotenv import load_dotenv
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception, retry_if_exception_type

from models import PaperMetadata, AuthorProfile, TopicItem, CitationResponse, AuthorWork

load_dotenv()

logger = logging.getLogger(__name__)

SCOPUS_API_KEY = os.getenv("SCOPUS_API_KEY")
SCOPUS_INST_TOKEN = os.getenv("SCOPUS_INST_TOKEN")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "developer@example.com")

HTTP_TIMEOUT = 30.0

def _should_retry_exception(exception: Exception) -> bool:
    """Helper to determine if an exception is retryable (429, 502, 503, 504 or network errors)."""
    if isinstance(exception, httpx.HTTPStatusError):
        return exception.response.status_code in (429, 500, 502, 503, 504)
    if isinstance(exception, (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout)):
        return True
    return False

api_retry = retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception(_should_retry_exception),
    reraise=True
)

@api_retry
async def _robust_fetch(url: str, headers: dict = None, params: dict = None, method: str = "GET") -> httpx.Response:
    """Universal robust HTTP fetcher with baked-in smart retries."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        response = await client.request(method, url, headers=headers, params=params)
        response.raise_for_status()
        return response

def _normalize_doi(doi: str) -> str:
    """Strips common DOI URL prefixes to extract the raw DOI."""
    if not doi:
        return ""
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"):
        if doi.startswith(prefix):
            return doi[len(prefix):]
    return doi


async def search_papers_scopus(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search papers using Scopus API. Returns a list of brief paper metadata."""
    if not SCOPUS_API_KEY:
        raise ValueError("SCOPUS_API_KEY is not set.")

    limit = min(limit, 25)
    url = "https://api.elsevier.com/content/search/scopus"
    headers = {
        "X-ELS-APIKey": SCOPUS_API_KEY,
        "Accept": "application/json"
    }
    if SCOPUS_INST_TOKEN:
        headers["X-ELS-Insttoken"] = SCOPUS_INST_TOKEN

    params = {
        "query": query,
        "count": limit,
        "view": "STANDARD"
    }

    try:
        response = await _robust_fetch(url, headers=headers, params=params)
        data = response.json()
    except Exception as e:
        logger.error(f"Scopus search failed: {e}")
        return []

    results = []
    entries = data.get("search-results", {}).get("entry", [])
    for entry in entries:
        results.append({
            "id": entry.get("dc:identifier", ""),
            "title": entry.get("dc:title", ""),
            "authors": entry.get("dc:creator", "Unknown"),
            "publication_name": entry.get("prism:publicationName", ""),
            "date": entry.get("prism:coverDate", ""),
            "doi": entry.get("prism:doi", ""),
            "url": entry.get("prism:url", ""),
            "abstract_available": "dc:description" in entry,
            "abstract_snippet": entry.get("dc:description", "Abstract snippet not available in standard search. Use get_paper_details for full abstract.")
        })
    return results


async def get_paper_details_scopus(scopus_id_or_doi: str) -> Dict[str, Any]:
    """Get full paper details including abstract from Scopus API."""
    if not SCOPUS_API_KEY:
        raise ValueError("SCOPUS_API_KEY is not set.")

    headers = {
        "X-ELS-APIKey": SCOPUS_API_KEY,
        "Accept": "application/json"
    }
    if SCOPUS_INST_TOKEN:
        headers["X-ELS-Insttoken"] = SCOPUS_INST_TOKEN

    if "SCOPUS_ID:" in scopus_id_or_doi:
        identifier = scopus_id_or_doi.split(":")[-1]
        url = f"https://api.elsevier.com/content/abstract/scopus_id/{identifier}"
    elif scopus_id_or_doi.startswith("10."):
        url = f"https://api.elsevier.com/content/abstract/doi/{scopus_id_or_doi}"
    else:
        identifier = scopus_id_or_doi.replace("SCOPUS_ID:", "").replace("scopus_id:", "")
        url = f"https://api.elsevier.com/content/abstract/scopus_id/{identifier}"

    params = {"view": "META_ABS", "httpAccept": "application/json"}

    try:
        response = await _robust_fetch(url, headers=headers, params=params)
        data = response.json()
    except httpx.HTTPStatusError as e:
        logger.warning(f"Scopus HTTP error: {e.response.status_code}")
        return {"error": f"Failed to retrieve data. Status code: {e.response.status_code}", "raw": e.response.text}
    except Exception as e:
        logger.error(f"Scopus request failed: {e}")
        return {"error": f"Request failed: {str(e)}"}

    abstract_retrieval = data.get("abstracts-retrieval-response", {})
    coredata = abstract_retrieval.get("coredata", {})

    title = coredata.get("dc:title", "")
    abstract = coredata.get("dc:description", "Abstract not available.")
    doi = coredata.get("prism:doi", "")
    open_access = coredata.get("openaccessFlag", False)
    links = coredata.get("link", [])
    pdf_link = None
    for link in links:
        if isinstance(link, dict) and link.get("@ref") == "full-text":
            pdf_link = link.get("@href")

    return {
        "id": coredata.get("dc:identifier", ""),
        "title": title,
        "abstract": abstract.strip() if isinstance(abstract, str) else str(abstract),
        "publicationName": coredata.get("prism:publicationName", ""),
        "volume": coredata.get("prism:volume", ""),
        "issue": coredata.get("prism:issueIdentifier", ""),
        "pages": coredata.get("prism:pageRange", ""),
        "date": coredata.get("prism:coverDate", ""),
        "doi": doi,
        "openAccess": open_access,
        "pdf_link_hint": pdf_link,
        "authors": [a.get("ce:indexed-name") for a in abstract_retrieval.get("authors", {}).get("author", [])]
    }


async def search_papers_openalex(query: str, limit: int = 5, sort_by: str = "relevance") -> List[Dict[str, Any]]:
    """
    Search using OpenAlex, deeply integrated with Open Access PDFs.
    sort_by: 'relevance' (default), 'cited_by_count', 'publication_year'.
    """
    limit = min(limit, 100)
    url = "https://api.openalex.org/works"
    params: Dict[str, Any] = {
        "search": query,
        "per-page": limit,
        "mailto": CONTACT_EMAIL
    }
    if sort_by == "cited_by_count":
        params["sort"] = "cited_by_count:desc"
    elif sort_by == "publication_year":
        params["sort"] = "publication_year:desc"

    try:
        response = await _robust_fetch(url, params=params)
        data = response.json()
    except Exception as e:
        logger.error(f"OpenAlex search failed: {e}")
        return []

    results = []
    for work in data.get("results", []):
        oa_info = work.get("open_access", {})
        oa_url = oa_info.get("oa_url")

        abstract = "Abstract not available/not parsed here."
        inv_abstract = work.get("abstract_inverted_index")
        if inv_abstract:
            try:
                max_index = max(max(pos) for pos in inv_abstract.values())
                words = [""] * (max_index + 1)
                for word, indices in inv_abstract.items():
                    for idx in indices:
                        if 0 <= idx <= max_index:
                            words[idx] = word
                abstract = " ".join(words)
            except (ValueError, TypeError):
                abstract = "Abstract could not be reconstructed."

        results.append({
            "id": work.get("id"),
            "title": work.get("title", ""),
            "authors": [a.get("author", {}).get("display_name") for a in work.get("authorships", [])],
            "year": work.get("publication_year", ""),
            "volume": work.get("biblio", {}).get("volume", ""),
            "issue": work.get("biblio", {}).get("issue", ""),
            "pages": f"{work.get('biblio', {}).get('first_page', '')}-{work.get('biblio', {}).get('last_page', '')}".strip("-"),
            "doi": work.get("doi", ""),
            "open_access_pdf": oa_url,
            "abstract_snippet": abstract[:500] + "..." if len(abstract) > 500 else abstract
        })

    return results


async def get_paper_details_openalex(openalex_id_or_doi: str) -> Dict[str, Any]:
    """Get full paper details from OpenAlex. Accepts OpenAlex IDs (Wxxxx) or DOIs."""
    if openalex_id_or_doi.startswith("10.") or openalex_id_or_doi.startswith("https://doi.org/"):
        doi = _normalize_doi(openalex_id_or_doi)
        url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    elif openalex_id_or_doi.startswith("W") or openalex_id_or_doi.startswith("https://openalex.org/"):
        wid = openalex_id_or_doi.split("/")[-1]
        url = f"https://api.openalex.org/works/{wid}"
    else:
        return {"error": f"Unrecognized identifier format: {openalex_id_or_doi}"}

    try:
        res = await _robust_fetch(url, params={"mailto": CONTACT_EMAIL})
        work = res.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"OpenAlex returned {e.response.status_code}"}
    except Exception as e:
        return {"error": f"General OpenAlex error: {str(e)}"}

    abstract = "Abstract not available."
    inv_abstract = work.get("abstract_inverted_index")
    if inv_abstract:
        try:
            max_index = max(max(pos) for pos in inv_abstract.values())
            words = [""] * (max_index + 1)
            for word, indices in inv_abstract.items():
                for idx in indices:
                    if 0 <= idx <= max_index:
                        words[idx] = word
            abstract = " ".join(words)
        except (ValueError, TypeError):
            pass

    oa = work.get("open_access", {})
    return {
        "id": work.get("id", ""),
        "title": work.get("title", ""),
        "abstract": abstract,
        "year": work.get("publication_year", ""),
        "doi": work.get("doi", ""),
        "openAccess": oa.get("is_oa", False),
        "open_access_pdf": oa.get("oa_url"),
        "authors": [a.get("author", {}).get("display_name") for a in work.get("authorships", [])],
        "cited_by_count": work.get("cited_by_count", 0),
    }


async def get_unpaywall_pdf_link(doi: str) -> Dict[str, Any]:
    """Query Unpaywall API to find Open Access information."""
    doi = _normalize_doi(doi)
    if not doi:
        return {"error": "No DOI provided"}

    url = f"https://api.unpaywall.org/v2/{doi}"
    params = {"email": CONTACT_EMAIL}

    try:
        response = await _robust_fetch(url, params=params)
        data = response.json()
        return {
            "is_oa": data.get("is_oa", False),
            "best_oa_location": data.get("best_oa_location"),
            "oa_locations": data.get("oa_locations", []),
            "title": data.get("title")
        }
    except httpx.HTTPStatusError as e:
        return {"error": f"Unpaywall returned HTTP {e.response.status_code} for DOI: {doi}"}
    except Exception as e:
        return {"error": f"Error contacting Unpaywall: {str(e)}"}


async def autocomplete_authors_openalex(name: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Rapidly search api.openalex.org/autocomplete/authors."""
    url = "https://api.openalex.org/autocomplete/authors"
    params = {"q": name, "mailto": CONTACT_EMAIL}

    try:
        res = await _robust_fetch(url, params=params)
        data = res.json()
    except Exception as e:
        logger.error(f"Author autocomplete failed: {e}")
        return []

    results = []
    for item in data.get("results", [])[:limit]:
        results.append({
            "id": item.get("id"),
            "display_name": item.get("display_name"),
            "hint": item.get("hint", "No institution"),
            "works_count": item.get("works_count", 0),
            "cited_by_count": item.get("cited_by_count", 0)
        })
    return results


async def search_authors_openalex(name: str, institution: str = None, limit: int = 5) -> List[Dict[str, Any]]:
    """Deep profile search for authors via OpenAlex. Optionally filter by institution name."""
    url = "https://api.openalex.org/authors"
    params: Dict[str, Any] = {"search": name, "mailto": CONTACT_EMAIL, "per-page": limit}

    if institution:
        try:
            inst_res = await _robust_fetch(
                "https://api.openalex.org/institutions", 
                params={"search": institution, "per-page": 1, "mailto": CONTACT_EMAIL}
            )
            inst_data = inst_res.json()
            inst_results = inst_data.get("results", [])
            if inst_results:
                inst_id = inst_results[0].get("id", "").split("/")[-1]
                params["filter"] = f"last_known_institutions.id:{inst_id}"
        except Exception as e:
            logger.warning(f"Institution filter lookup failed, proceeding without it: {e}")

    try:
        res = await _robust_fetch(url, params=params)
        data = res.json()
    except Exception as e:
        logger.error(f"Author search failed: {e}")
        return []

    results = []
    for author in data.get("results", []):
        affil = author.get("last_known_institutions", [{}])
        last_inst = affil[0].get("display_name", "Unknown") if isinstance(affil, list) and affil else "Unknown"
        results.append({
            "id": author.get("id"),
            "display_name": author.get("display_name"),
            "orcid": author.get("orcid"),
            "works_count": author.get("works_count"),
            "cited_by_count": author.get("cited_by_count"),
            "h_index": author.get("summary_stats", {}).get("h_index"),
            "i10_index": author.get("summary_stats", {}).get("i10_index"),
            "last_institution": last_inst,
            "x_concepts": [c.get("display_name") for c in author.get("x_concepts", [])[:3]]
        })
    return results


async def retrieve_author_works_openalex(author_id: str, limit: int = 15) -> List[Dict[str, Any]]:
    """Retrieves chronologically sorted works by an author."""
    if author_id.startswith("http"):
        author_id = author_id.split("/")[-1]

    limit = min(limit, 100)
    url = "https://api.openalex.org/works"
    params = {
        "filter": f"author.id:{author_id}",
        "sort": "publication_year:desc,cited_by_count:desc",
        "per-page": limit,
        "mailto": CONTACT_EMAIL
    }

    try:
        res = await _robust_fetch(url, params=params)
        data = res.json()
    except Exception as e:
        logger.error(f"Retrieve author works failed: {e}")
        return []

    results = []
    for work in data.get("results", []):
        results.append({
            "id": work.get("id"),
            "title": work.get("title"),
            "year": work.get("publication_year"),
            "citations": work.get("cited_by_count", 0),
            "oa_url": work.get("open_access", {}).get("oa_url")
        })
    return results


async def get_author_profile_scopus(author_id: str) -> Dict[str, Any]:
    """Get author profile via Scopus API."""
    if not SCOPUS_API_KEY:
        raise ValueError("SCOPUS_API_KEY is not set.")

    url = f"https://api.elsevier.com/content/author/author_id/{author_id}"
    headers = {"X-ELS-APIKey": SCOPUS_API_KEY, "Accept": "application/json"}
    if SCOPUS_INST_TOKEN:
        headers["X-ELS-Insttoken"] = SCOPUS_INST_TOKEN

    try:
        res = await _robust_fetch(url, headers=headers)
        data = res.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"Scopus author query failed: HTTP {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Scopus network failure: {str(e)}"}

    author_resp = data.get("author-retrieval-response", [{}])[0]
    profile = author_resp.get("author-profile", {})
    name_obj = profile.get("preferred-name", {})
    name = f"{name_obj.get('given-name', '')} {name_obj.get('surname', '')}".strip()

    affiliation_current = profile.get("affiliation-current", {})
    if isinstance(affiliation_current, list):
        affil_node = affiliation_current[0] if affiliation_current else {}
    else:
        affil_node = affiliation_current
    current_affiliation = affil_node.get("affiliation", {}).get("ip-doc", {}).get("afdispname", "Unknown")

    return {
        "scopus_id": author_resp.get("coredata", {}).get("dc:identifier", "").split(":")[-1],
        "name": name,
        "document_count": author_resp.get("coredata", {}).get("document-count", "0"),
        "cited_by_count": author_resp.get("coredata", {}).get("cited-by-count", "0"),
        "citation_count": author_resp.get("coredata", {}).get("citation-count", "0"),
        "h_index": author_resp.get("h-index", "N/A"),
        "current_affiliation": current_affiliation
    }


async def search_titles_unpaywall(query: str, is_oa: bool = None, page: int = 1) -> Dict[str, Any]:
    """Hits Unpaywall title search directly."""
    url = "https://api.unpaywall.org/v2/search"
    params: Dict[str, Any] = {
        "query": query,
        "email": CONTACT_EMAIL,
        "page": page
    }
    if is_oa is True:
        params["is_oa"] = "true"
    elif is_oa is False:
        params["is_oa"] = "false"

    try:
        res = await _robust_fetch(url, params=params)
        return res.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"Unpaywall search failed: HTTP {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Unpaywall network failure: {str(e)}"}


async def get_citations_openalex(doi_or_id: str, direction: str = "references", limit: int = 20) -> List[Dict[str, Any]]:
    """Tracks lineage of a paper (forward/backward citations)."""
    doi_or_id = _normalize_doi(doi_or_id)

    if doi_or_id.startswith("10."):
        resolve_url = f"https://api.openalex.org/works/https://doi.org/{doi_or_id}"
    elif doi_or_id.startswith("W"):
        resolve_url = f"https://api.openalex.org/works/{doi_or_id}"
    else:
        raise ValueError("Citation tracking requires a DOI (e.g., 10.10xx/...) or an OpenAlex ID (e.g., Wxxxx).")

    try:
        res = await _robust_fetch(resolve_url, params={"mailto": CONTACT_EMAIL})
        work_data = res.json()
        openalex_id = (work_data.get("id") or "").split("/")[-1]
    except Exception as e:
        logger.error(f"Citation resolution failed: {e}")
        return []

    if not openalex_id:
        return []

    url = "https://api.openalex.org/works"
    target_filter = f"cites:{openalex_id}" if direction == "citations" else f"cited_by:{openalex_id}"

    params = {
        "filter": target_filter,
        "per-page": min(limit, 100),
        "mailto": CONTACT_EMAIL
    }

    try:
        response = await _robust_fetch(url, params=params)
        data = response.json()
    except Exception as e:
        logger.error(f"Citation retrieval failed: {e}")
        return []

    results = []
    for work in data.get("results", []):
        results.append({
            "id": work.get("id"),
            "title": work.get("title", ""),
            "authors": [a.get("author", {}).get("display_name") for a in work.get("authorships", [])],
            "year": work.get("publication_year", ""),
            "doi": work.get("doi", ""),
            "open_access_pdf": work.get("open_access", {}).get("oa_url")
        })
    return results


async def get_bibtex_crossref(doi: str) -> str:
    """Fetches a BibTeX entry via CrossRef content negotiation."""
    doi = _normalize_doi(doi)
    if not doi:
        return "Error: No DOI provided."

    url = f"https://doi.org/{doi}"
    headers = {"Accept": "application/x-bibtex"}

    try:
        res = await _robust_fetch(url, headers=headers)
        return res.text.strip()
    except httpx.HTTPStatusError as e:
        return f"Error: CrossRef returned HTTP {e.response.status_code} for DOI: {doi}"
    except Exception as e:
        return f"Error fetching BibTeX: {str(e)}"


async def format_citation_crossref(doi: str, style: str = "apa") -> str:
    """Formats a citation via CrossRef/DOI content negotiation."""
    doi = _normalize_doi(doi)
    if not doi:
        return "Error: No DOI provided."

    url = f"https://doi.org/{doi}"
    headers = {"Accept": f"text/x-bibliography; style={style}"}

    try:
        res = await _robust_fetch(url, headers=headers)
        return res.text.strip()
    except httpx.HTTPStatusError as e:
        return f"Error: Citation service returned HTTP {e.response.status_code} for DOI: {doi} with style: {style}"
    except Exception as e:
        return f"Error formatting citation: {str(e)}"


async def get_related_works_openalex(paper_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Gets related/similar works via OpenAlex's related_works field."""
    paper_id = _normalize_doi(paper_id)

    if paper_id.startswith("10."):
        url = f"https://api.openalex.org/works/https://doi.org/{paper_id}"
    elif paper_id.startswith("W"):
        url = f"https://api.openalex.org/works/{paper_id}"
    else:
        return []

    try:
        res = await _robust_fetch(url, params={"mailto": CONTACT_EMAIL})
        work = res.json()
    except Exception as e:
        logger.error(f"Failed to fetch base paper for related works: {e}")
        return []

    related_ids = work.get("related_works", [])[:limit]
    if not related_ids:
        return []

    openalex_filter = "|".join(r.split("/")[-1] for r in related_ids)
    params = {
        "filter": f"openalex:{openalex_filter}",
        "per-page": limit,
        "mailto": CONTACT_EMAIL
    }

    try:
        res = await _robust_fetch("https://api.openalex.org/works", params=params)
        data = res.json()
    except Exception as e:
        logger.error(f"Failed to retrieve related works batch: {e}")
        return []

    results = []
    for w in data.get("results", []):
        results.append({
            "id": w.get("id"),
            "title": w.get("title", ""),
            "authors": [a.get("author", {}).get("display_name") for a in w.get("authorships", [])],
            "year": w.get("publication_year", ""),
            "doi": w.get("doi", ""),
            "cited_by_count": w.get("cited_by_count", 0),
            "open_access_pdf": w.get("open_access", {}).get("oa_url")
        })
    return results


async def _fetch_openalex_chunk(chunk: List[str]) -> List[Dict[str, Any]]:
    doi_filter = "|".join(f"https://doi.org/{d}" for d in chunk)
    params = {"filter": f"doi:{doi_filter}", "per-page": len(chunk), "mailto": CONTACT_EMAIL}
    res = await _robust_fetch("https://api.openalex.org/works", params=params)
    return res.json().get("results", [])

async def batch_get_papers_openalex(dois: List[str]) -> List[Dict[str, Any]]:
    """Batch-fetch metadata for multiple DOIs using chunked concurrency."""
    normalized = [_normalize_doi(d) for d in dois if _normalize_doi(d)]
    if not normalized:
        return []

    chunks = [normalized[i:i + 15] for i in range(0, len(normalized), 15)]
    results = []

    tasks = [_fetch_openalex_chunk(chunk) for chunk in chunks]
    chunked_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for r_chunk in chunked_results:
        if isinstance(r_chunk, Exception):
            logger.error(f"Error fetching batch chunk: {r_chunk}")
            continue
        
        for work in r_chunk:
            oa = work.get("open_access", {})
            authors = [a.get("author", {}).get("display_name") for a in work.get("authorships", [])]
            try:
                meta = PaperMetadata(
                    id=work.get("id"),
                    title=work.get("title") or "Unknown Title",
                    authors=[a for a in authors if a],
                    year=work.get("publication_year"),
                    doi=work.get("doi"),
                    cited_by_count=work.get("cited_by_count", 0),
                    is_oa=oa.get("is_oa", False),
                    open_access_pdf=oa.get("oa_url")
                )
                results.append(meta.model_dump())
            except Exception as e:
                logger.warning(f"Pydantic validation failed for batch item: {e}")
                
    return results


async def search_topics_openalex(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search OpenAlex topics/concepts for a given keyword."""
    url = "https://api.openalex.org/topics"
    params = {
        "search": query,
        "per-page": min(limit, 50),
        "mailto": CONTACT_EMAIL
    }

    try:
        res = await _robust_fetch(url, params=params)
        data = res.json()
    except Exception as e:
        logger.error(f"Search topics failed: {e}")
        return []

    results = []
    for topic in data.get("results", []):
        try:
            item = TopicItem(
                id=topic.get("id"),
                display_name=topic.get("display_name") or "",
                subfield=topic.get("subfield", {}).get("display_name") or "",
                field=topic.get("field", {}).get("display_name") or "",
                domain=topic.get("domain", {}).get("display_name") or "",
                works_count=topic.get("works_count", 0),
                cited_by_count=topic.get("cited_by_count", 0),
                description=topic.get("description", "")
            )
            results.append(item.model_dump())
        except Exception as e:
            logger.warning(f"Validation failed for topic item: {e}")
            
    return results


async def search_author_by_orcid_openalex(orcid: str) -> Dict[str, Any]:
    """Look up an author by ORCID via OpenAlex."""
    if not orcid.startswith("https://"):
        orcid = f"https://orcid.org/{orcid}"

    url = "https://api.openalex.org/authors"
    params = {
        "filter": f"orcid:{orcid}",
        "mailto": CONTACT_EMAIL
    }

    try:
        res = await _robust_fetch(url, params=params)
        data = res.json()
    except httpx.HTTPStatusError as e:
        return {"error": f"OpenAlex returned HTTP {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Failed to retrieve author by ORCID: {str(e)}"}

    authors = data.get("results", [])
    if not authors:
        return {"error": f"No author found for ORCID: {orcid}"}

    author = authors[0]
    affil = author.get("last_known_institutions", [{}])
    last_inst = affil[0].get("display_name", "Unknown") if isinstance(affil, list) and affil else "Unknown"

    try:
        profile = AuthorProfile(
            id=author.get("id"),
            display_name=author.get("display_name") or "Unknown",
            orcid=author.get("orcid"),
            works_count=author.get("works_count", 0),
            cited_by_count=author.get("cited_by_count", 0),
            h_index=author.get("summary_stats", {}).get("h_index", 0) or 0,
            i10_index=author.get("summary_stats", {}).get("i10_index", 0) or 0,
            last_institution=last_inst,
            x_concepts=[c.get("display_name") for c in author.get("x_concepts", [])[:5]]
        )
        return profile.model_dump()
    except Exception as e:
        logger.error(f"Author profile validation failed: {e}")
        return {"error": "Failed to parse author profile."}
