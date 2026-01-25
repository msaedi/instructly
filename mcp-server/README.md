# InstaInstru MCP Server

## Overview
This service exposes InstaInstru admin MCP tools over SSE using FastMCP. It forwards requests to the existing backend `/api/v1/admin/mcp/*` endpoints using a single service token.

## Local Setup
```bash
cd mcp-server
python -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## Quick Start (Local Development)

1. Start the backend first:
```bash
cd backend
python run_backend.py
```

2. In another terminal, start the MCP server:
```bash
cd mcp-server
python run_mcp.py
```

3. Test with MCP Inspector:
```bash
npx @modelcontextprotocol/inspector http://localhost:8001/sse
```

## Environment Variables
All variables are prefixed with `INSTAINSTRU_MCP_`.

- `INSTAINSTRU_MCP_API_BASE_URL` (default: `https://api.instainstru.com`)
- `INSTAINSTRU_MCP_API_SERVICE_TOKEN` (required)

Example `.env`:
```
INSTAINSTRU_MCP_API_BASE_URL=https://api.instainstru.com
INSTAINSTRU_MCP_API_SERVICE_TOKEN=svc_...
```

## Run Locally
```bash
uvicorn instainstru_mcp.server:app --host 0.0.0.0 --port 8001
```

## Deployment (Render)
Render start command:
```
uvicorn instainstru_mcp.server:app --host 0.0.0.0 --port $PORT
```

Required env vars in Render:
- `INSTAINSTRU_MCP_API_BASE_URL`
- `INSTAINSTRU_MCP_API_SERVICE_TOKEN`

## Testing
```bash
pytest tests/ -v
mypy src/
ruff check src/
```

## Example Usage (Claude)
Configure your MCP client with:
- Base URL: `https://mcp.instainstru.com/sse`

Then call tools like:
- `instainstru_founding_funnel_summary`
- `instainstru_instructors_list`
- `instainstru_invites_preview`
```
