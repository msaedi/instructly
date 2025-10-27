from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass
class QueryCounter:
    value: int = 0


@contextmanager
def count_sql(engine: Engine) -> Iterator[QueryCounter]:
    """Temporarily count SQL statements executed against an engine."""

    counter = QueryCounter()

    def _listener(*_args) -> None:
        counter.value += 1

    event.listen(engine, "after_cursor_execute", _listener)
    try:
        yield counter
    finally:
        event.remove(engine, "after_cursor_execute", _listener)
