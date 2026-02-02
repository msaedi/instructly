# InstaInstru Daily Operations Checklist

## Quick Health Check (2 minutes)

### 1. Services Status
Ask MCP: "Are all services up?"
- Expected: API, worker, beat, MCP all showing traces in Axiom

### 2. Celery Health
Ask MCP: "What's the Celery worker status?"
- Expected: Workers online > 0, queue depth < 100

### 3. Payment Pipeline
Ask MCP: "What's the payment health?"
- Expected: No stuck authorizations more than 48 hours old

### 4. Error Check
Ask MCP: "What are the top Sentry issues today?"
- Expected: No new critical issues

### 5. Axiom Traces
Check Axiom dashboard or ask: "What's the trace volume?"
- Expected: ~400 spans/min, 0 errors

## Full Daily Review (10 minutes)

### Business Metrics
- "What's today's booking summary?"
- "Any pending instructor payouts?"

### Performance
- "What's the p99 latency?"
- "What are the slowest endpoints?"

### Incidents
- Review any Sentry issues from the last 24 hours
- Check if any alerts fired

## Weekly Deep Dive

### Search Analytics
- "What are the top search queries this week?"
- "Any zero-result searches?"

### Instructor Funnel
- "What's the founding funnel status?"
- "Any stuck instructors in onboarding?"
