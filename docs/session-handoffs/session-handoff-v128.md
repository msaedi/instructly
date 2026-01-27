# InstaInstru MCP Admin Copilot Server
*Complete Implementation Guide*
*Last Updated: January 27, 2026*

## 🎯 Overview

The MCP Admin Copilot is an AI-powered admin interface for InstaInstru, enabling natural language operations through LLM clients like ChatGPT, Claude Desktop, and MCP Inspector.

| Component | Value |
|-----------|-------|
| **Production URL** | https://mcp.instainstru.com |
| **Transport** | streamable-http (with json_response) |
| **Auth** | OAuth 2.0 (WorkOS AuthKit) |
| **Tools** | 10 admin operations |
| **Framework** | FastMCP 2.14.3+ |

---

## 🏗️ Architecture

```
┌─────────────────────┐     ┌──────────────────────┐
│   LLM Client        │     │   InstaInstru API    │
│  (ChatGPT/Claude)   │     │  api.instainstru.com │
└─────────┬───────────┘     └──────────┬───────────┘
          │                            │
          │ MCP Protocol               │ REST API
          │ (streamable-http)          │ (Bearer Token)
          ▼                            ▼
┌─────────────────────────────────────────────────┐
│           MCP Server (FastMCP)                   │
│           mcp.instainstru.com                    │
├─────────────────────────────────────────────────┤
│  /mcp          - MCP protocol endpoint           │
│  /oauth2/*     - OAuth proxy to WorkOS           │
│  /.well-known/* - OAuth discovery metadata       │
│  /api/v1/health - Health check                   │
└─────────────────────────────────────────────────┘
```

---

## 🔧 10 Admin Tools

### Founding Instructor Management

| Tool | Description |
|------|-------------|
| `instainstru_founding_funnel_summary` | Pipeline stages, conversion rates, founding cap status (0/100 used) |
| `instainstru_founding_stuck_instructors` | Find instructors stuck in onboarding by stage/days |

### Instructor Operations

| Tool | Description |
|------|-------------|
| `instainstru_instructors_list` | List with filters (status, category, service, is_founding) |
| `instainstru_instructors_coverage` | Service coverage grouped by category/service |
| `instainstru_instructors_detail` | Full profile by ID, email, or name |

### Search Analytics

| Tool | Description |
|------|-------------|
| `instainstru_search_top_queries` | Top queries with count, avg results, conversion rate |
| `instainstru_search_zero_results` | Queries returning no results (supply gap analysis) |

### Outreach

| Tool | Description |
|------|-------------|
| `instainstru_invites_preview` | Preview invite batch with founding status grant option |
| `instainstru_invites_send` | Send invites after confirming preview token |

### Metrics

| Tool | Description |
|------|-------------|
| `instainstru_metrics_describe` | Get definition for a specific metric name |

---

## 🔐 Authentication

### OAuth 2.0 Flow (for LLM Clients)

```
1. Client → GET /.well-known/oauth-protected-resource
   ← Returns authorization_servers: ["https://mcp.instainstru.com"]

2. Client → GET /.well-known/oauth-authorization-server
   ← Returns rewritten metadata with proxied endpoints

3. Client → POST /oauth2/register (proxied to WorkOS)
   ← Dynamic client registration

4. User redirected to WorkOS login
   ← Authenticates with email

5. Client → POST /oauth2/token (proxied to WorkOS)
   ← Token exchange

6. Client → POST /mcp with Bearer token
   ← Server validates JWT + checks email allowlist
```

### Email Allowlist

Access restricted to:
- `admin@instainstru.com`
- `faeze@instainstru.com`
- `mehdi@instainstru.com`

### Backend API Authentication

The MCP server authenticates to the InstaInstru API using a service token:
```
Authorization: Bearer <INSTAINSTRU_MCP_API_SERVICE_TOKEN>
```

---

## 🚦 LLM Client Compatibility

| Client | Transport | Auth | Status |
|--------|-----------|------|--------|
| **ChatGPT** | streamable-http | OAuth 2.0 | ✅ Working |
| **Claude Desktop** | SSE | Bearer Token | ✅ Working |
| **MCP Inspector** | SSE/HTTP | OAuth/Bearer | ✅ Working |
| **Claude.ai Web** | SSE | OAuth 2.0 | ❌ Bug (gets token, never uses it) |

### ChatGPT Configuration

In ChatGPT (chatgpt.com):
1. Settings → MCP Servers → Add Server
2. URL: `https://mcp.instainstru.com/mcp`
3. Complete OAuth flow when prompted
4. 10 tools appear, ready to use

### Claude Desktop Configuration

In `~/.claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "instainstru": {
      "url": "https://mcp.instainstru.com/sse",
      "headers": {
        "Authorization": "Bearer <your-token>"
      }
    }
  }
}
```

---

## ⚙️ Technical Implementation

### FastMCP Configuration

