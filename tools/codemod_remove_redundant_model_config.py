import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "backend" / "app" / "schemas"

CLS_RE = re.compile(r"class\s+([A-Za-z0-9_]+)\s*\(([^)]*)\)\s*:\s*([\s\S]*?)(?=\nclass\s+|\Z)", re.M)
# naïve block matcher for 'model_config = ConfigDict(...)' in class body
MC_RE = re.compile(r"\n\s+model_config\s*=\s*ConfigDict\(([\s\S]*?)\)\s*\n", re.M)


def only_forbid_validate(cfg: str) -> bool:
    """Return True when config only sets extra="forbid" and validate_assignment=True."""
    normalized = re.sub(r"\s+", "", cfg).replace("'", '"')
    allowed = {"extra=\"forbid\"", "validate_assignment=True"}
    parts = [part for part in normalized.split(",") if part]
    return set(parts).issubset(allowed)


changed_files = 0
for path in SCHEMAS.rglob("*.py"):
    if path.name in {"__init__.py", "_strict_base.py"}:
        continue
    original_text = path.read_text(encoding="utf-8")
    file_state = {"changed": False}

    def repl(match: re.Match[str]) -> str:
        original = match.group(0)
        bases = match.group(2)
        if "StrictModel" not in bases and "StrictRequestModel" not in bases:
            return original

        body = match.group(3)
        local_state = {"trimmed": False}

        def strip_mc(mc_match: re.Match[str]) -> str:
            cfg = mc_match.group(1)
            if only_forbid_validate(cfg):
                local_state["trimmed"] = True
                return "\n"
            return mc_match.group(0)

        new_body = MC_RE.sub(strip_mc, body)
        if local_state["trimmed"]:
            file_state["changed"] = True
            return original.replace(body, new_body, 1)
        return original

    new_text = CLS_RE.sub(repl, original_text)
    if file_state["changed"]:
        path.write_text(new_text, encoding="utf-8")
        changed_files += 1

print(f"Changed files: {changed_files}")
