# InstaInstru MCP Admin Copilot Server
*Comprehensive Reference Document*
*Last Updated: January 28, 2026*

## 🎯 Overview

The MCP Admin Copilot is an AI-powered admin interface for InstaInstru, enabling natural language operations through LLM clients like ChatGPT, Claude Desktop, and MCP Inspector.

**What it does:** Allows administrators to query instructor data, analyze search patterns, send invitations, and monitor the founding instructor program—all through conversational AI.

| Property | Value |
|----------|-------|
| **Production URL** | https://mcp.instainstru.com |
| **Protocol** | Model Context Protocol (MCP) |
| **Transport** | Streamable HTTP with JSON responses |
| **Auth** | OAuth2 M2M (JWT) + static token fallback |
| **Framework** | FastMCP 2.14.3+ |
| **Hosting** | Render (Virginia region) |

---

## 🛠️ Available Tools (10 Total)

### Founding Instructor Management

| Tool | Description | Use Case |
|------|-------------|----------|
| `instainstru_founding_funnel_summary` | Pipeline stages, conversion rates, cap status | "How many founding slots are left?" |
| `instainstru_founding_stuck_instructors` | Find instructors stuck in onboarding | "Who hasn't completed onboarding in 7 days?" |

### Instructor Operations

| Tool | Description | Use Case |
|------|-------------|----------|
| `instainstru_instructors_list` | List with filters (status, category, is_founding) | "Show all founding music instructors" |
| `instainstru_instructors_coverage` | Service coverage by category | "What categories need more instructors?" |
| `instainstru_instructors_detail` | Full profile by ID, email, or name | "Look up sarah.chen@example.com" |

### Search Analytics

| Tool | Description | Use Case |
|------|-------------|----------|
| `instainstru_search_top_queries` | Top queries with conversion rates | "What are students searching for?" |
| `instainstru_search_zero_results` | Queries with no results (supply gaps) | "What services are students looking for that we don't have?" |

### Outreach

| Tool | Description | Use Case |
|------|-------------|----------|
| `instainstru_invites_preview` | Preview invite batch before sending | "Preview sending a founding invite to john@example.com" |
| `instainstru_invites_send` | Send invites after confirmation | "Send that invite" |

### Metrics

