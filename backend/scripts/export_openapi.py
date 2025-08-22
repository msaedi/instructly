#!/usr/bin/env python3
"""
Export OpenAPI specification from FastAPI application.
This script starts the FastAPI app and exports its OpenAPI schema to a YAML file.
"""

import json
import os
import sys
from pathlib import Path

import yaml

# Add the backend directory to Python path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Set test database to avoid touching production
os.environ["USE_TEST_DATABASE"] = "true"


def export_openapi():
    """Export the OpenAPI specification from FastAPI."""
    # Import the FastAPI app directly
    # fastapi_app is the original FastAPI instance before middleware wrapping
    from app.main import fastapi_app

    # Get the OpenAPI schema
    openapi_schema = fastapi_app.openapi()

    # Output path
    output_path = Path(__file__).parent.parent.parent / "docs" / "api" / "instainstru-openapi.yaml"

    # Ensure the directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to YAML and save
    with open(output_path, "w") as f:
        yaml.dump(openapi_schema, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"✅ OpenAPI specification exported to: {output_path}")
    print(f"📊 Total endpoints: {len(openapi_schema.get('paths', {}))}")

    # Print summary of paths
    paths = openapi_schema.get("paths", {})
    print("\n📋 Endpoint Summary:")
    for path in sorted(paths.keys()):
        methods = list(paths[path].keys())
        print(f"  {path}: {', '.join(methods).upper()}")


if __name__ == "__main__":
    export_openapi()
