#!/usr/bin/env python3
"""
MCP Server development runner.
For local development only - connects to local backend at localhost:8000.
"""

import os
import sys
from pathlib import Path

# Add mcp-server/src to path
mcp_dir = Path(__file__).parent
sys.path.insert(0, str(mcp_dir / "src"))
os.chdir(mcp_dir)

# Load .env file if it exists (values take priority over defaults)
from dotenv import load_dotenv

env_file = mcp_dir / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"📁 Loaded config from {env_file}")

# Set defaults for local development (only if not in .env)
os.environ.setdefault("INSTAINSTRU_MCP_API_BASE_URL", "http://localhost:8000")
os.environ.setdefault("INSTAINSTRU_MCP_API_SERVICE_TOKEN", "dev_LocalTestToken12345")

import uvicorn

if __name__ == "__main__":
    api_url = os.getenv("INSTAINSTRU_MCP_API_BASE_URL")
    print("🤖 Starting MCP Server for InstaInstru Admin...")
    print(f"🔗 Backend API: {api_url}")
    print("🌐 MCP Server: http://localhost:8001")
    print("📡 SSE Endpoint: http://localhost:8001/sse")
    print("")
    print("💡 Test with MCP Inspector:")
    print("   npx @modelcontextprotocol/inspector http://localhost:8001/sse")
    print("")
    print("⚠️  Make sure backend is running first:")
    print("   cd backend && python run_backend.py")

    uvicorn.run(
        "instainstru_mcp.server:get_app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        reload_dirs=["src"],
        log_level="info",
        factory=True,
    )
