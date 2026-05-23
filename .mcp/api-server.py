"""
MCP server — lets Claude Code call app API endpoints directly in conversation.
Run: python .mcp/api-server.py
Set API_BASE_URL in environment to override default (http://localhost:8000).
"""
import os
import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("api")
BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

@mcp.tool()
def health_check() -> str:
    """Check if the backend is running."""
    r = httpx.get(f"{BASE_URL}/health", timeout=5)
    return str(r.json())

@mcp.tool()
def get_endpoint(path: str, token: str = "") -> str:
    """Call a GET endpoint. path must start with /"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    r = httpx.get(f"{BASE_URL}{path}", headers=headers, timeout=10)
    return r.text

@mcp.tool()
def post_endpoint(path: str, body: str, token: str = "") -> str:
    """Call a POST endpoint with a JSON body string."""
    import json
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = httpx.post(f"{BASE_URL}{path}", content=body, headers=headers, timeout=30)
    return r.text

if __name__ == "__main__":
    mcp.run()
