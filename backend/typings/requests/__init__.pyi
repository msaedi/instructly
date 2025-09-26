from typing import Any, Mapping, MutableMapping, Sequence

class Response:
    status_code: int
    content: bytes

    def json(self) -> Any: ...


def get(
    url: str,
    *,
    headers: Mapping[str, str] | None = ...,
    timeout: float | tuple[float, float] | None = ...,
    params: Mapping[str, Any] | Sequence[tuple[str, Any]] | None = ...,
    **kwargs: Any,
) -> Response: ...


def put(
    url: str,
    data: bytes | bytearray | memoryview | None = ...,
    *,
    headers: Mapping[str, str] | MutableMapping[str, str] | None = ...,
    timeout: float | tuple[float, float] | None = ...,
    **kwargs: Any,
) -> Response: ...


def delete(
    url: str,
    *,
    headers: Mapping[str, str] | None = ...,
    timeout: float | tuple[float, float] | None = ...,
    **kwargs: Any,
) -> Response: ...
