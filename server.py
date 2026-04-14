from mcp.server.fastmcp import FastMCP, Image
from typing import List, Dict, Any, Optional

from api import search_papers_scopus, get_paper_details_scopus, search_papers_openalex, get_unpaywall_pdf_link
from extractor import extract_text_from_pdf_url, render_pdf_to_images_from_url

mcp = FastMCP("Scholar MCP Server")

@mcp.tool()
async def search_papers_tool(query: str, limit: int = 5, use_scopus: bool = True) -> str:
    """
    Search for scientific papers using a keyword query.
    By default uses Scopus API if available, which provides high-quality metadata.
    Set use_scopus=False to use OpenAlex which guarantees Open Access PDF links but might have less robust abstracts in standard search.
    Returns a formatted string of results.
    """
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
            output.append("") # empty line

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
        # Currently we only implemented detailed lookup for Scopus.
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
        
        # Add AI Context Prompt for manual downloads if it's closed access
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
        link = await get_unpaywall_pdf_link(doi)
        if link:
            return f"Success! Found legal Open Access PDF via Unpaywall: {link}"
        return "No Open Access route found on Unpaywall. The paper is strictly behind a paywall."
    except Exception as e:
        return f"Error querying Unpaywall: {str(e)}"

if __name__ == "__main__":
    # Provides stdio stream capabilities natively via FastMCP
    mcp.run()
