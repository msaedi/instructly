from __future__ import annotations

from datetime import datetime, timezone

from app.models.instructor import InstructorProfile
from app.models.service_catalog import InstructorService, ServiceCatalog, ServiceCategory


class DummyCounter:
    def __init__(self):
        self.count = 0

    def inc(self):
        self.count += 1


class DummyLabelCounter(DummyCounter):
    def labels(self, **_kwargs):
        return self


def test_bgc_report_id_handles_empty() -> None:
    instructor = InstructorProfile()
    instructor._bgc_report_id = None

    assert instructor.bgc_report_id is None

    instructor.bgc_report_id = ""
    assert instructor._bgc_report_id == ""


def test_bgc_report_id_decrypts_and_encrypts(monkeypatch) -> None:
    import app.core.crypto as crypto
    import app.core.metrics as metrics

    decrypt_counter = DummyCounter()
    encrypt_counter = DummyLabelCounter()

    monkeypatch.setattr(metrics, "BGC_REPORT_ID_DECRYPT_TOTAL", decrypt_counter)
    monkeypatch.setattr(metrics, "BGC_REPORT_ID_ENCRYPT_TOTAL", encrypt_counter)

    monkeypatch.setattr(crypto, "encrypt_report_token", lambda value: f"enc:{value}")
    monkeypatch.setattr(crypto, "decrypt_report_token", lambda value: value.replace("enc:", ""))

    instructor = InstructorProfile()
    instructor.bgc_report_id = "report-1"

    assert instructor._bgc_report_id.startswith("enc:")
    assert encrypt_counter.count == 1

    assert instructor.bgc_report_id == "report-1"
    assert decrypt_counter.count == 1


def test_bgc_report_id_decrypt_value_error(monkeypatch) -> None:
    import app.core.crypto as crypto

    monkeypatch.setattr(crypto, "decrypt_report_token", lambda _value: (_ for _ in ()).throw(ValueError()))

    instructor = InstructorProfile()
    instructor._bgc_report_id = "raw-token"

    assert instructor.bgc_report_id == "raw-token"


def _make_service(
    *,
    service_id: str,
    active: bool,
    category_name: str = "Music",
    category_slug: str = "music",
) -> InstructorService:
    category = ServiceCategory(name=category_name, slug=category_slug)
    catalog = ServiceCatalog(id=service_id, name="Guitar", category=category)
    service = InstructorService(
        instructor_profile_id="inst-1",
        service_catalog_id=service_id,
        hourly_rate=50.0,
        is_active=active,
    )
    service.catalog_entry = catalog
    return service


def test_service_helpers_and_to_dict() -> None:
    instructor = InstructorProfile(
        user_id="user-1",
        min_advance_booking_hours=24,
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )
    active_service = _make_service(service_id="svc-active", active=True)
    inactive_service = _make_service(service_id="svc-inactive", active=False)
    instructor.instructor_services = [active_service, inactive_service]

    assert instructor.active_services == [active_service]
    assert instructor.has_active_services is True
    assert instructor.total_services == 2
    assert instructor.offered_categories == {"Music"}
    assert instructor.offered_category_slugs == {"music"}
    assert instructor.offers_service("svc-active") is True
    assert instructor.offers_service("missing") is False
    assert instructor.get_service_by_catalog_id("svc-active") is active_service
    assert instructor.get_service_by_catalog_id("missing") is None
    assert instructor.can_accept_booking_at(24) is True
    assert instructor.can_accept_booking_at(10) is False

    data = instructor.to_dict(include_services=True)
    assert data["active_services_count"] == 1
    assert data["total_services"] == 2
    assert len(data["services"]) == 1

    no_services = instructor.to_dict(include_services=False)
    assert "services" not in no_services


def test_no_active_services_returns_empty() -> None:
    instructor = InstructorProfile(user_id="user-2")
    inactive_service = _make_service(service_id="svc", active=False)
    instructor.instructor_services = [inactive_service]

    assert instructor.has_active_services is False
    assert instructor.active_services == []
    assert instructor.offered_categories == set()
