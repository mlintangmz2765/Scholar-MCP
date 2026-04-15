import pytest
import respx
import httpx
from api import (
    search_papers_openalex, 
    batch_get_papers_openalex, 
    search_topics_openalex, 
    search_author_by_orcid_openalex
)

@pytest.mark.asyncio
@respx.mock
async def test_search_papers_openalex():
    # Mock response for search_papers_openalex
    mock_data = {
        "results": [
            {
                "id": "https://openalex.org/W123",
                "title": "Mock Paper",
                "authorships": [{"author": {"display_name": "Author One"}}],
                "publication_year": 2024,
                "biblio": {"volume": "1", "issue": "2", "first_page": "10", "last_page": "20"},
                "doi": "https://doi.org/10.1000/123",
                "open_access": {"is_oa": True, "oa_url": "https://example.com/pdf"},
                "abstract_inverted_index": {"The": [0], "mock": [1], "abstract": [2]}
            }
        ]
    }
    respx.get("https://api.openalex.org/works").mock(return_value=httpx.Response(200, json=mock_data))

    results = await search_papers_openalex("mock query", limit=1)
    
    assert len(results) == 1
    assert results[0]["title"] == "Mock Paper"
    assert results[0]["authors"] == ["Author One"]
    assert results[0]["year"] == 2024
    assert results[0]["doi"] == "https://doi.org/10.1000/123"

@pytest.mark.asyncio
@respx.mock
async def test_batch_get_papers_openalex():
    # Mock response for batch lookup
    mock_data = {
        "results": [
            {
                "id": "https://openalex.org/W123",
                "title": "Batch Paper 1",
                "authorships": [{"author": {"display_name": "Author A"}}],
                "publication_year": 2023,
                "doi": "https://doi.org/10.1000/1",
                "open_access": {"is_oa": True, "oa_url": "https://example.com/1.pdf"}
            }
        ]
    }
    respx.get("https://api.openalex.org/works").mock(return_value=httpx.Response(200, json=mock_data))

    dois = ["10.1000/1"]
    results = await batch_get_papers_openalex(dois)
    
    assert len(results) == 1
    assert results[0]["title"] == "Batch Paper 1"
    assert results[0]["authors"] == ["Author A"]

@pytest.mark.asyncio
@respx.mock
async def test_search_topics_openalex():
    # Mock response for search_topics_openalex
    mock_data = {
        "results": [
            {
                "id": "https://openalex.org/T1",
                "display_name": "Mock Topic",
                "subfield": {"display_name": "Subfield X"},
                "field": {"display_name": "Field Y"},
                "domain": {"display_name": "Domain Z"},
                "works_count": 100,
                "cited_by_count": 500,
                "description": "A mock topic description"
            }
        ]
    }
    respx.get("https://api.openalex.org/topics").mock(return_value=httpx.Response(200, json=mock_data))

    results = await search_topics_openalex("mock topic")
    
    assert len(results) == 1
    assert results[0]["display_name"] == "Mock Topic"
    assert results[0]["subfield"] == "Subfield X"

@pytest.mark.asyncio
@respx.mock
async def test_search_author_by_orcid_openalex():
    # Mock response for author by ORCID
    mock_data = {
        "results": [
            {
                "id": "https://openalex.org/A1",
                "display_name": "Mock Author",
                "orcid": "https://orcid.org/0000-0000-0000-0000",
                "works_count": 10,
                "cited_by_count": 100,
                "summary_stats": {"h_index": 5, "i10_index": 2},
                "last_known_institutions": [{"display_name": "Mock Uni"}],
                "x_concepts": [{"display_name": "Concept 1"}]
            }
        ]
    }
    respx.get("https://api.openalex.org/authors").mock(return_value=httpx.Response(200, json=mock_data))

    result = await search_author_by_orcid_openalex("0000-0000-0000-0000")
    
    assert "error" not in result
    assert result["display_name"] == "Mock Author"
    assert result["h_index"] == 5
    assert result["last_institution"] == "Mock Uni"
