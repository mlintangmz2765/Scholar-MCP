from mcp.server.fastmcp import FastMCP, Image
from typing import List, Dict, Any, Optional

from api import (
    search_papers_scopus, get_paper_details_scopus, get_paper_details_openalex,
    get_author_profile_scopus, search_papers_openalex, get_citations_openalex,
    autocomplete_authors_openalex, search_authors_openalex,
    retrieve_author_works_openalex, get_unpaywall_pdf_link, search_titles_unpaywall
)
from extractor import extract_text_from_pdf_url, render_pdf_to_images_from_url

mcp = FastMCP("Scholar MCP Server")

@mcp.tool()
async def search_papers_tool(query: str, limit: int = 5, use_scopus: bool = True) -> str:
    """
    Searches the Scopus library by accepting standard textual querying or advanced 
    Scopus Boolean Syntax (e.g. `TITLE-ABS-KEY(artificial intelligence) AND PUBYEAR > 2020`).
    Returns metadata summaries.
    Set use_scopus=False to use OpenAlex which guarantees Open Access PDF links but might have less robust abstracts in standard search.
    Returns a formatted string of results.
    """
    if not query or not query.strip():
        return "Error: query cannot be empty."

    try:
        if use_scopus:
            results = await search_papers_scopus(query, limit)
            source = "Scopus"
        else:
            results = await search_papers_openalex(query, limit)
            source = "OpenAlex"

        if not results:
            return f"No papers found for query '{query}' in {source}."

        output = [f"Found {len(results)} papers via {source}:\n"]
        for p in results:
            output.append(f"- [{p['id']}] {p['title']}")
            output.append(f"  Authors: {', '.join(p['authors']) if isinstance(p['authors'], list) else p['authors']}")
            if source == "OpenAlex":
                output.append(f"  Year: {p.get('year', '')}")
                output.append(f"  Volume: {p.get('volume', '')}, Issue: {p.get('issue', '')}, Pages: {p.get('pages', '')}")
                output.append(f"  OA PDF: {p.get('open_access_pdf') or 'Not Available'}")
                output.append(f"  Snippet: {p.get('abstract_snippet', '')}")
            else:
                output.append(f"  Date: {p.get('date', '')}")
                output.append(f"  DOI: {p.get('doi', '')}")
                output.append(f"  Abstract Available: {p.get('abstract_available', False)}")
            output.append("")

        return "\n".join(output)
    except Exception as e:
        return f"Error searching papers: {str(e)}"

@mcp.tool()
async def get_paper_details_tool(paper_id: str) -> str:
    """
    Get detailed metadata and the full abstract for a specific paper.
    If the paper_id looks like a Scopus ID (e.g., SCOPUS_ID:85123) or a DOI (10.xxx), it uses Scopus.
    Returns formatted detailed text.
    """
    try:
        is_openalex = paper_id.startswith("W") or paper_id.startswith("https://openalex.org/")

        if is_openalex:
            details = await get_paper_details_openalex(paper_id)
            if "error" in details:
                return f"Error: {details['error']}"
            output = [
                f"Title: {details.get('title')}",
                f"Authors: {', '.join(details.get('authors', []))}",
                f"Year: {details.get('year')}",
                f"DOI: {details.get('doi')}",
                f"Open Access: {details.get('openAccess')}",
                f"OA PDF: {details.get('open_access_pdf') or 'None'}",
                f"Cited By: {details.get('cited_by_count', 0)}",
                f"\nAbstract:\n{details.get('abstract')}"
            ]
            return "\n".join(output)

        details = await get_paper_details_scopus(paper_id)
        if "error" in details:
            return (
                f"Access Error: {details['error']}\n\n"
                "AI Instruction: You failed to retrieve this abstract/paper details due to an API limitation or paywall (e.g., 401 Unauthorized from Scopus). "
                "Please inform the user that the system cannot access the full metadata automatically, and politely ask them to download the PDF manually and upload/attach it to this chat so you can analyze it."
            )

        output = [
            f"Title: {details.get('title')}",
            f"Authors: {', '.join(details.get('authors', []))}",
            f"Publication: {details.get('publicationName')}",
            f"Volume: {details.get('volume', '')}, Issue: {details.get('issue', '')}, Pages: {details.get('pages', '')}",
            f"Date: {details.get('date')}",
            f"DOI: {details.get('doi')}",
            f"Open Access: {details.get('openAccess')}"
        ]

        if not str(details.get('openAccess')).lower() in ['true', '1', 'yes']:
            output.append("AI Instruction: This paper is CLOSED ACCESS. You cannot use get_full_text_tool for it. If you vitally need the full text, ask the user to manually download the PDF and provide it to you.")

        output.extend([
            f"PDF Link Hint: {details.get('pdf_link_hint') or 'None'}",
            f"\nAbstract:\n{details.get('abstract')}"
        ])
        return "\n".join(output)
    except Exception as e:
        return f"Error getting details: {str(e)}"

