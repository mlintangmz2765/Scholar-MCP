import os
import httpx
from typing import Dict, Any, List
from dotenv import load_dotenv

load_dotenv()

SCOPUS_API_KEY = os.getenv("SCOPUS_API_KEY")
SCOPUS_INST_TOKEN = os.getenv("SCOPUS_INST_TOKEN")
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "developer@example.com")

async def search_papers_scopus(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search papers using Scopus API.
    Returns a list of brief paper metadata.
    """
    if not SCOPUS_API_KEY:
        raise ValueError("SCOPUS_API_KEY is not set.")
        
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
        # 'view': 'COMPLETE' might require special entitlement, 'STANDARD' is safer.
        "view": "STANDARD"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
    results = []
    entries = data.get("search-results", {}).get("entry", [])
    for entry in entries:
        # Some fields might be absent
        results.append({
            "id": entry.get("dc:identifier", ""),
            "title": entry.get("dc:title", ""),
            "authors": entry.get("dc:creator", "Unknown"),
            "publication_name": entry.get("prism:publicationName", ""),
            "date": entry.get("prism:coverDate", ""),
            "doi": entry.get("prism:doi", ""),
            "url": entry.get("prism:url", ""),
            # Scopus search standard view may not give full abstract, we'll indicate that
            "abstract_available": True if "dc:description" in entry else False,
            "abstract_snippet": entry.get("dc:description", "Abstract snippet not available in standard search. Use get_paper_details for full abstract.")
        })
    return results


async def get_paper_details_scopus(scopus_id_or_doi: str) -> Dict[str, Any]:
    """
    Get full paper details including abstract from Scopus API.
    """
    if not SCOPUS_API_KEY:
        raise ValueError("SCOPUS_API_KEY is not set.")

    # Scopus API allows fetching abstract by scopus_id
    # Endpoint: https://api.elsevier.com/content/abstract/scopus_id/{scopus_id}
    # Or by DOI: /content/abstract/doi/{doi}

    headers = {
        "Accept": "application/json"
    }
    if SCOPUS_INST_TOKEN:
        headers["X-ELS-Insttoken"] = SCOPUS_INST_TOKEN
    
    # Check if doi or scopus id
    if "SCOPUS_ID:" in scopus_id_or_doi:
        identifier = scopus_id_or_doi.split(":")[-1]
        url = f"https://api.elsevier.com/content/abstract/scopus_id/{identifier}"
    elif scopus_id_or_doi.startswith("10."):  # DOI
        url = f"https://api.elsevier.com/content/abstract/doi/{scopus_id_or_doi}"
    else:
        # Clean potential formats
        identifier = scopus_id_or_doi.replace("SCOPUS_ID:", "").replace("scopus_id:", "")
        url = f"https://api.elsevier.com/content/abstract/scopus_id/{identifier}"

    params = {"view": "META_ABS", "apiKey": SCOPUS_API_KEY, "httpAccept": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            return {"error": f"Failed to retrieve data. Status code: {response.status_code}", "raw": response.text}

        data = response.json()
        
    # Extract robust metadata
    abstract_retrieval = data.get("abstracts-retrieval-response", {})
    coredata = abstract_retrieval.get("coredata", {})
    
    title = coredata.get("dc:title", "")
    abstract = coredata.get("dc:description", "Abstract not available.")
    doi = coredata.get("prism:doi", "")
    open_access = coredata.get("openaccessFlag", False)
    # Get links for pdf or full text
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


async def search_papers_openalex(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Fallback/Alternative search using OpenAlex, deeply integrated with Open Access PDFs.
    """
    url = "https://api.openalex.org/works"
    params = {
        "search": query,
        "per-page": limit,
        "mailto": CONTACT_EMAIL
    }

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()

    results = []
    for work in data.get("results", []):
        oa_info = work.get("open_access", {})
        oa_url = oa_info.get("oa_url")
        
        # OpenAlex uses inverted abstract, reconstruct it:
        abstract = "Abstract not available/not parsed here."
        inv_abstract = work.get("abstract_inverted_index")
        if inv_abstract:
            words = []
            max_index = max([max(pos) for pos in inv_abstract.values()]) if inv_abstract else -1
            if max_index >= 0:
                words = [""] * (max_index + 1)
                for word, indices in inv_abstract.items():
                    for idx in indices:
                        words[idx] = word
                abstract = " ".join(words)

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

async def get_unpaywall_pdf_link(doi: str) -> str:
    """
    Query Unpaywall API to find an Open Access PDF link using the DOI.
    Returns the URL or an error message.
    """
    if not doi:
        return ""
        
    url = f"https://api.unpaywall.org/v2/{doi}"
    # Unpaywall requires an email parameter for respectful rate-limits
    params = {"email": CONTACT_EMAIL}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                loc = data.get("best_oa_location")
                if loc:
                    return loc.get("url_for_pdf") or loc.get("url") or ""
    except Exception as e:
        return f"Error contacting Unpaywall: {str(e)}"
    
    return ""
