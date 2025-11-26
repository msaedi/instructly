from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import pytest
import requests

ARTIFACT_DIR = Path(__file__).resolve().parents[2] / ".artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = os.getenv("PREVIEW_API_BASE", "https://preview-api.instainstru.com").rstrip("/")
FRONT_ORIGIN = os.getenv("PREVIEW_FRONT_ORIGIN", "https://preview.instainstru.com").rstrip("/")
INSTRUCTOR_EMAIL = os.getenv("PREVIEW_INSTRUCTOR_EMAIL", "sarah.chen@example.com")
INSTRUCTOR_PASSWORD = os.getenv("PREVIEW_INSTRUCTOR_PASSWORD", "Test1234")

PROBE_SPECS = [
    {"label": "instructors_me", "path": "/instructors/me"},
    {"label": "addresses_me", "path": "/api/v1/addresses/me"},
    {"label": "referrals_me", "path": "/api/v1/referrals/me"},
    {"label": "payments_connect_status", "path": "/api/v1/payments/connect/status"},
    {
        "label": "availability_week",
        "path": "/instructors/availability/week",
        "params": {"start_date": "2025-11-10"},
    },
    {
        "label": "bookings_status_completed_lower",
        "path": "/api/v1/bookings",
        "params": {"status": "completed"},
    },
    {
        "label": "bookings_status_COMPLETED_upper",
        "path": "/api/v1/bookings",
        "params": {"status": "COMPLETED"},
    },
]


@pytest.fixture(scope="module")
def session_and_token() -> tuple[requests.Session, str]:
    session = requests.Session()
    login_payload = {
        "email": INSTRUCTOR_EMAIL,
        "password": INSTRUCTOR_PASSWORD,
        "guest_session_id": "auth-matrix",
    }
    headers = {"Origin": FRONT_ORIGIN, "Content-Type": "application/json"}
    resp = session.post(
        f"{API_BASE}/auth/login-with-session",
        headers=headers,
        json=login_payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token")
    assert token, "Expected access_token in login response"
    return session, token


def _summarize_response(resp: requests.Response) -> Dict[str, object]:
    summary: Dict[str, object] = {"status": resp.status_code}
    try:
        body = resp.json()
    except ValueError:
        body = resp.text[:200]
    summary["body"] = body
    return summary


def _probe(
    session: requests.Session,
    token: str,
    path: str,
    params: Optional[Dict[str, str]] = None,
    use_bearer: bool = False,
) -> Dict[str, object]:
    url = f"{API_BASE}{path}"
    headers = {"Origin": FRONT_ORIGIN}
    if use_bearer:
        headers["Authorization"] = f"Bearer {token}"
    resp = session.get(url, params=params, headers=headers, timeout=30)
    return _summarize_response(resp)


def test_auth_surface_matrix(session_and_token: tuple[requests.Session, str]) -> None:
    session, token = session_and_token
    matrix: List[Dict[str, object]] = []

    for spec in PROBE_SPECS:
        entry: Dict[str, object] = {
            "label": spec["label"],
            "path": spec["path"],
            "params": spec.get("params") or {},
        }
        entry["cookie"] = _probe(session, token, spec["path"], spec.get("params"), use_bearer=False)
        entry["bearer"] = _probe(session, token, spec["path"], spec.get("params"), use_bearer=True)
        matrix.append(entry)

    json_path = ARTIFACT_DIR / "auth_matrix.json"
    with json_path.open("w", encoding="utf-8") as jf:
        json.dump({"results": matrix}, jf, indent=2)

    md_path = ARTIFACT_DIR / "AUTH_MATRIX.md"
    with md_path.open("w", encoding="utf-8") as md:
        md.write("# Auth Surface Probe Matrix\n\n")
        md.write("| Label | Path | Params | Cookie Status | Bearer Status |\n")
        md.write("| --- | --- | --- | --- | --- |\n")
        for entry in matrix:
            params_repr = ", ".join(f"{k}={v}" for k, v in entry["params"].items()) or "-"
            cookie_status = entry["cookie"]["status"]
            bearer_status = entry["bearer"]["status"]
            md.write(
                f"| {entry['label']} | `{entry['path']}` | {params_repr} | {cookie_status} | {bearer_status} |\n"
            )

    assert len(matrix) == len(PROBE_SPECS)