@mcp.tool()
async def get_full_text_tool(url: str) -> str:
    """
    Extracts full text from an Open Access PDF or HTML page given its URL.
    This is best used after finding an OA PDF link from search_papers_openalex.
    Warning: This can return a very large string.
    """
    try:
        text = await extract_text_from_pdf_url(url)
        return text
    except Exception as e:
        return f"Error extracting full text from {url}: {str(e)}"

@mcp.tool()
async def get_full_text_visual_tool(url: str, max_pages: int = 3) -> list:
    """
    Multimodal Vision Tool.
    Downloads a PDF and renders the specified number of pages identically into images for the AI to 'look at'.
    Use this if the user asks you to analyze a graph, table, format, or layout in the paper.
    If the text extractor doesn't capture formatting, you can use this tool to 'see' the actual PDF!
    Returns a sequence of texts and images (multimodal format natively parsed).
    Warning: High token/vision capacity used per page. Default 3 pages.
    """
    try:
        pages = await render_pdf_to_images_from_url(url, max_pages)
        output = [f"Successfully rendered {len(pages)} pages visually from '{url}'. Here are the images:"]
        for p in pages:
            output.append(f"--- Page {p['page']} Visually Rendered ---")
            output.append(Image(data=p["data"], format="png"))

        return output
    except Exception as e:
        return [f"Error rendering visual PDF from {url}: {str(e)}"]

@mcp.tool()
async def get_unpaywall_link_tool(doi: str) -> str:
    """
    Checks the Unpaywall database using a DOI to find a legal Open Access PDF link.
    If found, returns the URL. If not, returns that it's behind a strict paywall.
    """
    try:
        info = await get_unpaywall_pdf_link(doi)
        if "error" in info:
            return info["error"]
        if not info.get("is_oa"):
            return "No Open Access route found on Unpaywall. The paper is strictly behind a paywall."
        best = info.get("best_oa_location")
        if best:
            pdf_url = best.get("url_for_pdf") or best.get("url") or ""
            return f"Success! Found legal Open Access PDF via Unpaywall: {pdf_url}"
        return "Unpaywall reports OA but no direct link was found."
    except Exception as e:
        return f"Error querying Unpaywall: {str(e)}"

@mcp.tool()
async def get_citations_tool(paper_id: str, direction: str = "references") -> str:
    """
    Tracks lineage by retrieving a paper's citations.
    Provide a DOI (10.xxx) or OpenAlex ID (Wxxx).
    Set direction="references" to see who this paper cites.
    Set direction="citations" to see who cited this paper recently.
    """
    if direction not in ("references", "citations"):
        return f"Error: direction must be 'references' or 'citations', got '{direction}'."

    try:
        results = await get_citations_openalex(paper_id, direction, limit=20)
        if not results:
            return f"No results found for {direction} of paper {paper_id}."

        output = [f"Found {len(results)} {direction} for {paper_id}:\n"]
        for p in results:
            output.append(f"- [{p['id']}] {p['title']}")
            output.append(f"  Authors: {', '.join(p['authors']) if isinstance(p['authors'], list) else p['authors']}")
            output.append(f"  Year: {p.get('year', '')}")
            output.append(f"  DOI: {p.get('doi', '')}")
            output.append(f"  OA PDF: {p.get('open_access_pdf') or 'Not Available'}")
            output.append("")
        return "\n".join(output)
    except Exception as e:
        return f"Error tracking citations: {str(e)}"

