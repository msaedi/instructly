from unittest.mock import AsyncMock, Mock, patch

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import settings
from app.middleware.rate_limiter import RateLimitKeyType, rate_limit


@patch("app.middleware.rate_limiter.RateLimiter")
def test_rate_limiter_with_request_body_parameter(mock_limiter_class, monkeypatch):
    """Rate limiter shouldn't crash when endpoint has 'request' body param."""
    monkeypatch.setattr(settings, "rate_limit_enabled", True, raising=False)

    app = FastAPI()

    @app.post("/collision")
    @rate_limit("5/minute", key_type=RateLimitKeyType.IP)
    async def collision(request: dict, req: Request):
        return {"ok": True}

    mock_limiter = Mock()
    mock_limiter.check_rate_limit = AsyncMock(return_value=(True, 1, 0))
    mock_limiter.get_remaining_requests = AsyncMock(return_value=4)
    mock_limiter_class.return_value = mock_limiter

    client = TestClient(app)
    response = client.post("/collision", json={"foo": "bar"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    mock_limiter.check_rate_limit.assert_called_once()
