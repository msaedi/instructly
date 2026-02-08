from types import SimpleNamespace

import pytest
from scripts.reset_and_seed_yaml import DatabaseSeeder


def _new_seeder() -> DatabaseSeeder:
    return DatabaseSeeder.__new__(DatabaseSeeder)


def _build_catalog_lookups(catalog_services):
    catalog_by_id = {svc.id: svc for svc in catalog_services}
    catalog_by_slug = {
        str(svc.slug).strip().lower(): svc
        for svc in catalog_services
        if str(getattr(svc, "slug", "") or "").strip()
    }
    catalog_by_name_lc = {}
    catalog_by_normalized_name = {}
    for svc in catalog_services:
        name_lc = str(svc.name).strip().lower()
        if name_lc:
            catalog_by_name_lc.setdefault(name_lc, []).append(svc)
        normalized_name = DatabaseSeeder._normalize_seed_text(str(svc.name))
        if normalized_name:
            catalog_by_normalized_name.setdefault(normalized_name, []).append(svc)
    return catalog_by_id, catalog_by_slug, catalog_by_name_lc, catalog_by_normalized_name


def test_resolve_catalog_service_uses_service_slug():
    seeder = _new_seeder()
    catalog_services = [
        SimpleNamespace(id="svc-piano", name="Piano", slug="piano"),
        SimpleNamespace(id="svc-guitar", name="Guitar", slug="guitar"),
    ]
    catalog_by_id, catalog_by_slug, catalog_by_name_lc, catalog_by_normalized_name = _build_catalog_lookups(
        catalog_services
    )

    service, source, score = seeder._resolve_catalog_service(
        service_data={"name": "Any Name", "service_slug": "guitar"},
        instructor_data={"profile": {"bio": "Teacher"}},
        catalog_services=catalog_services,
        catalog_by_id=catalog_by_id,
        catalog_by_slug=catalog_by_slug,
        catalog_by_name_lc=catalog_by_name_lc,
        catalog_by_normalized_name=catalog_by_normalized_name,
    )

    assert service is not None
    assert service.id == "svc-guitar"
    assert source == "service_slug"
    assert score == 1.0


def test_resolve_catalog_service_uses_fuzzy_matching():
    seeder = _new_seeder()
    catalog_services = [
        SimpleNamespace(id="svc-esl", name="English (ESL/EFL)", slug="english-esl-efl"),
        SimpleNamespace(id="svc-sat", name="SAT", slug="sat"),
    ]
    catalog_by_id, catalog_by_slug, catalog_by_name_lc, catalog_by_normalized_name = _build_catalog_lookups(
        catalog_services
    )

    service, source, score = seeder._resolve_catalog_service(
        service_data={"name": "ESL", "description": "English as a second language"},
        instructor_data={"profile": {"bio": "Experienced ESL teacher"}},
        catalog_services=catalog_services,
        catalog_by_id=catalog_by_id,
        catalog_by_slug=catalog_by_slug,
        catalog_by_name_lc=catalog_by_name_lc,
        catalog_by_normalized_name=catalog_by_normalized_name,
    )

    assert service is not None
    assert service.id == "svc-esl"
    assert source == "fuzzy"
    assert score >= seeder._DYNAMIC_MATCH_MIN_SCORE


def test_audit_instructors_yaml_shape_rejects_unsupported_fields():
    seeder = _new_seeder()
    sample_instructors = [
        {
            "email": "sample@example.com",
            "first_name": "Sample",
            "last_name": "Instructor",
            "zip_code": "10001",
            "phone": "+10000000000",
            "availability_pattern": "standard_weekday",
            "profile": {
                "bio": "Sample bio",
                "years_experience": 4,
                "areas": ["Manhattan"],
                "services": [
                    {
                        "name": "Piano",
                        "hourly_rate": 100,
                        "duration_options": [60],
                        "levels_taught": ["advanced"],
                    }
                ],
            },
        }
    ]

    with pytest.raises(ValueError, match="unsupported keys"):
        seeder._audit_instructors_yaml_shape(sample_instructors)
