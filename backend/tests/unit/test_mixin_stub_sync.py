"""Guard against drift between TYPE_CHECKING stubs and facade method signatures."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import inspect
from pathlib import Path
from typing import Iterable

import pytest

from app.services.availability_service import AvailabilityService
from app.services.instructor_service import InstructorService

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

_ALIAS_NAMES = {
    "Dict": "dict",
    "FrozenSet": "frozenset",
    "List": "list",
    "Set": "set",
    "Tuple": "tuple",
    "Type": "type",
}


@dataclass(frozen=True)
class ParamShape:
    name: str
    kind: str
    annotation: str | None
    has_default: bool


@dataclass(frozen=True)
class SignatureShape:
    method_name: str
    is_async: bool
    params: tuple[ParamShape, ...]
    return_annotation: str | None


@dataclass(frozen=True)
class MethodNodeRef:
    owner_name: str
    path: Path
    node: ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class StubSyncCase:
    mixin_path: Path
    mixin_class_name: str
    facade_class: type[object]


CASES = (
    StubSyncCase(
        mixin_path=REPO_ROOT / "backend/app/services/availability/mixin_base.py",
        mixin_class_name="AvailabilityMixinBase",
        facade_class=AvailabilityService,
    ),
    StubSyncCase(
        mixin_path=REPO_ROOT / "backend/app/services/instructor/mixin_base.py",
        mixin_class_name="InstructorMixinBase",
        facade_class=InstructorService,
    ),
)


def _module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _find_top_level_class(module: ast.Module, class_name: str) -> ast.ClassDef:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise AssertionError(f"Could not find class {class_name} in {module}")


def _is_type_checking_test(node: ast.expr) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "TYPE_CHECKING"
    return False


def _iter_type_checking_methods(
    class_node: ast.ClassDef,
) -> Iterable[ast.FunctionDef | ast.AsyncFunctionDef]:
    for item in class_node.body:
        if not isinstance(item, ast.If) or not _is_type_checking_test(item.test):
            continue
        for stubbed in item.body:
            if isinstance(stubbed, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield stubbed


def _flatten_union(node: ast.AST) -> list[str]:
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _flatten_union(node.left) + _flatten_union(node.right)
    normalized = _normalize_annotation(node)
    return [normalized] if normalized else []


def _normalize_union(parts: Iterable[str]) -> str:
    unique_parts = sorted({part for part in parts if part})
    return " | ".join(unique_parts)


def _normalize_annotation(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            parsed = ast.parse(node.value, mode="eval")
        except SyntaxError:
            return node.value.replace(" ", "")
        return _normalize_annotation(parsed.body)
    if isinstance(node, ast.Name):
        return _ALIAS_NAMES.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        value = _normalize_annotation(node.value)
        attr = _ALIAS_NAMES.get(node.attr, node.attr)
        if value == "typing":
            return attr
        return f"{value}.{attr}" if value else attr
    if isinstance(node, ast.Subscript):
        base = _normalize_annotation(node.value)
        args = _normalize_subscript_args(node.slice)
        if base == "Optional" and len(args) == 1:
            return _normalize_union((args[0], "None"))
        if base == "Union":
            return _normalize_union(args)
        return f"{base}[{', '.join(args)}]"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _normalize_union(_flatten_union(node))
    return ast.unparse(node).replace(" ", "")


def _normalize_subscript_args(slice_node: ast.AST) -> list[str]:
    if isinstance(slice_node, ast.Tuple):
        return [value for value in (_normalize_annotation(elt) for elt in slice_node.elts) if value]
    normalized = _normalize_annotation(slice_node)
    return [normalized] if normalized else []


def _parameter_shapes(
    args: ast.arguments,
) -> tuple[ParamShape, ...]:
    shapes: list[ParamShape] = []
    positional = [("posonly", arg) for arg in args.posonlyargs]
    positional.extend(("arg", arg) for arg in args.args)
    positional_defaults = [False] * (len(positional) - len(args.defaults)) + [True] * len(args.defaults)

    for (kind, arg), has_default in zip(positional, positional_defaults):
        shapes.append(
            ParamShape(
                name=arg.arg,
                kind=kind,
                annotation=_normalize_annotation(arg.annotation),
                has_default=has_default,
            )
        )

    if args.vararg is not None:
        shapes.append(
            ParamShape(
                name=args.vararg.arg,
                kind="vararg",
                annotation=_normalize_annotation(args.vararg.annotation),
                has_default=False,
            )
        )

    for kwarg, default in zip(args.kwonlyargs, args.kw_defaults):
        shapes.append(
            ParamShape(
                name=kwarg.arg,
                kind="kwonly",
                annotation=_normalize_annotation(kwarg.annotation),
                has_default=default is not None,
            )
        )

    if args.kwarg is not None:
        shapes.append(
            ParamShape(
                name=args.kwarg.arg,
                kind="kwarg",
                annotation=_normalize_annotation(args.kwarg.annotation),
                has_default=False,
            )
        )

    return tuple(shapes)


def _signature_shape(node: ast.FunctionDef | ast.AsyncFunctionDef) -> SignatureShape:
    return SignatureShape(
        method_name=node.name,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        params=_parameter_shapes(node.args),
        return_annotation=_normalize_annotation(node.returns),
    )


def _collect_facade_methods(facade_class: type[object]) -> dict[str, MethodNodeRef]:
    methods: dict[str, MethodNodeRef] = {}
    for owner in facade_class.__mro__:
        if owner is object:
            continue
        source_path = inspect.getsourcefile(owner)
        if source_path is None:
            continue
        path = Path(source_path)
        module = _module_ast(path)
        class_node = _find_top_level_class(module, owner.__name__)
        for item in class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name not in methods:
                methods[item.name] = MethodNodeRef(owner_name=owner.__name__, path=path, node=item)
    return methods


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.mixin_class_name)
def test_type_checking_stub_signatures_match_facade(case: StubSyncCase) -> None:
    mixin_module = _module_ast(case.mixin_path)
    mixin_class = _find_top_level_class(mixin_module, case.mixin_class_name)
    stub_methods = {node.name: node for node in _iter_type_checking_methods(mixin_class)}
    facade_methods = _collect_facade_methods(case.facade_class)

    missing = sorted(name for name in stub_methods if name not in facade_methods)
    assert not missing, (
        f"{case.mixin_class_name} stub methods missing from {case.facade_class.__name__}: {missing}"
    )

    mismatches: list[str] = []
    for name, stub_node in stub_methods.items():
        actual = facade_methods[name]
        stub_shape = _signature_shape(stub_node)
        actual_shape = _signature_shape(actual.node)
        if stub_shape != actual_shape:
            actual_path = actual.path.relative_to(REPO_ROOT)
            mismatches.append(
                f"{name}: stub={stub_shape} actual={actual_shape} "
                f"(owner={actual.owner_name}, path={actual_path})"
            )

    assert not mismatches, (
        f"{case.mixin_class_name} TYPE_CHECKING stubs drifted from "
        f"{case.facade_class.__name__}:\n" + "\n".join(mismatches)
    )
