#!/usr/bin/env python3
import sys
from pathlib import Path

import orjson

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Import the FastAPI app instance (use fastapi_app, not the wrapped ASGI app)
from app.main import fastapi_app as app


def strip_docs(obj):
    """Strip non-contract fields to reduce size."""
    STRIP = {"description", "summary", "examples", "example", "externalDocs"}
    if isinstance(obj, dict):
        return {k: strip_docs(v) for k, v in obj.items() if k not in STRIP}
    if isinstance(obj, list):
        return [strip_docs(v) for v in obj]
    return obj


def main():
    # Generate OpenAPI in-process (no running server)
    spec = app.openapi()

    # First: minified deterministic dump
    data = orjson.dumps(spec, option=orjson.OPT_SORT_KEYS)

    if len(data) > 500_000:
        # Fallback: strip doc-only fields and re-dump
        spec = strip_docs(spec)
        data = orjson.dumps(spec, option=orjson.OPT_SORT_KEYS)
        print(f"Stripped docs to reduce size: {len(data)} bytes")

    # Use absolute path based on script location
    script_dir = Path(__file__).parent
    out_path = script_dir.parent / "openapi" / "openapi.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)

    print(f"Wrote {out_path} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
