from fastapi import APIRouter, Depends, FastAPI, Header
from fastapi.testclient import TestClient

from app.middleware.rate_limiter import rate_limit

router = APIRouter()


def inject_value(x_token: str = Header("token")) -> str:
  return x_token


@router.get("/__di_check")  # lightweight, no DB
@rate_limit("5/minute")
def di_check(value: str = Depends(inject_value)) -> dict[str, str]:
  return {"value": value}


def test_rate_limiter_preserves_di():
  # Use an isolated FastAPI app to avoid polluting global routes
  app = FastAPI()
  app.include_router(router)
  with TestClient(app) as client:
    r = client.get("/__di_check", headers={"x-token": "ok"})
  assert r.status_code in (200, 429)
  if r.status_code == 200:
    assert r.json() == {"value": "ok"}
