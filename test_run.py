import asyncio
from server import get_citations_tool, get_full_text_tool


async def main():
    print("Testing get_citations_tool:")
    res = await get_citations_tool(paper_id="10.1038/nature14539", direction="citations")
    print(res[:500] + "...\n")

    print("Testing get_full_text_tool (PyMuPDF):")
    # Using attention is all you need arXiv PDF
    res2 = await get_full_text_tool("https://arxiv.org/pdf/1706.03762.pdf")
    print(res2[:500] + "...")


asyncio.run(main())
