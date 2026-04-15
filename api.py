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
        "view": "STANDARD"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
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

    headers = {
        "Accept": "application/json"
    }
    if SCOPUS_INST_TOKEN:
        headers["X-ELS-Insttoken"] = SCOPUS_INST_TOKEN
    
    if "SCOPUS_ID:" in scopus_id_or_doi:
        identifier = scopus_id_or_doi.split(":")[-1]
        url = f"https://api.elsevier.com/content/abstract/scopus_id/{identifier}"
    elif scopus_id_or_doi.startswith("10."):  # DOI
        url = f"https://api.elsevier.com/content/abstract/doi/{scopus_id_or_doi}"
    else:
        identifier = scopus_id_or_doi.replace("SCOPUS_ID:", "").replace("scopus_id:", "")
        url = f"https://api.elsevier.com/content/abstract/scopus_id/{identifier}"

    params = {"view": "META_ABS", "apiKey": SCOPUS_API_KEY, "httpAccept": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, params=params)
        
        if response.status_code != 200:
            return {"error": f"Failed to retrieve data. Status code: {response.status_code}", "raw": response.text}

        data = response.json()
        
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

async def get_unpaywall_pdf_link(doi: str) -> Dict[str, Any]:
    """
    Query Unpaywall API to find Open Access information.
    Instead of just returning one link, it returns all OA locations to mirror unpaywall-mcp capability.
    """
    if not doi:
        return {"error": "No DOI provided"}
        
    url = f"https://api.unpaywall.org/v2/{doi}"
    params = {"email": CONTACT_EMAIL}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            if response.status_code == 200:
                data = response.json()
                return {
                    "is_oa": data.get("is_oa", False),
                    "best_oa_location": data.get("best_oa_location"),
                    "oa_locations": data.get("oa_locations", []),
                    "title": data.get("title")
                }
    except Exception as e:
        return {"error": f"Error contacting Unpaywall: {str(e)}"}
    
    return {"error": "Failed to resolve DOI at Unpaywall."}

# ==========================================
# OPENALEX AUTHOR ANALYTICS (from alex-mcp)
# ==========================================

