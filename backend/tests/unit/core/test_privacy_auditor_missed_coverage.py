"""Tests targeting missed lines in app/core/privacy_auditor.py.

Missed lines:
  210->219: auth returns non-200 status => returns None
  213->215: auth returns 200 but token is None
  270->269: field format check where value matches format (no violation)
  315-321: _test_endpoint with POST and other HTTP methods
  330->381: response status != expected_status
  336: public endpoint category applying rules
  360: default rules applied
  376-379: exception during endpoint test with verbose traceback
  446->457: filter_category set but not in category_map
  452->457: filter_category in category_map
  563->558: markdown report with example_value as falsy
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.privacy_auditor import (
    AuditResult,
    EndpointCategory,
    EndpointTest,
    PrivacyAuditor,
    PrivacyRule,
    Violation,
    ViolationSeverity,
)


@pytest.mark.asyncio
async def test_authenticate_user_non_200_returns_none(monkeypatch) -> None:
    """Line 210->219: when response status is not 200, return None."""
    auditor = PrivacyAuditor(base_url="http://example")

    class DummyResponse:
        status_code = 401

        @staticmethod
        def json():
            return {}

    async def _post(*_args, **_kwargs):
        return DummyResponse()

    monkeypatch.setattr(auditor.client, "post", _post)

    token = await auditor._authenticate_user("bad@example.com")
    await auditor.close()

    assert token is None


@pytest.mark.asyncio
async def test_authenticate_user_200_but_no_token_returns_none(monkeypatch) -> None:
    """Line 213->215: 200 response but access_token key missing => returns None."""
    auditor = PrivacyAuditor(base_url="http://example")

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"other_field": "value"}  # no access_token

    async def _post(*_args, **_kwargs):
        return DummyResponse()

    monkeypatch.setattr(auditor.client, "post", _post)

    token = await auditor._authenticate_user("notoken@example.com")
    await auditor.close()

    assert token is None
    assert "notoken@example.com" not in auditor.auth_tokens


def test_check_privacy_violations_format_matches() -> None:
    """Line 270->269: field format matches, so no violation for that field."""
    auditor = PrivacyAuditor(base_url="http://example")
    try:
        rules = PrivacyRule(
            name="rule",
            description="",
            forbidden_fields=[],
            field_format={"name": "first_name last_initial"},
        )
        data = {"name": "John D."}  # matches the "FirstName L." pattern
        violations = auditor._check_privacy_violations(data, rules, "/test", "GET")
        assert len(violations) == 0
    finally:
        asyncio.run(auditor.client.aclose())


@pytest.mark.asyncio
async def test_test_endpoint_post_method(monkeypatch) -> None:
    """Lines 315-318: test POST method branch."""
    auditor = PrivacyAuditor(base_url="http://example")

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"password": "secret"}

    async def _post(*_args, **_kwargs):
        return DummyResponse()

    monkeypatch.setattr(auditor.client, "post", _post)

    endpoint = EndpointTest(
        path="/api/v1/test",
        method="POST",
        category=EndpointCategory.INSTRUCTOR,
        body={"data": "test"},
    )
    violations = await auditor._test_endpoint(endpoint)
    await auditor.close()

    # The default rules forbid "password" and "password_hash"
    assert any(v.violation_type == "forbidden_field" for v in violations)


@pytest.mark.asyncio
async def test_test_endpoint_other_method(monkeypatch) -> None:
    """Lines 319-327: test other HTTP method (e.g. PUT) branch."""
    auditor = PrivacyAuditor(base_url="http://example")

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True}

    async def _request(*_args, **_kwargs):
        return DummyResponse()

    monkeypatch.setattr(auditor.client, "request", _request)

    endpoint = EndpointTest(
        path="/api/v1/test",
        method="PUT",
        category=EndpointCategory.INSTRUCTOR,
        body={"data": "test"},
    )
    violations = await auditor._test_endpoint(endpoint)
    await auditor.close()

    # PUT with default rules, no violations since no password/password_hash
    assert violations == []


@pytest.mark.asyncio
async def test_test_endpoint_status_mismatch(monkeypatch) -> None:
    """Line 330->381: response status != expected_status skips violation checks."""
    auditor = PrivacyAuditor(base_url="http://example")

    class DummyResponse:
        status_code = 404

        @staticmethod
        def json():
            return {"email": "should_not_be_checked@test.com"}

    async def _get(*_args, **_kwargs):
        return DummyResponse()

    monkeypatch.setattr(auditor.client, "get", _get)

    endpoint = EndpointTest(
        path="/api/v1/test",
        method="GET",
        category=EndpointCategory.PUBLIC,
        expected_status=200,
    )
    violations = await auditor._test_endpoint(endpoint)
    await auditor.close()

    assert violations == []


@pytest.mark.asyncio
async def test_test_endpoint_default_rules(monkeypatch) -> None:
    """Line 360: else branch for default rules applied when category is not PUBLIC/STUDENT."""
    auditor = PrivacyAuditor(base_url="http://example")

    async def _auth(*_args, **_kwargs):
        return "token"

    class DummyResponse:
        status_code = 200

        @staticmethod
        def json():
            return {"password_hash": "abc123", "name": "Test"}

    async def _get(*_args, **_kwargs):
        return DummyResponse()

    monkeypatch.setattr(auditor, "_authenticate_user", _auth)
    monkeypatch.setattr(auditor.client, "get", _get)

    endpoint = EndpointTest(
        path="/api/v1/instructors/me",
        method="GET",
        category=EndpointCategory.INSTRUCTOR,
        auth_required=True,
    )
    violations = await auditor._test_endpoint(endpoint, as_user="sarah.chen@example.com")
    await auditor.close()

    # Default rules forbid "password" and "password_hash"
    assert len(violations) == 1
    assert violations[0].field_path == "password_hash"


@pytest.mark.asyncio
async def test_test_endpoint_exception_with_verbose(monkeypatch) -> None:
    """Lines 376-379: exception during endpoint test with verbose=True."""
    auditor = PrivacyAuditor(base_url="http://example", verbose=True)

    async def _get(*_args, **_kwargs):
        raise ConnectionError("network down")

    monkeypatch.setattr(auditor.client, "get", _get)

    endpoint = EndpointTest(
        path="/api/v1/test",
        method="GET",
        category=EndpointCategory.PUBLIC,
    )
    violations = await auditor._test_endpoint(endpoint)
    await auditor.close()

    assert violations == []


def test_discover_endpoints_filter_category_not_in_map() -> None:
    """Line 446->457, 452->457: filter_category set to unknown value not in category_map."""
    auditor = PrivacyAuditor(base_url="http://example")
    try:
        auditor.filter_category = "unknown_category"
        endpoints = auditor._discover_endpoints()
        # Should return all endpoints because "unknown_category" is not in category_map
        assert len(endpoints) > 0
    finally:
        asyncio.run(auditor.client.aclose())


def test_discover_endpoints_filter_category_auth() -> None:
    """Line 452: filter_category in category_map for 'auth'."""
    auditor = PrivacyAuditor(base_url="http://example")
    try:
        auditor.filter_category = "auth"
        endpoints = auditor._discover_endpoints()
        assert all(e.category == EndpointCategory.STUDENT for e in endpoints)
    finally:
        asyncio.run(auditor.client.aclose())


def test_generate_report_markdown_violation_no_example() -> None:
    """Line 563->558: violation with example_value as None/falsy."""
    violation = Violation(
        endpoint="/api/v1/demo",
        method="GET",
        violation_type="forbidden_field",
        message="field exposed",
        severity=ViolationSeverity.HIGH,
        field_path="user.email",
        example_value=None,  # falsy value
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
        # Should NOT contain "Example" line since example_value is None
        assert "Example" not in report
    finally:
        asyncio.run(auditor.client.aclose())
