import json

from app.main import fastapi_app as app


def main() -> None:
    doc = app.openapi()
    print(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))


if __name__ == "__main__":
    main()
