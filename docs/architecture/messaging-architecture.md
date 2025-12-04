# Messaging Architecture (v3.1)

## Overview

Real-time messaging uses Redis Pub/Sub as the single notification source. PostgreSQL remains the system of record and is used for catch-up when clients reconnect.

## Architecture

```
Client (EventSource)
      │
      │  SSE (Redis events + DB catch-up on reconnect)
      ▼
FastAPI backend
  ├─ PostgreSQL (persist + fetch missed messages)
  └─ Redis Pub/Sub (real-time fanout to user channels: user:{user_id})
```

## Message Flow

1) Client sends message via `POST /api/v1/messages/send`
2) Backend saves to PostgreSQL
3) Backend publishes to Redis channel `user:{recipient_id}`
4) SSE stream reads from Redis and forwards to clients
5) Client receives real-time update

## Reconnection (Last-Event-ID)

1) Client disconnects (network/tab sleep).
2) Browser auto-reconnects with `Last-Event-ID` header.
3) Backend queries PostgreSQL for messages after that ID (`fetch_messages_after`).
4) Backend sends catch-up messages, then resumes Redis stream.

## Event Types

| Event            | SSE `id:` | Catch-up | Notes                                   |
|------------------|-----------|----------|-----------------------------------------|
| `new_message`    | ✅ Yes    | ✅ Yes   | Drives Last-Event-ID                     |
| `message_edited` | ❌ No     | ❌ No    | Ephemeral; UI reflects latest state      |
| `reaction_update`| ❌ No     | ❌ No    | Ephemeral; rebuilt from messages if needed |
| `read_receipt`   | ❌ No     | ❌ No    | Ephemeral                                |
| `typing_status`  | ❌ No     | ❌ No    | Ephemeral                                |
| `heartbeat`      | ❌ No     | ❌ No    | Keep-alive (~10s interval)               |
| `connected`      | ❌ No     | ❌ No    | Initial ack                              |

## Key Files

- `backend/app/services/messaging/publisher.py` — Redis publish helpers
- `backend/app/services/messaging/sse_stream.py` — SSE generator + catch-up
- `backend/app/services/messaging/redis_pubsub.py` — Pub/Sub manager
- `backend/app/services/message_service.py` — Business logic entrypoints
- `frontend/hooks/useUserMessageStream.ts` — Client SSE hook

## Configuration

- `REDIS_URL` — Redis connection string
- Heartbeat interval: 10 seconds
- SSE reconnect: automatic via `EventSource` (browser-managed)

## Notes / Capacity

- Single source → no deduplication required.
- DB catch-up ensures missed messages are replayed after reconnect.
- Session pooler / Postgres LISTEN/NOTIFY code has been removed (Phase 3).
- Load testing for higher concurrency is planned; current stack uses a single Redis instance.
