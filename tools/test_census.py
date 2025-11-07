#!/usr/bin/env python3
"""Count tests by parsing AST across git baselines."""
import ast
import json
import subprocess
import sys
from pathlib import Path

ROOTS = ["backend/tests"]


def git_ls(commit, path):
    """List Python files in a path at a commit."""
    try:
        out = subprocess.check_output(
            ["git", "ls-tree", "-r", "--name-only", commit, path],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return [p for p in out.splitlines() if p.endswith(".py")]
    except subprocess.CalledProcessError:
        return []


def git_show(commit, path):
    """Read file contents from a commit."""
    try:
        return subprocess.check_output(
            ["git", "show", f"{commit}:{path}"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return ""


def read_working(path):
    """Read file from working directory."""
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def parametrize_cases(dec):
    """Count parameter cases from a parametrize decorator."""
    # dec is ast.Call (pytest.mark.parametrize(...))
    try:
        if not isinstance(dec, ast.Call) or not dec.args:
            return 1
        if len(dec.args) >= 2:
            vals = dec.args[1]
            if isinstance(vals, (ast.List, ast.Tuple)):
                # Count elements in the list/tuple
                count = sum(1 for elt in vals.elts)
                return max(1, count)
            # Check for pytest.param(...) calls
            if isinstance(vals, ast.Call):
                # If it's a list comprehension or generator, hard to count statically
                # Return 1 as fallback
                return 1
        return 1
    except Exception:
        return 1


def node_has_parametrize(decos):
    """Yield parametrize decorators from a decorator list."""
    for d in decos:
        if isinstance(d, ast.Call):
            f = d.func
            names = []
            while isinstance(f, ast.Attribute):
                names.append(f.attr)
                f = f.value
            if isinstance(f, ast.Name):
                names.append(f.id)
            dotted = ".".join(reversed(names))
            if (
                dotted.endswith("pytest.mark.parametrize")
                or dotted.endswith("mark.parametrize")
                or "parametrize" in dotted
            ):
                yield d


def count_tests_from_source(src):
    """Count test functions in source code."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError):
        return 0

    total = 0

    def count_function(fn: ast.FunctionDef):
        """Count a single function, handling parametrize."""
        base = 1 if fn.name.startswith("test_") else 0
        if base == 0:
            return 0

        mult = 1
        if fn.decorator_list:
            for dec in node_has_parametrize(fn.decorator_list):
                mult *= max(1, parametrize_cases(dec))

        return base * mult

    for n in tree.body:
        if isinstance(n, ast.FunctionDef):
            total += count_function(n)
        elif isinstance(n, ast.ClassDef) and n.name.startswith("Test"):
            for m in n.body:
                if isinstance(m, ast.FunctionDef):
                    total += count_function(m)

    return total


def bucket(path):
    """Assign a file to a bucket based on its path."""
    p = Path(path)
    parts = p.parts

    # Return top bucket
    if "integration" in parts and "repository_patterns" in parts:
        return "repo_patterns"
    if "integration" in parts:
        return "integration"
    if "unit" in parts:
        return "unit"
    if "routes" in parts:
        return "routes"
    if "repositories" in parts:
        return "repositories"
    if "scripts" in parts:
        return "scripts"
    return "other"


def main():
    """Main entry point."""
    baseline = sys.argv[1] if len(sys.argv) > 1 else "working"
    if baseline not in {"stable", "head", "working"}:
        print("usage: test_census.py [stable|head|working]", file=sys.stderr)
        sys.exit(2)

    if baseline == "stable":
        commit = "a1c0b6fc77a4bfc3ac1d092a7b062d04051ba341"
        reader = lambda path: git_show(commit, path)
        files = []
        for r in ROOTS:
            files += git_ls(commit, r)
    elif baseline == "head":
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
        reader = lambda path: git_show(commit, path)
        files = []
        for r in ROOTS:
            files += git_ls(commit, r)
    else:  # working
        reader = read_working
        files = [str(p) for root in ROOTS for p in Path(root).rglob("*.py")]

    counts = {"total": 0, "by_bucket": {}, "by_file": {}}

    for f in files:
        try:
            src = reader(f)
            if not src:
                continue
        except (subprocess.CalledProcessError, FileNotFoundError, OSError):
            # file may not exist in that commit
            continue

        n = count_tests_from_source(src)
        if n > 0:
            counts["total"] += n
            b = bucket(f)
            counts["by_bucket"][b] = counts["by_bucket"].get(b, 0) + n
            counts["by_file"][f] = n

    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
