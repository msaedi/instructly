#!/usr/bin/env python3
# backend/run_ssl.py
"""
SSL Development Server for InstaInstru Backend
Runs the FastAPI application with HTTPS for local development
"""
import os
import sys
from pathlib import Path

# Suppress the urllib3 LibreSSL warning on macOS
import urllib3

urllib3.disable_warnings(urllib3.exceptions.NotOpenSSLWarning)

# Add the backend directory to Python path and change to it
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))
os.chdir(backend_dir)  # Change to backend directory for uvicorn

import uvicorn

if __name__ == "__main__":
    # Check if certificates exist (now relative to backend dir)
    cert_file = Path("certs/cert.pem")
    key_file = Path("certs/key.pem")

    if not cert_file.exists() or not key_file.exists():
        print("❌ SSL certificates not found!")
        print("Please run: ./setup-local-ssl.sh")
        sys.exit(1)

    print("🔐 Starting InstaInstru API with HTTPS...")
    print("🌐 Access at: https://localhost:8001")  # Changed to 8001
    print("📚 API Docs: https://localhost:8001/docs")
    print("⚠️  HTTP API still available at: http://localhost:8000")

    # Run with SSL on port 8001 to avoid conflict with HTTP on 8000
    uvicorn.run(
        "app.main:app",  # Import string format for reload to work
        host="0.0.0.0",
        port=8001,  # Changed from 8000 to 8001
        ssl_keyfile="certs/key.pem",
        ssl_certfile="certs/cert.pem",
        reload=True,  # Enable hot reload for development
        log_level="info",
    )
