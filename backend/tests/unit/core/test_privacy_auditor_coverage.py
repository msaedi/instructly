from __future__ import annotations

import asyncio
import json

import pytest

from app.core.privacy_auditor import (
    AuditResult,
    EndpointCategory,
    EndpointTest,
    PrivacyAuditor,
    PrivacyRule,
    Violation,
    ViolationSeverity,
    run_privacy_audit,
)


def test_load_config_defaults() -> None:
    auditor = PrivacyAuditor(base_url="http://example")
    try:
        assert "rules" in auditor.config
        assert "skip_endpoints" in auditor.config
    finally:
        asyncio.run(auditor.client.aclose())


def test_load_config_custom(tmp_path) -> None:
    config_file = tmp_path / "privacy.yml"
    config_file.write_text("skip_endpoints: ['/custom']\n")

    auditor = PrivacyAuditor(base_url="http://example", config_file=str(config_file))
    try:
        assert auditor.config["skip_endpoints"] == ["/custom"]
    finally:
        asyncio.run(auditor.client.aclose())


def test_check_field_recursively() -> None:
    auditor = PrivacyAuditor(base_url="http://example")
    try:
        data = {"user": {"email": "a"}, "items": [{"email": "b"}]}
        findings = auditor._check_field_recursively(data, "email")
        paths = {path for path, _ in findings}
        assert "user.email" in paths
        assert "items[0].email" in paths
    finally:
        asyncio.run(auditor.client.aclose())


def test_check_privacy_violations_forbidden_and_format() -> None:
    auditor = PrivacyAuditor(base_url="http://example")
    try:
        rules = PrivacyRule(
            name="rule",
            description="",
            forbidden_fields=["email"],
            field_format={"name": "first_name last_initial"},
        )
        data = {"email": "x", "name": "John Doe"}
        violations = auditor._check_privacy_violations(data, rules, "/", "GET")
        assert len(violations) == 2
        assert {v.violation_type for v in violations} == {"forbidden_field", "incorrect_format"}
    finally:
        asyncio.run(auditor.client.aclose())


def test_matches_format() -> None:
    auditor = PrivacyAuditor(base_url="http://example")
    try:
        assert auditor._matches_format("John D.", "first_name last_initial") is True
        assert auditor._matches_format("John Doe", "first_name last_initial") is False
        assert auditor._matches_format("anything", "other") is True
    finally:
        asyncio.run(auditor.client.aclose())


def test_discover_endpoints_filters() -> None:
    auditor = PrivacyAuditor(base_url="http://example")
    try:
        auditor.filter_category = "public"
        endpoints = auditor._discover_endpoints()
        assert endpoints
        assert all(endpoint.category == EndpointCategory.PUBLIC for endpoint in endpoints)

        auditor.filter_endpoint = "services"
        endpoints = auditor._discover_endpoints()
        assert all("services" in endpoint.path for endpoint in endpoints)

        auditor.config["skip_endpoints"] = ["/api/v1/services/search"]
        endpoints = auditor._discover_endpoints()
        assert "/api/v1/services/search" not in {endpoint.path for endpoint in endpoints}
    finally:
        asyncio.run(auditor.client.aclose())


def test_generate_report_formats() -> None:
    result = AuditResult(
        summary={"total_endpoints": 1, "passed": 1, "failed": 0},
        violations=[],
        endpoints_tested=[],
        execution_time=1.0,
        coverage={"total": "1/1"},
    )
    auditor = PrivacyAuditor(base_url="http://example")
    try:
        json_report = auditor.generate_report(result, format="json")
        assert "summary" in json_report

        markdown_report = auditor.generate_report(result, format="markdown")
        assert "No violations" in markdown_report

        with pytest.raises(ValueError):
            auditor.generate_report(result, format="xml")
    finally:
        asyncio.run(auditor.client.aclose())


@pytest.mark.asyncio
async def test_audit_collects_violations(monkeypatch) -> None:
    auditor = PrivacyAuditor(base_url="http://example")

    async def _test_endpoint(endpoint, as_user=None):
        if endpoint.path == "/student":
            return [
                Violation(
                    endpoint=endpoint.path,
                    method=endpoint.method,
                    violation_type="forbidden_field",
                    message="bad",
                    severity=ViolationSeverity.HIGH,
                )
            ]
        return []

    monkeypatch.setattr(
        auditor,
        "_discover_endpoints",
        lambda: [
            EndpointTest(path="/public", method="GET", category=EndpointCategory.PUBLIC),
            EndpointTest(
                path="/student",
                method="GET",
                category=EndpointCategory.STUDENT,
                auth_required=True,
                test_as_users=["john.smith@example.com"],
            ),
        ],
    )
    monkeypatch.setattr(auditor, "_test_endpoint", _test_endpoint)

    result = await auditor.audit()
    await auditor.close()

    assert result.summary["total_endpoints"] == 2
    assert result.summary["failed"] == 1
    assert len(result.violations) == 1


