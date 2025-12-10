#!/usr/bin/env python3
"""
Pre-commit hook to detect sync blocking calls in async functions.

Catches:
- db.commit/flush/refresh/rollback/query/add/delete in async def
- repository.* calls in async def
- service.* calls in async def (configurable)

All must be wrapped in asyncio.to_thread() or run_in_threadpool().
"""

import ast
from pathlib import Path
import sys
from typing import List, Tuple

# Patterns that block when called synchronously
BLOCKING_PATTERNS = [
    # SQLAlchemy session operations
    "db.commit",
    "db.flush",
    "db.refresh",
    "db.rollback",
    "db.query",
    "db.add",
    "db.delete",
    "db.execute",
    "db.get",
    "session.commit",
    "session.flush",
    "session.refresh",
    "session.rollback",
    "session.query",
    "session.add",
    "session.delete",
    "session.execute",
    # Repository calls
    ".repository.",
    "_repo.",
    "_repository.",
    "repository.get",
    "repository.create",
    "repository.update",
    "repository.delete",
    "repository.find",
]

# Additional patterns to check (service calls) - more prone to false positives
SERVICE_PATTERNS = [
    # Uncomment if you want to catch service calls too
    # "service.",
    # "_service.",
]

# Known safe wrappers
SAFE_WRAPPERS = [
    "asyncio.to_thread",
    "run_in_threadpool",
    "run_in_executor",
    "loop.run_in_executor",
]

# Files/directories to skip
SKIP_PATTERNS = [
    "/tests/",
    "test_",
    "__pycache__",
    "alembic/",
    "migrations/",
]


class AsyncBlockingVisitor(ast.NodeVisitor):
    """AST visitor to find blocking calls in async functions."""

    def __init__(self, filename: str, source_lines: List[str]):
        self.filename = filename
        self.source_lines = source_lines
        self.violations: List[Tuple[int, str, str]] = []
        self.in_async_function = False
        self.async_function_name = ""
        self.safe_wrapper_depth = 0

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        """Enter an async function."""
        old_state = self.in_async_function
        old_name = self.async_function_name
        self.in_async_function = True
        self.async_function_name = node.name
        self.generic_visit(node)
        self.in_async_function = old_state
        self.async_function_name = old_name

    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Enter a sync function - resets async state for nested sync functions."""
        # When entering a nested sync function inside an async function,
        # we should NOT flag blocking calls (they're intentionally sync)
        old_state = self.in_async_function
        old_name = self.async_function_name
        self.in_async_function = False  # Reset - this is a sync function
        self.async_function_name = ""
        self.generic_visit(node)
        self.in_async_function = old_state
        self.async_function_name = old_name

    def visit_Call(self, node: ast.Call):
        """Check function calls for blocking patterns."""
        if not self.in_async_function:
            self.generic_visit(node)
            return

        call_str = self._get_call_string(node)

        # Check if this IS a safe wrapper call
        for wrapper in SAFE_WRAPPERS:
            if wrapper in call_str:
                old_depth = self.safe_wrapper_depth
                self.safe_wrapper_depth += 1
                self.generic_visit(node)
                self.safe_wrapper_depth = old_depth
                return

        # If not inside safe wrapper, check for blocking patterns
        if self.safe_wrapper_depth == 0:
            all_patterns = BLOCKING_PATTERNS + SERVICE_PATTERNS
            for pattern in all_patterns:
                if pattern in call_str:
                    # Get the actual source line for context
                    source_line = ""
                    if 0 < node.lineno <= len(self.source_lines):
                        source_line = self.source_lines[node.lineno - 1].strip()

                    self.violations.append((
                        node.lineno,
                        call_str[:60],
                        f"in async def {self.async_function_name}()",
                        source_line[:80]
                    ))
                    break

        self.generic_visit(node)

    def _get_call_string(self, node: ast.Call) -> str:
        """Convert call node to string representation."""
        try:
            if isinstance(node.func, ast.Attribute):
                parts = []
                current = node.func
                while isinstance(current, ast.Attribute):
                    parts.append(current.attr)
                    current = current.value
                if isinstance(current, ast.Name):
                    parts.append(current.id)
                return ".".join(reversed(parts))
            elif isinstance(node.func, ast.Name):
                return node.func.id
        except Exception:
            pass
        return ""


def should_skip_file(filepath: str) -> bool:
    """Check if file should be skipped."""
    for pattern in SKIP_PATTERNS:
        if pattern in filepath:
            return True
    return False


def check_file(filepath: Path) -> List[Tuple[str, int, str, str, str]]:
    """Check a single file for async blocking violations."""
    violations = []

    if should_skip_file(str(filepath)):
        return violations

    try:
        content = filepath.read_text()
        source_lines = content.splitlines()
        tree = ast.parse(content)

        visitor = AsyncBlockingVisitor(str(filepath), source_lines)
        visitor.visit(tree)

        for line, call, context, source in visitor.violations:
            violations.append((str(filepath), line, call, context, source))

    except SyntaxError as e:
        print(f"Warning: Syntax error in {filepath}: {e}", file=sys.stderr)
    except Exception as e:
        print(f"Warning: Error processing {filepath}: {e}", file=sys.stderr)

    return violations


def main():
    """Main entry point."""
    all_violations = []

    # Get files from command line (pre-commit passes changed files)
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:] if f.endswith('.py')]
    else:
        # Check all files in backend/app
        files = list(Path("backend/app").rglob("*.py"))

    for filepath in files:
        violations = check_file(filepath)
        all_violations.extend(violations)

    if all_violations:
        print("\n" + "=" * 60)
        print("ASYNC BLOCKING VIOLATIONS FOUND")
        print("=" * 60)
        print("\nSync DB/repo calls in async functions must be wrapped in asyncio.to_thread()\n")

        for filepath, line, call, context, source in all_violations:
            print(f"  {filepath}:{line}")
            print(f"    Call: {call}")
            print(f"    Context: {context}")
            print(f"    Source: {source}")
            print()

        print(f"{'='*60}")
        print(f"Total violations: {len(all_violations)}")
        print(f"{'='*60}")
        print("\nFix options:")
        print("  1. Wrap in: await asyncio.to_thread(sync_function, args)")
        print("  2. Move DB logic to service layer with self.transaction()")
        print("  3. Add # async-blocking-ignore comment if intentional")
        sys.exit(1)

    print("No async blocking violations found")
    sys.exit(0)


if __name__ == "__main__":
    main()
