from __future__ import annotations

from typing import Any, Mapping, Sequence

def init(
    *,
    dsn: str | None = ...,
    environment: str | None = ...,
    release: str | None = ...,
    integrations: Sequence[Any] | None = ...,
    send_default_pii: bool | None = ...,
    traces_sample_rate: float | None = ...,
    profiles_sample_rate: float | None = ...,
    **kwargs: Any,
) -> None: ...


def set_context(key: str, value: Mapping[str, Any] | None) -> None: ...
