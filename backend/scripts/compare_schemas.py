#!/usr/bin/env python3
"""Compare database schemas from old vs new migrations."""

from __future__ import annotations

import json
import os
import sys

from sqlalchemy import create_engine, inspect

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings


def get_schema_info(engine):
    """Extract complete schema information."""
    inspector = inspect(engine)
    schema = {
        "tables": {},
        "indexes": {},
        "foreign_keys": {},
        "unique_constraints": {},
        "check_constraints": {},
    }

    for table_name in sorted(inspector.get_table_names()):
        # Columns
        columns = {}
        for col in inspector.get_columns(table_name):
            columns[col["name"]] = {
                "type": str(col["type"]),
                "nullable": col["nullable"],
                "default": str(col.get("default")) if col.get("default") else None,
            }
        schema["tables"][table_name] = columns

        # Primary Key
        pk = inspector.get_pk_constraint(table_name)
        if pk and pk.get("constrained_columns"):
            schema["tables"][table_name]["__pk__"] = sorted(pk["constrained_columns"])

        # Indexes
        for idx in inspector.get_indexes(table_name):
            idx_name = idx["name"]
            column_names = idx.get("column_names") or []
            clean_columns = [name for name in column_names if name is not None]
            schema["indexes"][f"{table_name}.{idx_name}"] = {
                "columns": sorted(clean_columns),
                "unique": idx.get("unique", False),
            }

        # Foreign Keys
        for fk in inspector.get_foreign_keys(table_name):
            fk_name = fk.get("name", f"{table_name}_fk")
            schema["foreign_keys"][f"{table_name}.{fk_name}"] = {
                "columns": sorted(fk["constrained_columns"]),
                "referred_table": fk["referred_table"],
                "referred_columns": sorted(fk["referred_columns"]),
            }

        # Unique Constraints
        for uc in inspector.get_unique_constraints(table_name):
            uc_name = uc.get("name", f"{table_name}_unique")
            schema["unique_constraints"][f"{table_name}.{uc_name}"] = sorted(uc["column_names"])

        # Check Constraints
        try:
            for cc in inspector.get_check_constraints(table_name):
                cc_name = cc.get("name", f"{table_name}_check")
                schema["check_constraints"][f"{table_name}.{cc_name}"] = cc.get("sqltext", "")
        except Exception:
            pass

    return schema


def compare_schemas(old_schema, new_schema):
    """Compare two schemas and report differences."""
    differences = []

    # Compare tables
    old_tables = set(old_schema["tables"].keys())
    new_tables = set(new_schema["tables"].keys())

    missing_tables = old_tables - new_tables
    extra_tables = new_tables - old_tables

    if missing_tables:
        differences.append(f"MISSING TABLES: {sorted(missing_tables)}")
    if extra_tables:
        differences.append(f"EXTRA TABLES: {sorted(extra_tables)}")

    # Compare columns in common tables
    for table in old_tables & new_tables:
        old_cols = set(old_schema["tables"][table].keys())
        new_cols = set(new_schema["tables"][table].keys())

        missing_cols = old_cols - new_cols - {"__pk__"}
        extra_cols = new_cols - old_cols - {"__pk__"}

        if missing_cols:
            differences.append(f"MISSING COLUMNS in {table}: {sorted(missing_cols)}")
        if extra_cols:
            differences.append(f"EXTRA COLUMNS in {table}: {sorted(extra_cols)}")

        # Compare column types
        for col in old_cols & new_cols:
            if col == "__pk__":
                continue
            old_type = old_schema["tables"][table][col]["type"]
            new_type = new_schema["tables"][table][col]["type"]
            if old_type != new_type:
                differences.append(f"TYPE MISMATCH {table}.{col}: {old_type} vs {new_type}")

    # Compare indexes
    old_idx = set(old_schema["indexes"].keys())
    new_idx = set(new_schema["indexes"].keys())

    missing_idx = old_idx - new_idx
    extra_idx = new_idx - old_idx

    if missing_idx:
        differences.append(f"MISSING INDEXES: {sorted(missing_idx)}")
    if extra_idx:
        differences.append(f"EXTRA INDEXES: {sorted(extra_idx)}")

    # Compare foreign keys
    old_fk = set(old_schema["foreign_keys"].keys())
    new_fk = set(new_schema["foreign_keys"].keys())

    missing_fk = old_fk - new_fk
    extra_fk = new_fk - old_fk

    if missing_fk:
        differences.append(f"MISSING FOREIGN KEYS: {sorted(missing_fk)}")
    if extra_fk:
        differences.append(f"EXTRA FOREIGN KEYS: {sorted(extra_fk)}")

    return differences


def main():
    if len(sys.argv) < 2:
        print("Usage: python compare_schemas.py [dump|compare]")
        print("  dump    - Dump current schema to schema.json")
        print("  compare - Compare current schema against schema.json")
        sys.exit(1)

    engine = create_engine(settings.database_url)

    if sys.argv[1] == "dump":
        schema = get_schema_info(engine)
        with open("schema.json", "w") as f:
            json.dump(schema, f, indent=2, sort_keys=True)
        print("Schema dumped to schema.json")
        print(f"  Tables: {len(schema['tables'])}")
        print(f"  Indexes: {len(schema['indexes'])}")
        print(f"  Foreign Keys: {len(schema['foreign_keys'])}")

    elif sys.argv[1] == "compare":
        with open("schema.json") as f:
            old_schema = json.load(f)
        new_schema = get_schema_info(engine)

        differences = compare_schemas(old_schema, new_schema)

        if differences:
            print("❌ SCHEMA DIFFERENCES FOUND:")
            for diff in differences:
                print(f"  - {diff}")
            sys.exit(1)
        print("✅ SCHEMAS MATCH!")
        print(f"  Tables: {len(new_schema['tables'])}")
        print(f"  Indexes: {len(new_schema['indexes'])}")
        print(f"  Foreign Keys: {len(new_schema['foreign_keys'])}")

    else:
        print(f"Unknown command: {sys.argv[1]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
