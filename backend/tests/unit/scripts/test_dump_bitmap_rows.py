from datetime import date

import pytest
from scripts.ops.dump_bitmap_rows import dump_bitmap_rows


def test_dump_bitmap_rows_respects_db_url(monkeypatch, capsys):
    captured = {}

    class DummyResult:
        def fetchall(self):
            return [(date(2025, 1, 1), "HAS_BITS", 6, None)]

    class DummyConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, stmt, params):
            captured["params"] = params
            return DummyResult()

    class DummyEngine:
        def connect(self):
            captured["connected"] = True
            return DummyConn()

    def fake_create_engine(url: str):  # type: ignore[override]
        captured["url"] = url
        return DummyEngine()

    monkeypatch.setattr("scripts.ops.dump_bitmap_rows.create_engine", fake_create_engine)

    dump_bitmap_rows("postgresql://example", " instructor123 ,", days_back=1, days_forward=1)
    out = capsys.readouterr().out.strip().splitlines()

    assert captured["url"] == "postgresql://example"
    assert captured["params"]["instructor_id"] == "instructor123"
    assert out[0] == "day_date,has_bits,bytes,updated_at"
    assert out[1].startswith("2025-01-01,HAS_BITS,6")


def test_fetch_bitmap_rows_raises_on_empty(monkeypatch):
    class DummyConn:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, *args, **kwargs):
            class Empty:
                def fetchall(self):
                    return []

            return Empty()

    class DummyEngine:
        def connect(self):
            return DummyConn()

    monkeypatch.setattr("scripts.ops.dump_bitmap_rows.create_engine", lambda url: DummyEngine())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError):
        dump_bitmap_rows("postgresql://example", "instructor123", 1, 1)
