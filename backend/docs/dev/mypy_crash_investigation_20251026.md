# mypy crash investigation — 20251026

## Versions
- `./venv/bin/mypy --version`: `mypy 1.11.2 (compiled: yes)`
- `python -V`: `Python 3.12.7`

## Minimal crashing file(s)
- `python scripts/dev/mypy_bisect.py app/core app/models app/notifications app/repositories app/routes app/services app/tasks app/templates app/utils`
  - Result: `CRASH FILE: app/core/production_startup.py`
- `./scripts/dev/mypy_shadow_confirm.sh app/core/production_startup.py`
  - Replacing this file with an inert stub removes the placeholder crash (mypy now exits because of standard type errors such as missing `ProductionStartup` attributes).

## Failing mypy output (tail)
```
    main()
  File "mypy/main.py", line 103, in main
  File "mypy/main.py", line 187, in run_build
  File "mypy/build.py", line 193, in build
  File "mypy/build.py", line 268, in _build
  File "mypy/build.py", line 2950, in dispatch
  File "mypy/build.py", line 3348, in process_graph
  File "mypy/build.py", line 3475, in process_stale_scc
  File "mypy/build.py", line 2507, in write_cache
  File "mypy/build.py", line 1568, in write_cache
  File "mypy/nodes.py", line 390, in serialize
  File "mypy/nodes.py", line 4012, in serialize
  File "mypy/nodes.py", line 3949, in serialize
  File "mypy/nodes.py", line 3374, in serialize
  File "mypy/types.py", line 668, in serialize
  File "mypy/types.py", line 2461, in serialize
  File "mypy/types.py", line 1484, in serialize
  File "mypy/types.py", line 668, in serialize
  File "mypy/types.py", line 3117, in serialize
AssertionError: Internal error: unresolved placeholder type None
```

## Notes / next steps
- `app/core/production_startup.py` defines nested classes (e.g., `StructuredFormatter`) and global singletons (`ServiceCircuitBreaker`, `circuit_breakers`) without explicit typing; forward references to logging types and dynamic imports may leave mypy with placeholder symbols when serializing.
- The module relies on runtime-only imports (SQLAlchemy engine, Redis clients, monitoring helpers) inside async methods, which can confuse mypy when strict optional + plugin settings build its type graph.
- There is no `from __future__ import annotations`, so annotations that reference classes defined later in the file (or from lazy imports) stay as runtime objects rather than deferred strings, increasing the risk of placeholder leakage.

Next step is to inspect this file for problematic aliases (e.g., `TypeAlias = None`), forward/cyclic references, or SQLAlchemy `Mapped[...]` forward refs and propose localized typing fixes only.
