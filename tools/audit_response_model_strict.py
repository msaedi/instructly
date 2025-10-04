import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUTES = ROOT / "backend" / "app" / "routes"
SCHEMAS = ROOT / "backend" / "app" / "schemas"

DEC = re.compile(r'@router\.(get|post|put|delete|patch)\([^)]*response_model\s*=\s*([A-Za-z0-9_.\[\]]+)')
CLS = re.compile(r'class\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*:')


def is_strict_schema(txt: str) -> bool:
    """Return True if schema is strict (StrictModel or extra="forbid")."""
    return ("StrictModel" in txt) or ('extra="forbid"' in txt) or ("extra='forbid'" in txt)


# build class index: class name -> list of (file, file text)
class_index = {}
for schema_file in SCHEMAS.rglob("*.py"):
    text = schema_file.read_text(encoding="utf-8", errors="ignore")
    for match in CLS.finditer(text):
        class_index.setdefault(match.group(1), []).append((schema_file, text))


offenders: list[str] = []
total_refs = 0
for route_file in ROUTES.rglob("*.py"):
    text = route_file.read_text(encoding="utf-8", errors="ignore")
    for match in DEC.finditer(text):
        total_refs += 1
        raw = match.group(2).strip()
        # normalize Optional/List[...] -> inner name
        model = re.sub(r'.*\[([A-Za-z0-9_\.]+)\].*', r'\1', raw)
        short = model.split(".")[-1]
        ok = False
        for schema_entry in class_index.get(short, []):
            _, schema_text = schema_entry
            if is_strict_schema(schema_text):
                ok = True
                break
        if not ok:
            offenders.append(f"{route_file}:{match.group(0).strip()} -> {model}")

if offenders:
    print(f"TOTAL_REFERENCES={total_refs}")
    print(f"OFFENDER_COUNT={len(offenders)}")
    print("OFFENDERS:")
    print("\n".join(offenders))
    sys.exit(0)

print(f"TOTAL_REFERENCES={total_refs}")
print("OFFENDER_COUNT=0")
print("OK")
