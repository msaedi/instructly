#!/usr/bin/env python3
# backend/run_dev.py
"""
Development server runner that uses test database
For local development only - forces is_testing=True
"""
import os
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)

# Force test database for local development
os.environ["IS_TESTING"] = "true"

import uvicorn

if __name__ == "__main__":
    print("🚀 Starting development server with TEST database...")
    print("📊 This ensures local development doesn't touch production data")
    print("🌐 Access at: http://localhost:8000")
    print("📚 API Docs: http://localhost:8000/docs")

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
