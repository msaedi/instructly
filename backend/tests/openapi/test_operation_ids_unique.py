from app.main import fastapi_app as app


def test_all_openapi_operation_ids_are_unique():
    doc = app.openapi()
    paths = doc.get("paths", {})
    op_ids = []

    for methods in paths.values():
        for method, spec in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "options", "head"}:
                continue
            opid = spec.get("operationId")
            assert opid, f"Missing operationId for {method.upper()} {spec.get('summary', '')}"
            op_ids.append(opid)

    duplicates = {opid for opid in op_ids if op_ids.count(opid) > 1}
    assert not duplicates, f"Duplicate operationIds: {sorted(duplicates)}"
