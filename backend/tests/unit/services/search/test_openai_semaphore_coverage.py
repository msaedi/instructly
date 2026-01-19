from __future__ import annotations

from app.services.search import openai_semaphore


def test_coerce_concurrency_values() -> None:
    assert openai_semaphore._coerce_concurrency(5) == 5
    assert openai_semaphore._coerce_concurrency(0) == 1
    assert openai_semaphore._coerce_concurrency(-2) == 1
    assert openai_semaphore._coerce_concurrency("bad") == 1
    assert openai_semaphore._coerce_concurrency(None) == 1
