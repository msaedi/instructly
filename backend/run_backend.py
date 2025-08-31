#!/usr/bin/env python3
# backend/run.py
"""
Development server runner that uses staging database
For local development only - preserves development data
"""
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

# Default SITE_MODE for local development
os.environ.setdefault("SITE_MODE", "local")

import uvicorn

if __name__ == "__main__":
    print("🚀 Starting development server (SITE_MODE=" + os.getenv("SITE_MODE", "local") + ")…")
    print("📊 This preserves your local development data between test runs")
    print("🌐 Access at: http://localhost:8000")
    print("📚 API Docs: http://localhost:8000/docs")

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
