from __future__ import annotations

from datetime import datetime, timezone

from tests.conftest import _ensure_region_boundary

from app.models.location_alias import LocationAlias
from app.models.region_boundary import RegionBoundary
from app.models.unresolved_location_query import UnresolvedLocationQuery


def _create_region(db, borough: str) -> RegionBoundary:
    region = _ensure_region_boundary(db, borough)
    db.flush()
    return region


def _create_pending_alias(db, *, alias: str, region_id: str) -> LocationAlias:
    alias_row = LocationAlias(
        alias_normalized=alias,
        region_boundary_id=region_id,
        status="pending_review",
        source="user_learning",
        confidence=0.92,
        user_count=6,
    )
    db.add(alias_row)
    db.flush()
    return alias_row


def _create_unresolved_query(db, query: str, region_id: str) -> UnresolvedLocationQuery:
    row = UnresolvedLocationQuery(
        query_normalized=query,
        sample_original_queries=[query],
        search_count=2,
        unique_user_count=1,
        click_region_counts={region_id: 3},
        click_count=3,
        last_seen_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    return row


def test_list_unresolved_location_queries(client, db, auth_headers_admin):
    region = _create_region(db, "Manhattan")
    unresolved = _create_unresolved_query(db, "museum mile", region.id)
    db.commit()

    response = client.get(
        "/api/v1/admin/location-learning/unresolved",
        headers=auth_headers_admin,
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert any(item["id"] == unresolved.id for item in payload["queries"])


def test_list_pending_aliases_and_approve_reject(client, db, auth_headers_admin):
    region = _create_region(db, "Brooklyn")
    alias_one = _create_pending_alias(db, alias="wburg", region_id=region.id)
    alias_two = _create_pending_alias(db, alias="bk bridge", region_id=region.id)
    db.commit()

    pending = client.get(
        "/api/v1/admin/location-learning/pending-aliases",
        headers=auth_headers_admin,
    )
    assert pending.status_code == 200
    pending_payload = pending.json()
    assert any(item["id"] == alias_one.id for item in pending_payload["aliases"])

    approve = client.post(
        f"/api/v1/admin/location-learning/aliases/{alias_one.id}/approve",
        headers=auth_headers_admin,
    )
    assert approve.status_code == 200
    db.refresh(alias_one)
    assert alias_one.status == "active"

    reject = client.post(
        f"/api/v1/admin/location-learning/aliases/{alias_two.id}/reject",
        headers=auth_headers_admin,
    )
    assert reject.status_code == 200
    db.refresh(alias_two)
    assert alias_two.status == "deprecated"


def test_list_regions_and_process(client, db, auth_headers_admin):
    _create_region(db, "Queens")
    db.commit()

    regions = client.get(
        "/api/v1/admin/location-learning/regions",
        headers=auth_headers_admin,
    )
    assert regions.status_code == 200
    payload = regions.json()
    assert payload["regions"]

    process = client.post(
        "/api/v1/admin/location-learning/process",
        headers=auth_headers_admin,
    )
    assert process.status_code == 200
    assert "learned_count" in process.json()


def test_create_manual_alias_paths(client, db, auth_headers_admin):
    region_one = _create_region(db, "Manhattan")
    region_two = _create_region(db, "Bronx")
    db.commit()

    response = client.post(
        "/api/v1/admin/location-learning/aliases",
        headers=auth_headers_admin,
        json={
            "alias": "ues",
            "region_boundary_id": region_one.id,
            "alias_type": "abbreviation",
        },
    )
    assert response.status_code == 200

    ambiguous = client.post(
        "/api/v1/admin/location-learning/aliases",
        headers=auth_headers_admin,
        json={
            "alias": "river",
            "candidate_region_ids": [region_one.id, region_two.id],
            "alias_type": "colloquial",
        },
    )
    assert ambiguous.status_code == 200

    duplicate = client.post(
        "/api/v1/admin/location-learning/aliases",
        headers=auth_headers_admin,
        json={
            "alias": "ues",
            "region_boundary_id": region_one.id,
            "alias_type": "abbreviation",
        },
    )
    assert duplicate.status_code == 400


def test_dismiss_unresolved_query(client, db, auth_headers_admin):
    region = _create_region(db, "Queens")
    unresolved = _create_unresolved_query(db, "astoria", region.id)
    db.commit()

    response = client.post(
        f"/api/v1/admin/location-learning/unresolved/{unresolved.query_normalized}/dismiss",
        headers=auth_headers_admin,
    )
    assert response.status_code == 200
    db.refresh(unresolved)
    assert unresolved.status == "rejected"


def test_non_admin_forbidden(client, auth_headers_student):
    response = client.get(
        "/api/v1/admin/location-learning/unresolved",
        headers=auth_headers_student,
    )
    assert response.status_code == 403
