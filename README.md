# Scholar MCP Server 🎓

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Model Context Protocol](https://img.shields.io/badge/MCP-FastMCP-brightgreen)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A robust **Model Context Protocol (MCP)** server built in Python that empowers AI assistants (like Claude, Gemini, or Cursor) to act as advanced scientific research agents. The server connects directly to the **Scopus API** and **OpenAlex API** to search academic literature, retrieve rich metadata, and securely extract full-text content from Open Access PDFs on-the-fly.

## ✨ Key Features

- **Multi-Source Architecture:** 
  - 🥇 **Scopus API Integration:** Delivers gold-standard metadata (DOIs, exact citations, authoritative abstracts).
  - 🥈 **OpenAlex Fallback:** An open, massive catalog highly optimized for hunting down *Open Access (OA)* PDF URLs.
  - 🥉 **Unpaywall Routing:** Automatically checks DOIs against Unpaywall to discover legal pre-prints and institutional repository PDFs.
- **On-The-Fly PDF & Vision Extraction:** 
  - **Text Extractor:** Automatically downloads OA PDFs into memory and extracts raw text via `pypdf`.
  - **Multimodal Visual Renderer:** Uses `PyMuPDF` to render PDF pages as raw high-res images directly to the AI's Vision Model context (to analyze charts, tables, and layouts).
- **Smart Paywall Awareness:** Proactively detects "Closed Access" papers and dynamically injects "Meta Instructions" instructing the AI to politely ask the human prompt engineer to download the payload via university VPNs manually.
- **FastMCP Built-in:** Utilizes the lightweight standard implementation of the Model Context Protocol for seamless integration via `stdio`.

## 🛠️ Prerequisites

- Python 3.10 or higher
- An Elsevier/Scopus API Key (You can request one [here](https://dev.elsevier.com/)).
- Optional: Scopus Institutional Token (for full abstract retrieval).

## ⚙️ Installation

1. **Clone the Directory:**
   Navigate into the project folder.
   ```bash
   cd scholar_mcp
   ```

2. **Setup the Virtual Environment:**
   Create a virtual environment and install dependencies.
   ```bash
   python -m venv venv
   # On Windows
   venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   
   pip install httpx mcp pypdf beautifulsoup4 python-dotenv
   ```

3. **Configure Environment Variables:**
   Rename or copy `.env.example` to `.env` in the root directory and add your keys securely:
   ```env
   SCOPUS_API_KEY=your_scopus_api_key_here
   SCOPUS_INST_TOKEN=your_institutional_token_here
   ```

## 🚀 Configuration (MCP Clients)

To use this server, you need an MCP-capable client. Provide the client with the absolute path to your Python virtual environment and the main server file (`server.py`).

### Example for `Claude Desktop` / `Gemini CLI`
Add the following to your MCP configuration file (typically `claude_desktop_config.json` or `mcp_config.json`):

```json
{
  "mcpServers": {
    "scholar-mcp": {
      "command": "C:/path/to/scholar_mcp/venv/Scripts/python.exe",
      "args": [
        "C:/path/to/scholar_mcp/server.py"
      ],
      "env": {
        "SCOPUS_API_KEY": "your_scopus_api_key_here"
      }
    }
  }
}
```

*Note: Replace `C:/path/to/` with the actual absolute path to where you stored the repository.*

## 🧰 Available MCP Tools

Once connected, your AI will have access to the following tools:

- `search_papers_tool(query: str, limit: int = 5, use_scopus: bool = True)`
  Returns a list of matching academic papers. Defaults to Scopus, but the AI is instructed to toggle `use_scopus=False` if it specifically hunts for Open Access PDFs.
  
- `get_paper_details_tool(paper_id: str)`
  Retrieves deep metadata, full abstracts, and Open Access statuses for a specific ID. (Smart prompts are baked in).

- `get_full_text_tool(url: str)`
  Takes an Open Access PDF/HTML URL natively found by the search tools, downloads it into memory buffer, and returns the raw unstructured text.

- `get_unpaywall_link_tool(doi: str)`
  Checks the Unpaywall database using a DOI to find a legal Open Access PDF link bypassing strict paywalls.

- `get_full_text_visual_tool(url: str, max_pages: int = 3)`
  Downloads a PDF and renders the specified number of pages as high-resolution images natively to the AI's multimodal vision engine. Used for analyzing complex diagrams, charts, and mathematical templates.

## 📄 License & Usage

This project is licensed under the MIT License. Always ensure your AI tool usage respects the Terms of Service for Semantic Scholar, Elsevier Scopus, and OpenAlex. Excessive automated requests may lead to temporary IP blocks by the publishers. Data harvested should primarily be used for non-commercial research purposes.
