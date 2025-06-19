import json
import time

import redis
from fastapi import FastAPI

app = FastAPI()
r = redis.from_url("redis://localhost:6379", decode_responses=True)


@app.get("/test-cache-speed")
async def test_cache():
    start = time.time()
    data = r.get("avail:week:208:2025-06-16")
    if data:
        json.loads(data)
        elapsed = (time.time() - start) * 1000
        return {"cached": True, "time_ms": elapsed, "data_size": len(data)}
    return {"cached": False}


# Run with: uvicorn test_cache_speed:app --port 8001
