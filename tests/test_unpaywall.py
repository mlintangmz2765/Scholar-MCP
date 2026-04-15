import pytest
import respx
import httpx
from api import get_unpaywall_pdf_link, search_titles_unpaywall

@pytest.mark.asyncio
@respx.mock
async def test_get_unpaywall_pdf_link():
    doi = "10.1234/nature.1"
    mock_data = {
        "is_oa": True,
        "best_oa_location": {"url_for_pdf": "https://example.com/best.pdf"},
        "oa_locations": [{"url": "https://example.com/loc.pdf"}],
        "title": "OA Paper Title"
    }
    respx.get(f"https://api.unpaywall.org/v2/{doi}").mock(return_value=httpx.Response(200, json=mock_data))

    result = await get_unpaywall_pdf_link(doi)
    
    assert "error" not in result
    assert result["is_oa"] is True
    assert result["title"] == "OA Paper Title"
    assert result["best_oa_location"]["url_for_pdf"] == "https://example.com/best.pdf"

@pytest.mark.asyncio
@respx.mock
async def test_search_titles_unpaywall():
    query = "global warming"
    mock_data = {
        "results": [
            {
                "response": {
                    "title": "A study on global warming",
                    "doi": "10.1234/gw.1",
                    "is_oa": True
                },
                "score": 0.9
            }
        ]
    }
    respx.get("https://api.unpaywall.org/v2/search").mock(return_value=httpx.Response(200, json=mock_data))

    result = await search_titles_unpaywall(query)
    
    assert "error" not in result
    assert "results" in result
    assert result["results"][0]["response"]["title"] == "A study on global warming"