@mcp.tool()
async def autocomplete_authors_tool(name: str, limit: int = 5) -> str:
    """
    Rapidly autocomplete author names via OpenAlex to find the correct OpenAlex ID.
    Useful for disambiguation before tracking works.
    """
    try:
        results = await autocomplete_authors_openalex(name, limit)
        if not results:
            return f"No authors found matching '{name}'."
        out = [f"Found {len(results)} autocomplete suggestions:\n"]
        for r in results:
            out.append(f"- ID: {r['id']}")
            out.append(f"  Name: {r['display_name']} ({r['hint']})")
            out.append(f"  Metrics: {r['works_count']} works, {r['cited_by_count']} citations\n")
        return "\n".join(out)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def search_authors_tool(name: str, institution: str = None, limit: int = 5) -> str:
    """
    Search for deep author profiles via OpenAlex. Returns h-index, i10-index, and recent institutions.
    """
    try:
        results = await search_authors_openalex(name, institution, limit)
        if not results:
            return f"No detailed author profiles found for '{name}'."
        out = [f"Found {len(results)} detailed profiles:\n"]
        for r in results:
            out.append(f"- ID: {r['id']}")
            out.append(f"  Name: {r['display_name']} (ORCID: {r['orcid']})")
            out.append(f"  Institution: {r['last_institution']}")
            out.append(f"  Metrics: {r['works_count']} works, H-Index: {r['h_index']}, i10-Index: {r['i10_index']}")
            out.append(f"  Concepts: {', '.join(r['x_concepts'])}\n")
        return "\n".join(out)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def retrieve_author_works_tool(author_id: str, limit: int = 15) -> str:
    """
    Retrieve chronologically sorted publications for an OpenAlex author ID.
    E.g., input 'W123456789' or 'https://openalex.org/A123456789'.
    """
    try:
        results = await retrieve_author_works_openalex(author_id, limit)
        if not results:
            return f"No works found for author {author_id}."
        out = [f"Found {len(results)} works for {author_id}:\n"]
        for r in results:
            out.append(f"- [{r['year']}] {r['title']} (Citations: {r['citations']})")
            out.append(f"  ID: {r['id']}")
            out.append(f"  OA PDF: {r['oa_url']}\n")
        return "\n".join(out)
    except Exception as e:
        return f"Error: {e}"

@mcp.tool()
async def get_author_profile_scopus_tool(author_id: str) -> str:
    """
    Retrieve Elsevier Scopus Author Profile strictly using a Scopus Author ID (digits).
    Returns precise academic h-index and document metrics from Scopus.
    """
    try:
        r = await get_author_profile_scopus(author_id)
        if "error" in r:
            return r["error"]
        out = [
            f"Scopus Profile for ID: {r['scopus_id']}",
            f"Name: {r['name']}",
            f"Affiliation: {r['current_affiliation']}",
            f"Documents: {r['document_count']}",
            f"Total Citations: {r['citation_count']} (from {r['cited_by_count']} documents)",
            f"H-Index: {r['h_index']}"
        ]
        return "\n".join(out)
    except Exception as e:
        return f"Error pulling Scopus author profile: {e}"

@mcp.tool()
async def search_titles_unpaywall_tool(query: str, is_oa: bool = None) -> str:
    """
    Natively search Unpaywall's database via paper titles.
    Set is_oa=True to strictly return Open Access results.
    """
    try:
        data = await search_titles_unpaywall(query, is_oa)
        if "error" in data:
            return data["error"]
        results = data.get("results", [])
        if not results:
            return "No titles found in Unpaywall."

        out = [f"Found {len(results)} results in Unpaywall:\n"]
        for r in results:
            resp = r.get("response", {})
            out.append(f"- {resp.get('title')}")
            out.append(f"  DOI: {resp.get('doi')}")
            out.append(f"  Is OA: {resp.get('is_oa', False)}")
            loc = resp.get("best_oa_location")
            if loc:
                out.append(f"  PDF URL: {loc.get('url_for_pdf') or loc.get('url')}")
            out.append("")
        return "\n".join(out)
    except Exception as e:
        return f"Error using Unpaywall search: {e}"

@mcp.tool()
async def fetch_pdf_text_unpaywall_tool(doi: str) -> str:
    """
    An all-in-one bypass. Takes a DOI, resolves its best PDF on Unpaywall,
    and directly downloads/extracts the text using PyMuPDF.
    """
    try:
        info = await get_unpaywall_pdf_link(doi)
        if "error" in info:
            return info["error"]

        best = info.get("best_oa_location")
        if not best:
            return f"Unpaywall confirms no Open Access PDF exists for DOI: {doi}."

        pdf_url = best.get("url_for_pdf") or best.get("url")
        if not pdf_url:
            return f"Found OA location but no direct PDF URL for DOI: {doi}."

        return await extract_text_from_pdf_url(pdf_url)
    except Exception as e:
        return f"Error fetching and extracting Unpaywall text: {e}"

if __name__ == "__main__":
    mcp.run()
