from datetime import datetime
from unittest.mock import Mock

from jinja2 import TemplateNotFound
from jinja2.sandbox import SandboxedEnvironment
import pytest

from app.services.template_service import TemplateService


class StubCache:
    def __init__(self, *, raise_get=False, raise_set=False):
        self.store = {}
        self.raise_get = raise_get
        self.raise_set = raise_set
        self.delete_calls = []
        self.pattern_calls = []

    def get(self, key):
        if self.raise_get:
            raise RuntimeError("get failed")
        return self.store.get(key)

    def set(self, key, value, ttl=None):
        if self.raise_set:
            raise RuntimeError("set failed")
        self.store[key] = value

    def delete(self, key):
        self.delete_calls.append(key)

    def delete_pattern(self, pattern):
        self.pattern_calls.append(pattern)


def test_custom_filters_and_cache_key():
    service = TemplateService(db=Mock(), cache=None)
    currency = service.env.filters["currency"]
    format_date = service.env.filters["format_date"]
    format_time = service.env.filters["format_time"]

    assert currency(12.5) == "$12.50"
    assert format_date("2024-01-01") == "2024-01-01"
    assert format_date(datetime(2024, 1, 1)).startswith("January")
    assert format_time("10:00") == "10:00"
    assert "10:00" in format_time(datetime(2024, 1, 1, 10, 0))
    assert service._get_cache_key("prefix", "a", 1) == "prefix:a:1"


def test_init_without_db_closes_session():
    service = TemplateService(db=None, cache=None)
    assert service._owns_db is True
    service.__del__()


def test_get_common_context_cache_hit_and_set():
    cache = StubCache()
    cache.store[TemplateService.CACHE_PREFIX_CONTEXT] = {"brand_name": "Cached"}
    service = TemplateService(db=Mock(), cache=cache)

    cached = service.get_common_context()
    assert cached["brand_name"] == "Cached"

    cache_miss = StubCache(raise_get=True, raise_set=True)
    service_miss = TemplateService(db=Mock(), cache=cache_miss)
    context = service_miss.get_common_context()
    assert "brand_name" in context


def test_render_template_success_and_template_not_found():
    service = TemplateService(db=Mock(), cache=StubCache())
    rendered = service.render_template("email/base.html", context={"subject": "Hello"})
    assert "Hello" in rendered

    rendered_no_context = service.render_template("email/base.html")
    assert "<html>" in rendered_no_context

    with pytest.raises(TemplateNotFound):
        service.render_template("missing_template.html")


def test_render_template_fallback_path(monkeypatch):
    service = TemplateService(db=Mock(), cache=StubCache())

    def raise_error(_name):
        raise RuntimeError("boom")

    monkeypatch.setattr(service.env, "get_template", raise_error)

    rendered = service.render_template("email/base.html", context={"subject": "Fallback"})
    assert "Fallback" in rendered


def test_render_template_fallback_failure(monkeypatch):
    service = TemplateService(db=Mock(), cache=StubCache())

    def raise_error(_name):
        raise RuntimeError("boom")

    def raise_from_string(_template):
        raise RuntimeError("fallback failed")

    monkeypatch.setattr(service.env, "get_template", raise_error)
    monkeypatch.setattr(service.env, "from_string", raise_from_string)

    with pytest.raises(RuntimeError):
        service.render_template("email/base.html")


def test_render_string_error(monkeypatch):
    service = TemplateService(db=Mock(), cache=StubCache())

    def raise_error(_template):
        raise RuntimeError("boom")

    monkeypatch.setattr(service.env, "from_string", raise_error)

    with pytest.raises(RuntimeError):
        service.render_string("Hello {{ name }}", name="Test")


def test_render_string_success():
    service = TemplateService(db=Mock(), cache=StubCache())
    rendered = service.render_string("Hello {{ name }}", name="Test")
    assert rendered == "Hello Test"


def test_template_exists_cache_and_set(monkeypatch):
    cache = StubCache()
    cache.store[service_key := f"{TemplateService.CACHE_PREFIX_EXISTS}:email/base.html"] = True
    service = TemplateService(db=Mock(), cache=cache)

    assert service.template_exists("email/base.html") is True
    assert cache.get(service_key) is True

    cache_miss = StubCache(raise_get=True)
    service_miss = TemplateService(db=Mock(), cache=cache_miss)
    assert service_miss.template_exists("missing_template.html") is False
    assert cache_miss.store[service_miss._get_cache_key(service_miss.CACHE_PREFIX_EXISTS, "missing_template.html")] is False

    cache_non_bool = StubCache()
    cache_non_bool.store[service_key] = "yes"
    service_non_bool = TemplateService(db=Mock(), cache=cache_non_bool)
    assert service_non_bool.template_exists("email/base.html") is True

    service_no_cache = TemplateService(db=Mock(), cache=None)
    service_no_cache._caching_enabled = False
    assert service_no_cache.template_exists("email/base.html") is True


def test_invalidate_cache_and_stats(monkeypatch):
    cache = StubCache()
    service = TemplateService(db=Mock(), cache=cache)

    service.invalidate_cache()
    assert cache.delete_calls
    assert cache.pattern_calls

    service.invalidate_cache("template:context:common")

    monkeypatch.setattr(service, "get_metrics", lambda: {"render": {"count": 1}})
    stats = service.get_cache_stats()
    assert stats.get("operation_metrics")

    monkeypatch.setattr(service, "get_metrics", lambda: None)
    stats_no_metrics = service.get_cache_stats()
    assert "operation_metrics" not in stats_no_metrics

    service._caching_enabled = False
    service.invalidate_cache()

    cache_error = StubCache()
    cache_error.delete = lambda _key: (_ for _ in ()).throw(RuntimeError("boom"))
    service_error = TemplateService(db=Mock(), cache=cache_error)
    service_error.invalidate_cache()


# ── SSTI regression tests (SSTI-VULN-01) ─────────────────────────────────


def test_uses_sandboxed_environment():
    """Regression: TemplateService must use SandboxedEnvironment, never plain Environment."""
    service = TemplateService(db=Mock(), cache=None)
    assert isinstance(service.env, SandboxedEnvironment)


def test_template_syntax_in_context_vars_not_evaluated():
    """Regression: user-controlled data containing {{ }} must NOT be evaluated as Jinja2 code."""
    service = TemplateService(db=Mock(), cache=None)
    result = service.render_string("Hello {{ name }}", name="{{ 7*7 }}")
    # If the sandbox/autoescape is working, the output must NOT contain "49"
    assert "49" not in result
    # The template syntax should be escaped or rendered literally
    assert "7*7" in result or "&" in result
