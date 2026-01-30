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

## Available Tools

The MCP server exposes 10 tools for AI agents:

### Founding Instructor Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `instainstru_founding_funnel_summary` | Get founding instructor funnel with stage counts and conversion rates | `start_date?`, `end_date?` |
| `instainstru_founding_stuck_instructors` | Find instructors stuck in onboarding | `stuck_days?` (default: 7), `stage?`, `limit?` (default: 50) |

### Instructor Management Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `instainstru_instructors_list` | List instructors with optional filters | `status?`, `is_founding?`, `service_slug?`, `category_slug?`, `limit?`, `cursor?` |
| `instainstru_instructors_coverage` | Get instructor service coverage data | `status?` (default: "live"), `group_by?` (default: "category"), `top?` (default: 25) |
| `instainstru_instructors_detail` | Get full instructor profile by ID, email, or name | `identifier` (required) |

### Invite Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `instainstru_invites_preview` | Preview sending invites (returns confirm token) | `recipient_emails` (required), `grant_founding_status?`, `expires_in_days?`, `message_note?` |
| `instainstru_invites_send` | Execute invite send after preview confirmation | `confirm_token` (required), `idempotency_key` (required) |

### Search Analytics Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `instainstru_search_top_queries` | Get top search queries with conversion metrics | `start_date?`, `end_date?`, `min_count?` (default: 2), `limit?` (default: 50) |
| `instainstru_search_zero_results` | Get zero-result queries (demand gaps) | `start_date?`, `end_date?`, `limit?` (default: 50) |

### Metrics Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `instainstru_metrics_describe` | Get a metrics dictionary definition | `metric_name` (required) |

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

| Variable | Required | Description |
|----------|----------|-------------|
| `INSTAINSTRU_MCP_API_SERVICE_TOKEN` | Yes | Bearer token for Claude Desktop authentication |
| `INSTAINSTRU_MCP_API_BASE_URL` | Yes | Backend API URL (e.g., `https://api.instainstru.com`) |
| `INSTAINSTRU_MCP_AUTH0_DOMAIN` | No | Auth0 domain for OAuth (e.g., `instainstru-admin.us.auth0.com`) |
| `INSTAINSTRU_MCP_AUTH0_AUDIENCE` | No | Auth0 API audience (e.g., `https://mcp.instainstru.com`) |
| `INSTAINSTRU_MCP_SENTRY_DSN` | No | Sentry DSN for MCP error tracking |
| `INSTAINSTRU_MCP_ENVIRONMENT` | No | Sentry environment name (default: `development`) |

**Note:** For Auth0 OAuth support, both `INSTAINSTRU_MCP_AUTH0_DOMAIN` and `INSTAINSTRU_MCP_AUTH0_AUDIENCE` must be set.

Example `.env`:
```
INSTAINSTRU_MCP_API_BASE_URL=https://api.instainstru.com
INSTAINSTRU_MCP_API_SERVICE_TOKEN=svc_...
```

## Run Locally
```bash
uvicorn instainstru_mcp.server:get_app --factory --host 0.0.0.0 --port 8001
```

## Deployment (Render)
Render start command:
```
uvicorn instainstru_mcp.server:get_app --factory --host 0.0.0.0 --port $PORT
```

Required env vars in Render:
- `INSTAINSTRU_MCP_API_BASE_URL`
- `INSTAINSTRU_MCP_API_SERVICE_TOKEN`

Optional Sentry env vars in Render:
- `INSTAINSTRU_MCP_SENTRY_DSN`
- `INSTAINSTRU_MCP_ENVIRONMENT`

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