| Tool | Description | Use Case |
|------|-------------|----------|
| `instainstru_metrics_describe` | Get definition for a metric name | "What does GMV mean?" |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LLM Client (ChatGPT/Claude)                  │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS + JSON-RPC
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MCP Server (Render)                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ DualAuthMiddleware                                       │   │
│  │ • OAuth 2.0 (WorkOS) for client discovery               │   │
│  │ • Unauthenticated: initialize, tools/list               │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ FastMCP Application                                      │   │
│  │ • transport="streamable-http"                           │   │
│  │ • json_response=True (critical for ChatGPT)             │   │
│  │ • stateless_http=True (load balancer compatible)        │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ M2M Token Manager                                        │   │
│  │ • Fetches JWT from WorkOS (client_credentials grant)    │   │
│  │ • 1-hour tokens, auto-refresh with 60s buffer           │   │
│  │ • Fallback to static service token                       │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ InstaInstruClient (httpx)                               │   │
│  │ • 30s read timeout, 60s for slow endpoints              │   │
│  │ • Bearer token (M2M JWT or static)                      │   │
│  └──────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS + Bearer Token (M2M JWT)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              InstaInstru Backend API                            │
│              (api.instainstru.com)                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Principal-Based Authentication                           │   │
│  │ • Verify JWT via JWKS (1-hour cache)                    │   │
│  │ • Extract ServicePrincipal from claims                  │   │
│  │ • Enforce scopes: mcp:read, mcp:write                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ /api/v1/admin/mcp/* endpoints                           │   │
│  │ • founding/funnel-summary                                │   │
│  │ • instructors/list, coverage, detail                    │   │
│  │ • search/top-queries, zero-results                      │   │
│  │ • invites/preview, send                                 │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Components

| Component | File | Purpose |
|-----------|------|---------|
| **Server** | `server.py` | FastMCP app, middleware, health check |
| **Auth Middleware** | `server.py` | DualAuthMiddleware for OAuth + Bearer |
| **M2M Token** | `client.py` | WorkOS M2M JWT fetching and caching |
| **API Client** | `client.py` | httpx client for backend calls |
| **Tools** | `tools/*.py` | MCP tool definitions |
| **Config** | `config.py` | pydantic-settings with env vars |

---

## 🔐 Authentication

### Two-Layer Auth Architecture

The MCP system has two authentication layers:

| Layer | Purpose | Method |
|-------|---------|--------|
| **Client → MCP Server** | Verify LLM client identity | OAuth 2.0 (ChatGPT) or Bearer token |
| **MCP Server → Backend** | Service-to-service auth | OAuth2 M2M JWT (WorkOS) |

### OAuth2 M2M Flow (Server → Backend)

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  MCP Server     │     │  WorkOS         │     │  Backend API    │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         │ POST /oauth2/token    │                       │
         │ (client_credentials)  │                       │
         │──────────────────────>│                       │
         │                       │                       │
         │ JWT (1-hour expiry)   │                       │
         │<──────────────────────│                       │
         │                       │                       │
         │                       │ GET /admin/mcp/*      │
         │                       │ Authorization: Bearer │
         │                       │──────────────────────>│
         │                       │                       │
         │                       │                       │ Verify JWT (JWKS)
         │                       │                       │ Extract Principal
         │                       │                       │ Check Scopes
         │                       │                       │
         │                       │        200 OK         │
         │                       │<──────────────────────│
```

### Principal-Based Authorization (Backend)

The backend uses a Principal abstraction to handle both human and service actors:

```python
@runtime_checkable
class Principal(Protocol):
    @property
    def id(self) -> str: ...        # For audit trails
    @property
    def identifier(self) -> str: ... # Email or client_id
    @property
    def principal_type(self) -> Literal["user", "service"]: ...
```

| Principal Type | Source | Example ID |
|----------------|--------|------------|
| **UserPrincipal** | Database User | `01KFVQBM6GTBKGMZVRYCWHJTMV` |
| **ServicePrincipal** | M2M JWT claims | `client_01KG195317CE131WXZRSWP93S9` |

### Scope Enforcement

| Scope | Operations | Endpoints |
|-------|------------|-----------|
| `mcp:read` | List, get, search | `GET /instructors`, `GET /search/*` |
| `mcp:write` | Create, send | `POST /invites/preview`, `POST /invites/send` |

### Unauthenticated Methods (Required for ChatGPT)

These methods must work without authentication:
- `initialize`
- `notifications/initialized`
- `tools/list`

This is ChatGPT's "mixed-auth" pattern—discover tools first, authenticate when invoking.

---

## ⚙️ Configuration

### MCP Server Environment Variables

```bash
# Backend API
INSTAINSTRU_MCP_API_BASE_URL=https://api.instainstru.com
INSTAINSTRU_MCP_API_SERVICE_TOKEN=<static-token-fallback>

# OAuth2 M2M (WorkOS)
INSTAINSTRU_MCP_WORKOS_M2M_CLIENT_ID=client_01KG195317CE131WXZRSWP93S9
INSTAINSTRU_MCP_WORKOS_M2M_CLIENT_SECRET=<secret>
INSTAINSTRU_MCP_WORKOS_M2M_TOKEN_URL=https://savvy-stone-81-staging.authkit.app/oauth2/token
INSTAINSTRU_MCP_WORKOS_M2M_AUDIENCE=https://api.instainstru.com

# OAuth for client discovery (ChatGPT)
INSTAINSTRU_MCP_WORKOS_CLIENT_ID=client_01KFVQBM6GTBKGMZVRYCWHJTMV
INSTAINSTRU_MCP_WORKOS_DOMAIN=savvy-stone-81-staging.authkit.app
```

### Backend Environment Variables

```bash
# JWT Verification
WORKOS_JWKS_URL=https://api.workos.com/sso/jwks/client_01KFVQBM6GTBKGMZVRYCWHJTMV
WORKOS_M2M_AUDIENCE=client_01KFVQBM6GTBKGMZVRYCWHJTMV
WORKOS_ISSUER=https://savvy-stone-81-staging.authkit.app

# Static token fallback
MCP_SERVICE_TOKEN=<same-as-mcp-server>
```

### Key Discovery: WorkOS Token Endpoint

The correct WorkOS M2M token endpoint is:
- ❌ `https://api.workos.com/oauth/token`
- ❌ `https://xxx.authkit.app/oauth/token`
- ✅ `https://xxx.authkit.app/oauth2/token` (note the `2`)

### FastMCP Configuration

```python
mcp.http_app(
    path="/mcp",
    transport="streamable-http",
    stateless_http=True,      # Required for load balancing
    json_response=True,       # Critical for ChatGPT!
)
```

---

## 🖥️ Client Setup

### ChatGPT

1. Go to ChatGPT → Settings → Connected Apps
2. Add MCP server: `https://mcp.instainstru.com/mcp`
3. Authenticate with WorkOS when prompted
4. Tools appear in the tool picker

### Claude Desktop

Add to `~/.config/claude/mcp.json`:

```json
{
  "mcpServers": {
    "instainstru": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://mcp.instainstru.com/mcp"],
      "env": {
        "BEARER_TOKEN": "<your-service-token>"
      }
    }
  }
}
```

### MCP Inspector

```bash
npx @anthropic-ai/mcp-inspector https://mcp.instainstru.com/mcp
```

---

## 🚦 Client Compatibility

| Client | Transport | Auth | Status | Notes |
|--------|-----------|------|--------|-------|
| **ChatGPT** | Streamable HTTP | OAuth 2.0 | ✅ Working | All 10 tools operational, read + write verified |
| **Claude Desktop** | SSE | Bearer Token | ⚠️ Blocked | Anthropic OAuth bug [#5](https://github.com/anthropics/claude-ai-mcp/issues/5) |
| **Claude.ai Web** | SSE | OAuth 2.0 | ⚠️ Blocked | Same Anthropic bug - OAuth discovery works, flow never completes |
| **MCP Inspector** | Both | Both | ✅ Working | Testing tool |
| **Cursor IDE** | Both | Various | 🔶 Untested | Should work |

### Claude OAuth Bug Details

**Issue:** [anthropics/claude-ai-mcp#5](https://github.com/anthropics/claude-ai-mcp/issues/5)

Claude clients discover OAuth metadata successfully but never complete the flow:
```
POST /mcp → 406 (triggers OAuth discovery) ✅
GET /.well-known/oauth-protected-resource → 200 ✅
... flow stops here, never completes ❌
```

**Not our issue:** WorkOS supports all token auth methods (`none`, `client_secret_basic`, `client_secret_post`), so the DCR-related bug mentioned in updates doesn't apply.

**Workaround:** Use ChatGPT for MCP admin operations until Anthropic fixes this.

---

## 📊 Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/mcp` | POST | Main MCP endpoint |
| `/api/v1/health` | GET | Health check for Render |
| `/.well-known/oauth-protected-resource` | GET | OAuth discovery |
| `/.well-known/oauth-authorization-server` | GET | OAuth metadata (proxied) |
| `/oauth2/register` | POST | Dynamic client registration (proxied) |
| `/oauth2/token` | POST | Token exchange (proxied) |
| `/oauth2/userinfo` | GET | User profile (proxied) |

---

## 🔧 Performance Optimizations

### Auth Caching (MCP Server)

```python
# 55-second TTL, hash-based keys
# Prevents CPU spikes from repeated JWT validation
AUTH_CACHE_TTL = 55
AUTH_CACHE_MAX_SIZE = 1000
```

### JWKS Caching (Backend)

```python
# 1-hour TTL for WorkOS JWKS
# Async fetching to avoid blocking
JWKS_CACHE_TTL = 3600
```

### M2M Token Caching (MCP Server)

```python
# Token cached until expiry - 60 seconds buffer
# Avoids token fetch on every request
token_expiry = datetime.now() + timedelta(seconds=expires_in - 60)
```

### Backend Timeouts

```python
httpx.Timeout(
    connect=10.0,
    read=30.0,      # Default read timeout
    write=10.0,
    pool=10.0,
)

# Slow endpoints get 60s
await self.call(..., timeout=60.0)
```

---

## 🔒 Security Features

| Feature | Implementation |
|---------|----------------|
| **JWT Validation** | JWKS-based with 1-hour cache |
| **Timing-Safe Comparison** | `secrets.compare_digest()` for static tokens |
| **Scope Enforcement** | Route-level `mcp:read` / `mcp:write` |
| **Audit Trail** | Principal type + ID in all audit logs |
| **Short-Lived Tokens** | M2M JWTs expire in 1 hour |
| **Dual Auth Support** | M2M JWT + static token fallback |

### Structured Logging

```python
# Auth events logged with context
mcp_auth_m2m_jwt       # M2M token validated
mcp_auth_static_token  # Static token used (fallback)
mcp_auth_failed        # Auth failed
mcp_scope_insufficient # Scope check failed
```

---

## 🧪 Testing

### Test File

`mcp-server/tests/test_auth_middleware.py` - 45+ tests

### Key Test Cases

| Test | Purpose |
|------|---------|
| `test_mcp_initialize_succeeds` | JSON response, no hang |
| `test_mcp_slash_no_redirect` | /mcp/ works without 307 |
| `test_mcp_mcp_returns_404` | No double-mount regression |
| `test_delete_mcp_passthrough` | DELETE method for session termination |
| `test_userinfo_*` | Email extraction from WorkOS |

### Backend Auth Tests

| File | Purpose |
|------|---------|
| `test_principal.py` | Principal protocol tests |
| `test_mcp_auth.py` | MCP auth dependency tests |
| `test_m2m_auth.py` | JWT verification tests |

### Running Tests

```bash
cd mcp-server
pytest tests/ -v
```

---

## 🚀 Deployment

### Render Service

| Property | Value |
|----------|-------|
| **Service ID** | srv-d5qp5lmr433s7387el9g |
| **URL** | https://mcp.instainstru.com |
| **Plan** | Starter |
| **Region** | Virginia |
| **Health Check** | `/api/v1/health` |

### Deploy Command

```bash
# Included in render_deploy_api.sh
render deploy srv-d5qp5lmr433s7387el9g
```

---

## 📝 Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| **OAuth2 M2M over static tokens** | Short-lived JWTs, automatic rotation, scope enforcement |
| **Principal abstraction** | Decouples auth from User model, enables service actors |
| **Streamable HTTP over SSE** | SSE deprecated by MCP project; better proxy compatibility |
| **json_response=True** | ChatGPT hangs on SSE streaming for tool listing |
| **stateless_http=True** | Required for load balancing; no sticky sessions |
| **WorkOS for M2M** | Same provider as user auth; JWKS validation |
| **Proxy OAuth endpoints** | Browser CORS prevents direct cross-origin calls |
| **Mixed auth pattern** | ChatGPT requires unauthenticated discovery |
| **55s auth cache** | Prevents CPU spikes from JWT validation |
| **audit_log.actor_id VARCHAR(64)** | M2M client IDs are 32 chars (vs 26-char ULIDs) |

---

## 🐛 Troubleshooting

### "ReadTimeout" on tool calls

**Cause:** Backend API slow to respond
**Fix:** Increase timeout in `client.py` or add per-request override

### 32-second hang on tools/list

**Cause:** SSE streaming + ChatGPT don't mix
**Fix:** `json_response=True` in FastMCP config

### 100% CPU on tool refresh

**Cause:** JWT validation on every request
**Fix:** Auth cache with 55s TTL

### "Session not found"

**Cause:** UUID format mismatch
**Fix:** Normalize session_id (ChatGPT sends without dashes)

### OAuth flow works but 401 on tool call

**Cause:** Email not in allowlist or scope mismatch
**Fix:** Check userinfo endpoint returns valid email, verify scopes

### "value too long for type character varying(26)"

**Cause:** M2M client IDs are 32 chars, audit_log.actor_id was VARCHAR(26)
**Fix:** Expand column to VARCHAR(64)

### Claude OAuth discovery succeeds but tools return "Insufficient permissions"

**Cause:** Anthropic OAuth bug [#5](https://github.com/anthropics/claude-ai-mcp/issues/5)
**Fix:** Use ChatGPT until Anthropic fixes it

---

## 📈 Production Data (as of Jan 28, 2026)

```
Founding Cap: 100 slots, 0 used, 100 remaining
Live Instructors: 65 total
Service Coverage:
  - Arts: 12
  - Language: 11
  - Music: 11
  - Tutoring: 11
  - Hidden Gems: 10
  - Sports & Fitness: 10
```

---

## 🎯 Status & Next Steps

### Completed ✅
- MCP server deployed to production
- OAuth2 M2M authentication (WorkOS)
- Principal-based authorization
- Scope enforcement (mcp:read, mcp:write)
- ChatGPT integration fully working (read + write)
- All 10 tools operational
- Auth caching for performance
- Timeout handling for reliability
- audit_log schema fix for M2M client IDs

### Known Issues ⚠️
- Claude Desktop/Web blocked by Anthropic OAuth bug
- Awaiting fix from Anthropic team

### Future Enhancements

#### Infrastructure Monitoring Tools
| Tool Category | Use Cases |
|---------------|-----------|
| **Celery/Flower** | "What tasks are running?", "Any failed tasks?", "Show queue depth" |
| **Prometheus** | "What's our API latency?", "Show error rate last hour" |
| **Grafana** | "Get dashboard snapshot", "Show slow queries panel" |
| **Alertmanager** | "Any firing alerts?", "Silence the disk space alert" |

#### Admin Operations Tools
| Tool Category | Use Cases |
|---------------|-----------|
| **Booking Management** | "Show today's bookings", "Find cancelled lessons" |
| **Payment Insights** | "Show pending payouts", "Revenue this week" |
| **User Support** | "Look up user by phone", "Check booking history" |

#### Platform Improvements
- Rate limiting for MCP endpoints
- Metrics dashboard for tool usage
- Preview environment MCP service
- Remove static token fallback once M2M stable

---

## 📚 Related Files

```
mcp-server/
├── src/instainstru_mcp/
│   ├── server.py          # Main server, middleware
│   ├── client.py          # Backend API client, M2M token manager
│   ├── config.py          # Environment config
│   └── tools/
│       ├── founding.py    # Founding instructor tools
│       ├── instructors.py # Instructor tools
│       ├── search.py      # Search analytics tools
│       ├── invites.py     # Outreach tools
│       └── metrics.py     # Metrics tools
├── tests/
│   └── test_auth_middleware.py
├── pyproject.toml
└── render.yaml

backend/app/
├── auth/
│   └── principal.py       # Principal protocol and implementations
├── dependencies/
│   └── mcp_auth.py        # get_mcp_principal, require_mcp_scope
├── m2m_auth.py            # JWT verification via JWKS
└── routes/v1/admin/mcp/   # MCP admin endpoints
```

---

*MCP Admin Copilot Server - OAuth2 M2M Production Ready 🚀*

**STATUS:** ChatGPT fully operational. Claude blocked by Anthropic bug.
