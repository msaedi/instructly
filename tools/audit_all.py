#!/usr/bin/env python3
"""Repo-wide guardrail audit (report-only)."""

from __future__ import annotations

import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:  # Python 3.11+
    import tomllib  # type: ignore
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
SCHEMAS_DIR = BACKEND_DIR / "app" / "schemas"
ROUTES_DIR = BACKEND_DIR / "app" / "routes"
REPOSITORIES_DIR = BACKEND_DIR / "app" / "repositories"
SERVICES_DIR = BACKEND_DIR / "app" / "services"

METHOD_NAMES = {"get", "post", "put", "delete", "patch"}
REQUEST_SUFFIXES = ("Request", "Create", "Update", "Confirm", "Reset", "Verify")
PIN_PACKAGES = ["openapi-typescript", "@playwright/test", "@axe-core/playwright"]
SIZE_LIMIT_CMD = ["npx", "--yes", "size-limit", "--json"]
CONTRACT_CHECK_CMD = ["npm", "run", "contract:check"]
CONTRACT_AUDIT_CMD = ["npm", "run", "audit:contract:ci"]
PUBLIC_ENV_CMD = ["node", "scripts/verify-public-env.mjs"]
CONTRACT_AUDIT_JSON = FRONTEND_DIR / ".artifacts" / "contract-audit.json"

AuditJSON = Dict[str, Any]


@dataclass
class Check:
    """Structured result for a guardrail check."""

    name: str
    title: str
    violations: List[Any] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> AuditJSON:
        return {
            "title": self.title,
            "violations": self.violations,
            "errors": self.errors,
            "details": self.details,
        }