@pytest.mark.asyncio
async def test_run_privacy_audit_returns_report(monkeypatch) -> None:
    result = AuditResult(
        summary={"total_endpoints": 0, "passed": 0, "failed": 0},
        violations=[],
        endpoints_tested=[],
        execution_time=0.0,
        coverage={},
    )

    async def _audit(self):
        return result

    async def _close(self) -> None:
        return None

    monkeypatch.setattr(PrivacyAuditor, "audit", _audit, raising=True)
    monkeypatch.setattr(PrivacyAuditor, "generate_report", lambda *_args, **_kwargs: "report")
    monkeypatch.setattr(PrivacyAuditor, "close", _close, raising=True)

    got_result, report = await run_privacy_audit(
        base_url="http://example",
        output_format="json",
        filter_category="public",
        filter_endpoint="search",
    )
    assert got_result is result
    assert report == "report"


@pytest.mark.asyncio
async def test_authenticate_user_caches_token(monkeypatch) -> None:
    auditor = PrivacyAuditor(base_url="http://example")
    calls = {"count": 0}

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"access_token": "token"}

    async def _post(*_args, **_kwargs):
        calls["count"] += 1
        return DummyResponse()

    monkeypatch.setattr(auditor.client, "post", _post)

    token = await auditor._authenticate_user("john.smith@example.com")
    token_again = await auditor._authenticate_user("john.smith@example.com")

    await auditor.close()

    assert token == "token"
    assert token_again == "token"
    assert calls["count"] == 1


@pytest.mark.asyncio
async def test_authenticate_user_handles_exception(monkeypatch) -> None:
    auditor = PrivacyAuditor(base_url="http://example")

    async def _post(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(auditor.client, "post", _post)

    token = await auditor._authenticate_user("john.smith@example.com")
    await auditor.close()

    assert token is None


@pytest.mark.asyncio
async def test_test_endpoint_returns_empty_when_auth_missing(monkeypatch) -> None:
    auditor = PrivacyAuditor(base_url="http://example")

    async def _auth(*_args, **_kwargs):
        return None

    monkeypatch.setattr(auditor, "_authenticate_user", _auth)

    endpoint = EndpointTest(
        path="/api/v1/bookings",
        method="GET",
        category=EndpointCategory.STUDENT,
        auth_required=True,
    )

    violations = await auditor._test_endpoint(endpoint, as_user="john.smith@example.com")
    await auditor.close()

    assert violations == []


@pytest.mark.asyncio
async def test_test_endpoint_student_rules_violation(monkeypatch) -> None:
    auditor = PrivacyAuditor(base_url="http://example")

    async def _auth(*_args, **_kwargs):
        return "token"

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"instructor_name": "John Doe"}

    async def _get(*_args, **_kwargs):
        return DummyResponse()

    monkeypatch.setattr(auditor, "_authenticate_user", _auth)
    monkeypatch.setattr(auditor.client, "get", _get)

    endpoint = EndpointTest(
        path="/api/v1/bookings",
        method="GET",
        category=EndpointCategory.STUDENT,
        auth_required=True,
    )

    violations = await auditor._test_endpoint(endpoint, as_user="john.smith@example.com")
    await auditor.close()

    assert len(violations) == 1
    assert violations[0].violation_type == "incorrect_format"


@pytest.mark.asyncio
async def test_test_endpoint_handles_non_json(monkeypatch) -> None:
    auditor = PrivacyAuditor(base_url="http://example")

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json():
            raise json.JSONDecodeError("nope", "doc", 1)

    async def _get(*_args, **_kwargs):
        return DummyResponse()

    monkeypatch.setattr(auditor.client, "get", _get)

    endpoint = EndpointTest(path="/api/v1/public", method="GET", category=EndpointCategory.PUBLIC)
    violations = await auditor._test_endpoint(endpoint)
    await auditor.close()

    assert violations == []


def test_generate_report_includes_violations() -> None:
    violation = Violation(
        endpoint="/api/v1/demo",
        method="GET",
        violation_type="forbidden_field",
        message="field exposed",
        severity=ViolationSeverity.HIGH,
        field_path="user.email",
        example_value="user@example.com",
    )
    result = AuditResult(
        summary={"total_endpoints": 1, "passed": 0, "failed": 1},
        violations=[violation],
        endpoints_tested=[],
        execution_time=1.0,
        coverage={"total": "1/1"},
    )
    auditor = PrivacyAuditor(base_url="http://example")
    try:
        report = auditor.generate_report(result, format="markdown")
        assert "Violations Found" in report
        assert "Example" in report
    finally:
        asyncio.run(auditor.client.aclose())
