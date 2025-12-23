#!/usr/bin/env python3
# backend/run_backend.py
"""
Development server runner that uses staging database
For local development only - preserves development data
"""
import os
from pathlib import Path
import sys

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

# Default SITE_MODE for local development
os.environ.setdefault("SITE_MODE", "local")

import uvicorn

from app.utils.env_logging import log_info

if __name__ == "__main__":
    site_mode = os.getenv("SITE_MODE", "local").lower()
    if site_mode in {"prod", "production", "live"}:
        env_tag = "prod"
    elif site_mode in {"preview", "pre"}:
        env_tag = "preview"
    elif site_mode in {"stg", "local", "stage", "staging"}:
        env_tag = "stg"
    else:
        env_tag = "int"
    log_info(env_tag, f"Starting development server (SITE_MODE={site_mode})…")
    print("📊 This preserves your local development data between test runs")
    print("🌐 Access at: http://localhost:8000")
    print("📚 API Docs: http://localhost:8000/docs")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_delay=0.5,  # Small delay to batch rapid file changes
        log_level="info",
        timeout_graceful_shutdown=5,  # Force shutdown after 5s instead of hanging
    )
