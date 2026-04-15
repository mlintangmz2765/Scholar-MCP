import pytest
import respx
import httpx
import os
from api import (
    search_papers_scopus,
    get_paper_details_scopus,
    get_author_profile_scopus
)

@pytest.fixture(autouse=True)
def mock_env():
    os.environ["SCOPUS_API_KEY"] = "fake_key"

@pytest.mark.asyncio
@respx.mock
async def test_search_papers_scopus():
    mock_data = {
        "search-results": {
            "entry": [
                {
                    "dc:identifier": "SCOPUS_ID:123",
                    "dc:title": "Scopus Mock Paper",
                    "dc:creator": "Creator Name",
                    "prism:publicationName": "Mock Journal",
                    "prism:coverDate": "2024-01-01",
                    "prism:doi": "10.1234/scopus.1",
                    "prism:url": "https://api.elsevier.com/123",
                    "dc:description": "Abstract snippet"
                }
            ]
        }
    }
    respx.get("https://api.elsevier.com/content/search/scopus").mock(return_value=httpx.Response(200, json=mock_data))

    results = await search_papers_scopus("mock query", limit=1)
    
    assert len(results) == 1
    assert results[0]["title"] == "Scopus Mock Paper"
    assert results[0]["authors"] == "Creator Name"

@pytest.mark.asyncio
@respx.mock
async def test_get_paper_details_scopus():
    mock_data = {
        "abstracts-retrieval-response": {
            "coredata": {
                "dc:title": "Detailed Scopus Paper",
                "dc:description": "Full abstract here.",
                "prism:doi": "10.1234/scopus.detail",
                "openaccessFlag": "1",
                "dc:identifier": "SCOPUS_ID:456",
                "prism:publicationName": "Full Journal",
                "prism:coverDate": "2024-02-02",
                "link": [{"@ref": "full-text", "@href": "https://example.com/fulltext"}]
            },
            "authors": {
                "author": [{"ce:indexed-name": "Author, X."}]
            }
        }
    }
    respx.get(url__startswith="https://api.elsevier.com/content/abstract/scopus_id/").mock(return_value=httpx.Response(200, json=mock_data))

    result = await get_paper_details_scopus("SCOPUS_ID:456")
    
    assert "error" not in result
    assert result["title"] == "Detailed Scopus Paper"
    assert result["abstract"] == "Full abstract here."
    assert result["authors"] == ["Author, X."]

@pytest.mark.asyncio
@respx.mock
async def test_get_author_profile_scopus():
    mock_data = {
        "author-retrieval-response": [
            {
                "coredata": {
                    "dc:identifier": "AUTHOR_ID:789",
                    "document-count": "50",
                    "cited-by-count": "1000",
                    "citation-count": "1200"
                },
                "author-profile": {
                    "preferred-name": {"given-name": "John", "surname": "Doe"},
                    "affiliation-current": {
                        "affiliation": {"ip-doc": {"afdispname": "Mock University"}}
                    }
                },
                "h-index": "25"
            }
        ]
    }
    respx.get(url__startswith="https://api.elsevier.com/content/author/author_id/").mock(return_value=httpx.Response(200, json=mock_data))

    result = await get_author_profile_scopus("789")
    
    assert "error" not in result
    assert result["name"] == "John Doe"
    assert result["h_index"] == "25"
    assert result["current_affiliation"] == "Mock University"
