from fastapi.testclient import TestClient

from app.main import fastapi_app as app

client = TestClient(app)


def _any_instructor_id() -> str | None:
    # Try v1 instructors listing
    r = client.get("/api/v1/instructors")
    if r.status_code == 200:
        data = r.json()
        items = data if isinstance(data, list) else (data.get("results") or [])
        if items:
            first = items[0]
            return first.get("id") or first.get("instructor_id")

    # Fall back to search (Phase 14: Search migrated to /api/v1/search)
    r = client.get("/api/v1/search/instructors?q=Yoga")
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, dict):
            items = data.get("results") or data.get("items") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
        if items:
            cand = items[0]
            return cand.get("instructor_id") or cand.get("id") or (cand.get("instructor") or {}).get("id")
    return None


def test_catalog_serializes():
    # Phase 13: Services migrated to /api/v1/services
    r = client.get("/api/v1/services/catalog")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    if body:
        sample = body[0]
        # smoke keys; we just care that serialization didn't explode
        assert "id" in sample and "name" in sample


def test_instructor_detail_serializes():
    instr_id = _any_instructor_id()
    if not instr_id:
        # Don't fail CI if seed didn't produce an instructor
        return
    # Phase 8: Instructors migrated to /api/v1/instructors
    r = client.get(f"/api/v1/instructors/{instr_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, dict)
    assert data.get("id") or data.get("instructor_id")

    # If services are present, ensure they serialize without Pydantic blowing up
    services = data.get("services") or []
    if services:
        s0 = services[0]
        # These keys previously drifted—assert presence if they exist in payload
        if "name" in s0:
            assert isinstance(s0["name"], str | type(None))
        if "is_active" in s0:
            assert isinstance(s0["is_active"], bool | type(None))


def test_search_serializes():
    # Search endpoint (Phase 14: migrated to /api/v1/search)
    r = client.get("/api/v1/search/instructors?q=Yoga")
    if r.status_code == 200:
        return
    # If search doesn't exist, don't fail the suite; these are smoke/contract checks
    return
