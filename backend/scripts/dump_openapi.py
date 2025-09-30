# bootstrap sys.path so `app` is importable when run as a script
import contextlib
import io
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def load_app():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        from app.main import fastapi_app  # type: ignore
    noise = buffer.getvalue()
    if noise.strip():
        print(noise, file=sys.stderr, end="")
    return fastapi_app


def main() -> None:
    app = load_app()
    doc = app.openapi()
    print(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