async def autocomplete_authors_openalex(name: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Rapidly search api.openalex.org/autocomplete/authors.
    """
    url = "https://api.openalex.org/autocomplete/authors"
    params = {"q": name, "mailto": CONTACT_EMAIL}
    
    async with httpx.AsyncClient() as client:
        res = await client.get(url, params=params)
        if res.status_code != 200:
            return []
        data = res.json()
    
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
    """
    Deep profile search using normal /authors endpoint for authors.
    """
    url = "https://api.openalex.org/authors"
    params = {"search": name, "mailto": CONTACT_EMAIL, "per-page": limit}
        
    async with httpx.AsyncClient() as client:
        res = await client.get(url, params=params)
        if res.status_code != 200:
            return []
        data = res.json()
        
    results = []
    for author in data.get("results", []):
        affil = author.get("last_known_institution", {})
        results.append({
            "id": author.get("id"),
            "display_name": author.get("display_name"),
            "orcid": author.get("orcid"),
            "works_count": author.get("works_count"),
            "cited_by_count": author.get("cited_by_count"),
            "h_index": author.get("summary_stats", {}).get("h_index"),
            "i10_index": author.get("summary_stats", {}).get("i10_index"),
            "last_institution": affil.get("display_name") if affil else "Unknown",
            "x_concepts": [c.get("display_name") for c in author.get("x_concepts", [])[:3]]
        })
    return results

async def retrieve_author_works_openalex(author_id: str, limit: int = 15) -> List[Dict[str, Any]]:
    """
    Retrieves chronologically sorted works by an author.
    author_id should be an OpenAlex ID (e.g. Wxxx or Axxx).
    """
    if author_id.startswith("http"):
        author_id = author_id.split("/")[-1]
        
    url = "https://api.openalex.org/works"
    params = {
        "filter": f"author.id:{author_id}",
        "sort": "publication_year:desc,cited_by_count:desc",
        "per-page": limit,
        "mailto": CONTACT_EMAIL
    }
    
    async with httpx.AsyncClient() as client:
        res = await client.get(url, params=params)
        res.raise_for_status()
        data = res.json()
        
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

# ==========================================
# SCOPUS AUTHOR ANALYTICS (from scopus-mcp)
# ==========================================

async def get_author_profile_scopus(author_id: str) -> Dict[str, Any]:
    """
    Get author profile via Scopus API.
    """
    if not SCOPUS_API_KEY:
        raise ValueError("SCOPUS_API_KEY is not set.")
        
    url = f"https://api.elsevier.com/content/author/author_id/{author_id}"
    headers = {"X-ELS-APIKey": SCOPUS_API_KEY, "Accept": "application/json"}
    if SCOPUS_INST_TOKEN:
        headers["X-ELS-Insttoken"] = SCOPUS_INST_TOKEN
        
    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers)
        if res.status_code != 200:
            return {"error": f"Scopus auth query failed: {res.status_code}", "raw": res.text}
        data = res.json()
        
    author_resp = data.get("author-retrieval-response", [{}])[0]
    profile = author_resp.get("author-profile", {})
    name_obj = profile.get("preferred-name", {})
    name = f"{name_obj.get('given-name', '')} {name_obj.get('surname', '')}".strip()
    
    return {
        "scopus_id": author_resp.get("coredata", {}).get("dc:identifier", "").split(":")[-1],
        "name": name,
        "document_count": author_resp.get("coredata", {}).get("document-count", "0"),
        "cited_by_count": author_resp.get("coredata", {}).get("cited-by-count", "0"),
        "citation_count": author_resp.get("coredata", {}).get("citation-count", "0"),
        "h_index": author_resp.get("h-index", "N/A"),
        "current_affiliation": profile.get("affiliation-current", {}).get("affiliation", {}).get("ip-doc", {}).get("afdispname", "Unknown")
    }

# ==========================================
# UNPAYWALL SEARCH (from unpaywall-mcp)
# ==========================================

async def search_titles_unpaywall(query: str, is_oa: bool = None, page: int = 1) -> Dict[str, Any]:
    """
    Hits Unpaywall title search directly.
    """
    url = "https://api.unpaywall.org/v2/search"
    params = {
        "query": query,
        "email": CONTACT_EMAIL,
        "page": page
    }
    if is_oa is True:
        params["is_oa"] = "true"
    elif is_oa is False:
        params["is_oa"] = "false"
        
    async with httpx.AsyncClient() as client:
        res = await client.get(url, params=params)
        if res.status_code != 200:
            return {"error": f"Failed Unpaywall search: {res.status_code}", "raw": res.text}
        
    return res.json()

async def get_citations_openalex(doi_or_id: str, direction: str = "references", limit: int = 20) -> List[Dict[str, Any]]:
    """
    Tracks lineage of a paper.
    direction="references": returns papers that the target paper cited.
    direction="citations": returns papers that cite the target paper.
    """
    if doi_or_id.startswith("10."):
        resolve_url = f"https://api.openalex.org/works/https://doi.org/{doi_or_id}"
    elif doi_or_id.startswith("W"):
        resolve_url = f"https://api.openalex.org/works/{doi_or_id}"
    else:
        raise ValueError("Citation tracking requires a DOI (e.g., 10.10xx/...) or an OpenAlex ID (e.g., Wxxxx).")
        
    async with httpx.AsyncClient(follow_redirects=True) as client:
        res = await client.get(resolve_url, params={"mailto": CONTACT_EMAIL})
        res.raise_for_status()
        work_data = res.json()
        openalex_id = work_data.get("id").split("/")[-1]
        
    url = "https://api.openalex.org/works"
    if direction == "citations":
        target_filter = f"cites:{openalex_id}"
    else:
        target_filter = f"cited_by:{openalex_id}"
        
    params = {
        "filter": target_filter,
        "per-page": limit,
        "mailto": CONTACT_EMAIL
    }
    
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        
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