def run(cmd: List[str], cwd: Path, env: Optional[Dict[str, str]] = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def load_pyproject() -> Dict[str, Any]:
    pyproject_path = BACKEND_DIR / "pyproject.toml"
    with pyproject_path.open("rb") as fh:
        return tomllib.load(fh)


def iter_python_modules(root: Path) -> Iterable[str]:
    for path in root.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        rel = path.relative_to(BACKEND_DIR)
        module = "backend." + ".".join(rel.with_suffix("").parts)
        yield module


def backend_strict_coverage() -> Check:
    check = Check(
        name="backend_strict_coverage",
        title="Backend strict coverage (mypy overrides)",
    )

    data = load_pyproject()
    overrides = data.get("tool", {}).get("mypy", {}).get("overrides", [])
    patterns: List[str] = []
    for entry in overrides:
        modules = entry.get("module")
        if not modules:
            continue
        if isinstance(modules, str):
            patterns.append(modules)
        else:
            patterns.extend(modules)
    patterns = sorted(set(patterns))

    targets = [REPOSITORIES_DIR, SERVICES_DIR, ROUTES_DIR]
    uncovered: List[str] = []
    total_modules = 0
    for directory in targets:
        for module in iter_python_modules(directory):
            total_modules += 1
            if any(fnmatch.fnmatch(module, pattern) for pattern in patterns):
                continue
            uncovered.append(module)

    check.violations = sorted(uncovered)
    check.details["total_modules"] = total_modules
    check.details["patterns"] = patterns
    check.details["uncovered_count"] = len(uncovered)
    return check


def get_base_names(node: ast.ClassDef) -> List[str]:
    names: List[str] = []
    for base in node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            parts: List[str] = []
            current: ast.AST = base
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            names.append(".".join(reversed(parts)))
    return names


def has_dual_mode_config(node: ast.ClassDef) -> bool:
    for stmt in node.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == "model_config":
                    value = stmt.value
                    if isinstance(value, ast.Attribute):
                        parts: List[str] = []
                        current: ast.AST = value
                        while isinstance(current, ast.Attribute):
                            parts.append(current.attr)
                            current = current.value
                        if isinstance(current, ast.Name):
                            parts.append(current.id)
                        dotted = ".".join(reversed(parts))
                        if "StrictRequestModel" in dotted:
                            return True
                    elif isinstance(value, ast.Name):
                        if "StrictRequestModel" in value.id:
                            return True
                    elif isinstance(value, ast.Call):
                        call = value
                        if isinstance(call.func, ast.Name) and call.func.id == "ConfigDict":
                            for keyword in call.keywords:
                                if keyword.arg == "extra":
                                    expr = keyword.value
                                    if isinstance(expr, ast.IfExp):
                                        # Requires Python 3.9+ for ast.unparse
                                        if hasattr(ast, "unparse"):
                                            text = ast.unparse(expr)
                                            if (
                                                "STRICT" in text
                                                and "forbid" in text
                                                and "ignore" in text
                                            ):
                                                return True
                        if (
                            isinstance(call.func, ast.Attribute)
                            and isinstance(call.func.value, ast.Name)
                            and call.func.value.id == "StrictRequestModel"
                        ):
                            return True
    return False


def request_dto_dual_mode() -> Check:
    check = Check(
        name="request_dto_dual_mode",
        title="Request DTO dual-mode coverage",
    )

    offenders: List[Dict[str, Any]] = []
    total_candidates = 0
    for path in SCHEMAS_DIR.rglob("*.py"):
        if path.name.startswith("_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover
            check.errors.append(f"Parse error in {path}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name.endswith(REQUEST_SUFFIXES):
                total_candidates += 1
                bases = get_base_names(node)
                inherits_strict = any("StrictRequestModel" in base for base in bases)
                dual_mode = inherits_strict or has_dual_mode_config(node)
                if not dual_mode:
                    offenders.append(
                        {
                            "file": str(path.relative_to(ROOT)),
                            "class": node.name,
                            "bases": bases,
                        }
                    )
    check.violations = sorted(offenders, key=lambda x: (x["file"], x["class"]))
    check.details["total_request_like_classes"] = total_candidates
    check.details["offender_count"] = len(offenders)
    return check


def get_attribute_root_name(attr: ast.Attribute) -> str:
    parts = [attr.attr]
    value = attr.value
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if isinstance(value, ast.Name):
        parts.append(value.id)
    return ".".join(reversed(parts))


def routes_response_model() -> Check:
    check = Check(
        name="routes_response_model",
        title="Routes missing response_model",
    )

    missing: List[Dict[str, Any]] = []
    for path in ROUTES_DIR.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:  # pragma: no cover
            check.errors.append(f"Parse error in {path}: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                        if decorator.func.attr not in METHOD_NAMES:
                            continue
                        base_name = get_attribute_root_name(decorator.func)
                        if not base_name.endswith("router"):
                            continue
                        has_response_model = any(
                            kw.arg == "response_model" for kw in decorator.keywords if kw.arg
                        )
                        if not has_response_model:
                            missing.append(
                                {
                                    "file": str(path.relative_to(ROOT)),
                                    "line": decorator.lineno,
                                    "method": decorator.func.attr,
                                    "router": base_name,
                                    "endpoint": node.name,
                                }
                            )
    check.violations = sorted(missing, key=lambda x: (x["file"], x["line"]))
    check.details["total_missing"] = len(missing)
    return check


def ensure_frontend_artifacts_dir() -> None:
    artifacts = FRONTEND_DIR / ".artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)


def contract_audit() -> Check:
    check = Check(
        name="frontend_contract",
        title="Frontend contract drift & forbidden imports",
    )

    ensure_frontend_artifacts_dir()
    env = {"CI": "1"}

    contract = run(CONTRACT_CHECK_CMD, cwd=FRONTEND_DIR, env=env)
    drift = contract.returncode != 0
    check.details["contract_stdout"] = contract.stdout.strip()
    check.details["contract_stderr"] = contract.stderr.strip()
    if drift:
        check.violations.append(
            {
                "kind": "drift",
                "message": contract.stderr.strip() or contract.stdout.strip(),
            }
        )

    audit = run(CONTRACT_AUDIT_CMD, cwd=FRONTEND_DIR, env=env)
    if audit.returncode not in (0, 1):
        check.errors.append(
            f"contract audit command failed (exit {audit.returncode}): {audit.stderr.strip()}"
        )

    if CONTRACT_AUDIT_JSON.exists():
        try:
            data = json.loads(CONTRACT_AUDIT_JSON.read_text(encoding="utf-8"))
            outside = int(data.get("directImports", {}).get("outsideAllowed", 0))
            via_shim = int(data.get("viaShimCount", 0))
            check.details["direct_imports_outside_allowed"] = outside
            check.details["via_shim_count"] = via_shim
            if outside > 0:
                check.violations.append({"kind": "forbidden_direct_imports", "count": outside})
        except json.JSONDecodeError as exc:
            check.errors.append(f"Failed to parse contract audit JSON: {exc}")
    else:
        check.errors.append("contract audit JSON not found; did the audit command run?")

    return check


def pin_assert() -> Check:
    check = Check(
        name="pin_assert",
        title="Pinned versions (codegen/test deps)",
    )
    package_json = json.loads((FRONTEND_DIR / "package.json").read_text(encoding="utf-8"))
    deps = package_json.get("dependencies", {})
    dev_deps = package_json.get("devDependencies", {})
    pattern = re.compile(r"^[0-9]+(\.[0-9]+)*(?:-[0-9A-Za-z.]+)?$")
    for pkg in PIN_PACKAGES:
        version = deps.get(pkg) or dev_deps.get(pkg)
        if not version:
            check.errors.append(f"{pkg} not found in package.json")
            continue
        if not pattern.fullmatch(version):
            check.violations.append({"package": pkg, "version": version})
    return check


def public_env_full_scan() -> Check:
    check = Check(
        name="public_env",
        title="Public env full scan",
    )

    try:
        root_commit = (
            subprocess.check_output(
                ["git", "rev-list", "--max-parents=0", "HEAD"], cwd=ROOT, text=True
            )
            .strip()
            .splitlines()[0]
        )
    except subprocess.SubprocessError as exc:
        check.errors.append(f"Failed to resolve root commit: {exc}")
        return check

    env = {"CI": "1", "GITHUB_BASE_REF": root_commit}
    result = run(PUBLIC_ENV_CMD, cwd=FRONTEND_DIR, env=env)
    check.details["stdout"] = result.stdout.strip()
    check.details["stderr"] = result.stderr.strip()
    if result.returncode != 0:
        findings = [line.strip()[2:].strip() for line in result.stderr.splitlines() if line.strip().startswith("- ")]
        if not findings:
            findings = [line.strip() for line in result.stderr.splitlines() if line.strip()]
        check.violations.extend(findings)
    return check


def parse_size_limit_output(raw: str) -> List[Dict[str, Any]]:
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "results" in data:
            res = data["results"]
            if isinstance(res, list):
                return res
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def size_limit_check() -> Check:
    check = Check(
        name="size_limit",
        title="Size-limit budgets",
    )

    ensure_frontend_artifacts_dir()
    result = run(SIZE_LIMIT_CMD, cwd=FRONTEND_DIR, env={"CI": "1"})
    blocks = parse_size_limit_output(result.stdout)
    check.details["entries"] = blocks
    for entry in blocks:
        if entry.get("passed") is False:
            check.violations.append(
                {
                    "name": entry.get("name"),
                    "size": entry.get("size"),
                    "limit": entry.get("limit"),
                }
            )
    if not blocks and result.returncode != 0:
        check.errors.append(
            f"size-limit command failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return check


def load_pip_allowlist() -> set[str]:
    allow = set()
    txt = BACKEND_DIR / "pip-audit-allowlist.txt"
    if txt.exists():
        for line in txt.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            allow.add(line)
    json_path = BACKEND_DIR / "pip-audit.ignore.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            for item in data.get("ignore", []):
                allow.add(item)
        except json.JSONDecodeError:
            pass
    return allow


def pip_audit_check() -> Check:
    check = Check(
        name="pip_audit",
        title="pip-audit (high/critical)",
    )
    allow = load_pip_allowlist()
    cmd = [
        sys.executable,
        "-m",
        "pip_audit",
        "--format",
        "json",
        "-r",
        "requirements.txt",
    ]
    try:
        result = run(cmd, cwd=BACKEND_DIR)
    except FileNotFoundError:
        check.errors.append("pip-audit not available in this environment")
        return check

    if result.returncode not in (0, 1):
        check.errors.append(
            f"pip-audit failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    raw = (result.stdout or "").strip()
    json_text = raw
    if raw and not raw.lstrip().startswith(("[", "{")):
        for idx, ch in enumerate(raw):
            if ch in "[{":
                json_text = raw[idx:]
                break
    try:
        payload = json.loads(json_text or "[]")
    except json.JSONDecodeError as exc:
        check.errors.append(f"pip-audit JSON parse error: {exc}")
        return check

    if isinstance(payload, dict):
        items = payload.get("dependencies", []) or []
    elif isinstance(payload, list):
        items = payload
    else:
        items = []

    findings: List[Dict[str, Any]] = []
    for item in items:
        vulns = item.get("vulns") or []
        for vuln in vulns:
            vuln_id = vuln.get("id") or vuln.get("vuln_id")
            severity = (
                (vuln.get("severity") or "")
                or (vuln.get("advisory", {}).get("severity") or "")
            ).lower()
            if severity not in {"high", "critical"}:
                continue
            if vuln_id and vuln_id in allow:
                continue
            findings.append(
                {
                    "package": item.get("name"),
                    "version": item.get("version"),
                    "id": vuln_id,
                    "severity": severity,
                    "fix_versions": vuln.get("fix_versions"),
                }
            )
    check.violations = findings
    check.details["allowlisted"] = sorted(allow)
    return check


def npm_audit_check() -> Check:
    check = Check(
        name="npm_audit",
        title="npm audit (high/critical)",
    )
    allow_path = FRONTEND_DIR / "audit-allowlist.json"
    allow = set()
    if allow_path.exists():
        try:
            data = json.loads(allow_path.read_text(encoding="utf-8"))
            for item in data.get("advisories", []):
                allow.add(str(item))
        except json.JSONDecodeError:
            pass

    cmd = [
        "npm",
        "audit",
        "--omit=dev",
        "--audit-level=high",
        "--json",
    ]
    result = run(cmd, cwd=FRONTEND_DIR, env={"CI": "1"})
    if result.returncode not in (0, 1):
        check.errors.append(
            f"npm audit failed (exit {result.returncode}): {result.stderr.strip()}"
        )

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        check.errors.append(f"npm audit JSON parse error: {exc}")
        return check

    vulnerabilities = payload.get("vulnerabilities", {})
    offenders = []
    for vuln in vulnerabilities.values():
        severity = (vuln.get("severity") or "").lower()
        vuln_id = str(vuln.get("id")) if vuln.get("id") else None
        if severity not in {"high", "critical"}:
            continue
        if vuln_id and vuln_id in allow:
            continue
        offenders.append(
            {
                "id": vuln_id,
                "name": vuln.get("name"),
                "severity": severity,
            }
        )
    check.violations = offenders
    check.details["allowlisted"] = sorted(allow)
    return check


def a11y_info_mode_check() -> Check:
    check = Check(
        name="a11y_smoke",
        title="A11y smoke info-mode",
    )
    path = FRONTEND_DIR / "e2e" / "a11y.smoke.spec.ts"
    if not path.exists():
        check.errors.append("a11y smoke spec not found")
        return check
    content = path.read_text(encoding="utf-8")
    info_mode = "A11Y_STRICT" in content and "fails only when A11Y_STRICT=1" in content
    check.details["info_mode_detected"] = info_mode
    return check


def collect_checks() -> List[Check]:
    return [
        backend_strict_coverage(),
        request_dto_dual_mode(),
        routes_response_model(),
        contract_audit(),
        pin_assert(),
        public_env_full_scan(),
        size_limit_check(),
        pip_audit_check(),
        npm_audit_check(),
        a11y_info_mode_check(),
    ]


def emit_summary(checks: List[Check]) -> None:
    print("=== Guardrail Audit Summary ===")
    for check in checks:
        if check.violations:
            print(f"[FAIL] {check.title}: {len(check.violations)} issue(s)")
            for item in check.violations:
                print(f"  - {item}")
        else:
            print(f"[OK] {check.title}")
        for err in check.errors:
            print(f"  ! error: {err}")
    print()


def main() -> int:
    checks = collect_checks()
    json_output = {check.name: check.to_json() for check in checks}
    print(json.dumps(json_output, indent=2, sort_keys=True))
    print()
    emit_summary(checks)
    failures = any(
        check.violations
        for check in checks
        if check.name not in {"a11y_smoke"}
    )
    return 1 if failures else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
