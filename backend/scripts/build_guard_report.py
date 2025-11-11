#!/usr/bin/env python
"""
Generate PATH_AND_GUARD_AUDIT.md based on route inventory and auth matrix artifacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _route_lines(routes: List[Dict[str, Any]]) -> str:
    lines = []
    for route in sorted(routes, key=lambda r: (r["path"], r["methods"])):
        methods = route["methods"]
        deps = route["include_router_dependencies"]
        if route["endpoint_dependencies"]:
            deps = ";".join(
                filter(None, [deps, route["endpoint_dependencies"]])
            )
        tag_str = route["tags"] or "-"
        lines.append(
            f"- `{route['path']}` ({methods}) — tags: {tag_str}; deps: {deps or '-'}"
        )
    return "\n".join(lines) if lines else "_None_"


def main() -> None:
    root = _project_root()
    artifacts_dir = root / "backend" / ".artifacts"
    route_data = _load_json(artifacts_dir / "route_inventory.json")
    auth_matrix = _load_json(artifacts_dir / "auth_matrix.json")["results"]

    api_guarded = [
        r for r in route_data if r.get("is_api") and r.get("has_public_guard")
    ]
    top_level = [r for r in route_data if not r.get("is_api")]
    availability_beta = [
        r
        for r in route_data
        if r["path"].startswith("/instructors/availability")
        and r.get("has_require_beta_access")
    ]

    audit_path = artifacts_dir / "PATH_AND_GUARD_AUDIT.md"
    with audit_path.open("w", encoding="utf-8") as md:
        md.write("# Path & Guard Audit\n\n")
        md.write(
            "Preview routes are split between legacy cookie-authenticated instructor "
            "paths (e.g. `/instructors/*`) and `/api/*` routers that were wrapped with "
            "`public_guard_dependency` in `backend/app/main.py:861-879`. "
            "The guard enforces Authorization headers because preview cookies "
            "(`SameSite=Lax`) are not sent cross-origin, leading to systematic 401s on `/api/*`.\n\n"
        )

        md.write("## Route Groups\n\n")
        md.write("### `/api/*` routes behind `public_guard`\n")
        md.write(_route_lines(api_guarded) + "\n\n")
        md.write("### Top-level routes (no `/api` prefix)\n")
        md.write(_route_lines(top_level) + "\n\n")
        md.write("### Availability routes requiring beta access\n")
        md.write(_route_lines(availability_beta) + "\n\n")

        md.write("## Live Probe Results\n\n")
        md.write("| Label | Path | Params | Cookie Status | Bearer Status | Notes |\n")
        md.write("| --- | --- | --- | --- | --- | --- |\n")
        for entry in auth_matrix:
            params_repr = ", ".join(f"{k}={v}" for k, v in entry["params"].items()) or "-"
            cookie_status = entry["cookie"]["status"]
            bearer_status = entry["bearer"]["status"]
            note = ""
            if cookie_status == 401:
                note = "Rejected by public_guard"
            elif bearer_status == 403 and entry["path"].startswith("/instructors/availability"):
                note = "require_beta_access('instructor')"
            elif entry["label"].startswith("bookings") and cookie_status != bearer_status:
                note = "Case-sensitive status parameter"
            md.write(
                f"| {entry['label']} | `{entry['path']}` | {params_repr} | {cookie_status} | {bearer_status} | {note or '-'} |\n"
            )

        md.write("\n## Recommended Fixes\n\n")
        md.write(
            "1. **Accept preview session cookies on `/api/*`** — Update "
            "`public_guard()` (`backend/app/api/dependencies/authz.py:173-279`) to fall "
            "back to `session_cookie_candidates()` when no Authorization header is present. "
            "Alternatively, remove `Depends(public_guard_dependency)` from the affected "
            "routers in `backend/app/main.py:861-879`.\n"
        )
        md.write(
            "2. **Preserve bearer support for API clients** — continue honoring "
            "Authorization headers so automated clients remain unaffected.\n"
        )
        md.write(
            "3. **Preview availability policy** — either add instructor accounts to the "
            "beta cohort or remove `require_beta_access(\"instructor\")` from "
            "`backend/app/routes/availability_windows.py` (see `/week` endpoints around "
            "lines 161-688) when preview needs parity.\n"
        )
        md.write(
            "4. **Booking status normalization** — frontend should send uppercase values "
            "(`COMPLETED`) or the API should normalize in `backend/app/models/booking.py:44-57`.\n\n"
        )

        md.write("## Verification Checklist\n\n")
        verification_block = """```bash
# after implementing cookie parity
curl -sS -c /tmp/jar -H "Origin: https://preview.instainstru.com" -H "content-type: application/json" \\
  -X POST https://preview-api.instainstru.com/auth/login-with-session \\
  --data '{"email":"sarah.chen@example.com","password":"Test1234","guest_session_id":"audit"}'
curl -sS -b /tmp/jar -H "Origin: https://preview.instainstru.com" https://preview-api.instainstru.com/api/addresses/me
curl -sS -b /tmp/jar -H "Origin: https://preview.instainstru.com" \\
  "https://preview-api.instainstru.com/instructors/availability/week?start_date=2025-11-10"
curl -sS -H "Origin: https://preview.instainstru.com" -H "Authorization: Bearer $ACCESS_TOKEN" \\
  "https://preview-api.instainstru.com/bookings/?status=COMPLETED"
```
"""
        md.write(verification_block)
        md.write(
            "Re-run `pytest backend/tests/integration/test_auth_surface_matrix.py` "
            "to refresh the matrix after applying fixes.\n"
        )


if __name__ == "__main__":
    main()
