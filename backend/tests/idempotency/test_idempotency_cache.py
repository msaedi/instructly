from app.idempotency.cache import get_cached, set_cached


def test_idempotency_cache_set_and_get(monkeypatch):
    raw = "POST:/api/payments/checkout:user:123:bodyhash"
    payload = {"status": "ok", "id": "abc123"}

    set_cached(raw, payload, ttl_s=2)
    got = get_cached(raw)
    assert got == payload