```python
mcp = FastMCP("InstaInstru Admin")

app_instance = mcp.http_app(
    transport="streamable-http",
    stateless_http=True,      # Required for horizontal scaling
    json_response=True,       # Critical: prevents SSE streaming hangs
    path="/mcp",              # Explicit path
)
```

### Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| `json_response=True` | ChatGPT hangs on SSE-style streaming responses |
| `stateless_http=True` | Enables horizontal scaling, no session affinity |
| OAuth proxy endpoints | Browsers block cross-origin POSTs to WorkOS |
| 30s default timeout | Backend API calls can be slow |
| 60s timeout for invites | Email sending is particularly slow |
| Mixed auth pattern | Unauthenticated discovery, OAuth for tool execution |

### Backend Client (httpx)

```python
self.http = httpx.AsyncClient(
    base_url=settings.api_base_url,
    timeout=httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0,
    ),
)
```

### JWT Validation with Caching

- JWKS fetched from WorkOS with 1-hour cache
- Auth results cached 55s with hash-based key
- Max 1000 cached entries

---

## 🌐 Deployment

### Render Service

| Property | Value |
|----------|-------|
| **Service Name** | instainstru-mcp |
| **Service ID** | srv-d5qp5lmr433s7387el9g |
| **Live URL** | https://mcp.instainstru.com |
| **Health Check** | /api/v1/health |
| **Plan** | Starter |

### Environment Variables

```bash
# Backend API
INSTAINSTRU_MCP_API_SERVICE_TOKEN=<service-token>
INSTAINSTRU_MCP_API_BASE_URL=https://api.instainstru.com

# OAuth (WorkOS)
INSTAINSTRU_MCP_WORKOS_CLIENT_ID=client_01KFQCYZ...
INSTAINSTRU_MCP_WORKOS_DOMAIN=savvy-stone-81-staging.authkit.app
INSTAINSTRU_MCP_WORKOS_JWKS_URL=https://api.workos.com/sso/jwks/client_01KFQCYZ...
```

### Files Structure

```
mcp-server/
├── src/instainstru_mcp/
│   ├── server.py          # FastMCP app, OAuth endpoints, auth middleware
│   ├── client.py          # httpx client for backend API
│   ├── endpoints.py       # OAuth proxy implementation
│   ├── settings.py        # pydantic-settings configuration
│   └── tools/
│       ├── founding.py    # Founding instructor tools
│       ├── instructors.py # Instructor management tools
│       ├── search.py      # Search analytics tools
│       ├── invites.py     # Outreach tools
│       └── metrics.py     # Metrics tools
├── tests/
│   └── test_auth_middleware.py  # 43 tests
└── pyproject.toml
```

---

## 🧪 Testing

### Test Coverage

| Area | Tests |
|------|-------|
| Auth middleware | 25+ |
| OAuth flow | 10+ |
| MCP routes | 8+ |
| **Total** | 43+ |

### Key Test Cases

```python
# MCP route behavior
test_mcp_initialize_returns_json()
test_mcp_slash_works_without_redirect()
test_mcp_mcp_returns_404()  # No double-mount
test_delete_mcp_passes_through()

# OAuth flow
test_oauth_register_proxied()
test_oauth_token_proxied()
test_userinfo_fetched_for_email()

# Auth
test_allowlisted_email_granted()
test_non_allowlisted_email_denied()
test_jwt_validation_caches_result()
```

---

## 📊 Production Data (Current)

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

## 🐛 Known Issues & Workarounds

### Claude.ai Web OAuth Bug
- **Issue**: Completes OAuth, gets token, but never sends it with requests
- **Status**: Anthropic bug (GitHub #11814, #3515)
- **Workaround**: Use Claude Desktop with Bearer token instead

### Slow Backend Endpoints
- **Issue**: Some endpoints (invites) take >5s
- **Fix**: 60s timeout override for slow endpoints

---

## 🔮 Future Enhancements

1. **More Tools**
   - Booking management (view, cancel, reschedule)
   - Payment insights (revenue, payouts)
   - Student analytics (signups, retention)

2. **Rate Limiting**
   - Per-user rate limits on tool calls
   - Protect against abuse

3. **Observability**
   - Prometheus metrics for tool calls
   - Error rate tracking
   - Latency percentiles

4. **Multi-Environment**
   - Preview MCP server (preview-mcp.instainstru.com)
   - Staging environment support

---

## 📚 Key Learnings

1. **`json_response=True` is critical** - Without it, FastMCP's streamable-http returns SSE-style responses that never close, causing 32s hangs

2. **OAuth must be proxied** - Browser clients can't POST to different origins (WorkOS)

3. **Mixed auth works** - Unauthenticated tool discovery, OAuth only for execution

4. **Auth caching prevents CPU spikes** - JWT verification is expensive, cache for 55s

5. **Path normalization matters** - ChatGPT clients sensitive to `/mcp` vs `/mcp/` redirects

6. **Timeout per-endpoint** - Some endpoints are genuinely slow, don't fail fast

---

*MCP Admin Copilot Server - Production Ready 🚀*
