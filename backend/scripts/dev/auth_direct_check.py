"""
Simple HTTP smoke check for login-with-session using seeded credentials.
"""
from __future__ import annotations

import os
from pathlib import Path

import requests

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BACKEND_DIR / ".env"


def main() -> int:
    api_base = os.environ.get("PLAYWRIGHT_API_BASE") or os.environ.get("E2E_API_BASE_URL") or "http://localhost:8000"
    email = os.environ.get("E2E_INSTRUCTOR_EMAIL", "sarah.chen@example.com")
    password = os.environ.get("E2E_INSTRUCTOR_PASSWORD", "Test1234")

    if ENV_PATH.exists():
        from dotenv import dotenv_values

        env_values = dotenv_values(ENV_PATH)
        for key, value in env_values.items():
            if key not in os.environ and value is not None:
                os.environ[key] = value

    print(f"🔍 Hitting {api_base}/api/v1/auth/login-with-session for {email} ...")
    try:
        response = requests.post(
            f"{api_base}/api/v1/auth/login-with-session",
            json={"email": email, "password": password},
            timeout=10,
        )
    except Exception as exc:
        print(f"❌ Request failed: {exc}")
        return 1

    if response.status_code != 200:
        print(f"❌ login-with-session failed: {response.status_code} {response.text}")
        return 1

    print("✅ login-with-session OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
