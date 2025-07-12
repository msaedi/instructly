#!/usr/bin/env python3
"""
Generate TypeScript interfaces from Pydantic schemas for InstaInstru API.

This script reads all Pydantic schemas and generates corresponding TypeScript
interfaces to ensure type safety between backend and frontend.

Usage:
    python generate_types.py > ../frontend/src/types/api.ts
"""

import ast
import os
from typing import List, Tuple

# Mapping of Python types to TypeScript types
PYTHON_TO_TS_TYPES = {
    "str": "string",
    "int": "number",
    "float": "number",
    "bool": "boolean",
    "date": "string",  # ISO date string
    "datetime": "string",  # ISO datetime string
    "time": "string",  # Time string HH:MM:SS
    "Decimal": "number",
    "Any": "any",
    "EmailStr": "string",
    "SecretStr": "string",
    # Type aliases used in schemas
    "DateType": "string",  # ISO date string
    "TimeType": "string",  # Time string HH:MM:SS
    "DateTimeType": "string",  # ISO datetime string
    # Custom types
    "Money": "number",  # Money type that serializes as float
    "dict": "Record<string, any>",  # Python dict type
}

# Enums to generate
ENUMS = {
    "UserRole": ["student", "instructor"],
    "BookingStatus": ["PENDING", "CONFIRMED", "COMPLETED", "CANCELLED", "NO_SHOW"],
    "LocationType": ["student_home", "instructor_location", "neutral"],
}


def get_schemas_directory() -> str:
    """Get the path to the schemas directory."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "schemas")


def find_pydantic_classes(file_path: str) -> List[Tuple[str, ast.ClassDef]]:
    """Find all Pydantic model classes in a file."""
    with open(file_path, "r") as f:
        content = f.read()
        tree = ast.parse(content)

    classes = []
    # Also look for type aliases in the file

    for node in ast.walk(tree):
        # Find type aliases like DateType = datetime.date
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ["DateType", "TimeType", "DateTimeType"]:
                    # These are already handled in PYTHON_TO_TS_TYPES
                    pass

        if isinstance(node, ast.ClassDef):
            # Check if it inherits from BaseModel or StandardizedModel
            for base in node.bases:
                base_name = ""
                if isinstance(base, ast.Name):
                    base_name = base.id
                elif isinstance(base, ast.Attribute):
                    base_name = base.attr

                if base_name in ["BaseModel", "StandardizedModel"]:
                    classes.append((node.name, node))
                    break

    return classes


def get_field_type(annotation: ast.AST) -> str:
    """Convert Python type annotation to TypeScript type."""
    if isinstance(annotation, ast.Name):
        return PYTHON_TO_TS_TYPES.get(annotation.id, annotation.id)

    elif isinstance(annotation, ast.Subscript):
        # Handle Optional[T], List[T], etc.
        if isinstance(annotation.value, ast.Name):
            origin = annotation.value.id

            if origin == "Optional":
                inner_type = get_field_type(annotation.slice)
                return f"{inner_type} | null"

            elif origin == "List":
                inner_type = get_field_type(annotation.slice)
                return f"{inner_type}[]"

            elif origin == "Dict":
                if isinstance(annotation.slice, ast.Tuple):
                    key_type = get_field_type(annotation.slice.elts[0])
                    value_type = get_field_type(annotation.slice.elts[1])
                    return f"Record<{key_type}, {value_type}>"
                return "Record<string, any>"

            elif origin == "Literal":
                # Handle Literal types
                if isinstance(annotation.slice, ast.Constant):
                    return f'"{annotation.slice.value}"'
                return "string"

    elif isinstance(annotation, ast.Constant):
        # Handle string literals
        return f'"{annotation.value}"'

    elif isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        # Handle Union types (Type1 | Type2)
        left_type = get_field_type(annotation.left)
        right_type = get_field_type(annotation.right)
        return f"{left_type} | {right_type}"

    return "any"


def extract_fields(class_def: ast.ClassDef) -> List[Tuple[str, str, bool]]:
    """Extract fields from a Pydantic model class."""
    fields = []

    for node in class_def.body:
        # Handle annotated assignments (field: Type = ...)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            field_name = node.target.id
            field_type = get_field_type(node.annotation)

            # Check if field is required (no default value)
            is_required = node.value is None

            # Check for Field(...) with default
            if node.value and isinstance(node.value, ast.Call):
                if hasattr(node.value.func, "id") and node.value.func.id == "Field":
                    # Check if default is provided
                    for keyword in node.value.keywords:
                        if keyword.arg == "default":
                            is_required = False
                            break
                    else:
                        # Check if it's Field(...)  without default
                        if node.value.args and isinstance(node.value.args[0], ast.Constant):
                            if node.value.args[0].value == ...:
                                is_required = True

            fields.append((field_name, field_type, is_required))

    return fields


def generate_typescript_interface(class_name: str, fields: List[Tuple[str, str, bool]], is_missing=False) -> str:
    """Generate TypeScript interface from class name and fields."""
    lines = [f"export interface {class_name} {{"]

    for field_name, field_type, is_required in fields:
        optional = "" if is_required else "?"
        lines.append(f"  {field_name}{optional}: {field_type};")

    lines.append("}")
    return "\n".join(lines)


def generate_typescript_enum(enum_name: str, values: List[str]) -> str:
    """Generate TypeScript enum."""
    lines = [f"export enum {enum_name} {{"]

    for value in values:
        # For string enums
        lines.append(f"  {value.upper()} = '{value}',")

    lines.append("}")
    return "\n".join(lines)


def main():
    """Main function to generate TypeScript types."""
    schemas_dir = get_schemas_directory()

    # Collect all interfaces

    # First, generate enums
    print("// Generated TypeScript types for InstaInstru API")
    print("// DO NOT EDIT - This file is auto-generated from Pydantic schemas")
    print()
    print("// Enums")

    for enum_name, values in ENUMS.items():
        print(generate_typescript_enum(enum_name, values))
        print()

    print("// Interfaces")
    print()

    # Track all defined interfaces
    defined_interfaces = set()

    # Process each schema file
    schema_files = [f for f in os.listdir(schemas_dir) if f.endswith(".py") and f != "__init__.py"]

    for schema_file in sorted(schema_files):
        file_path = os.path.join(schemas_dir, schema_file)
        classes = find_pydantic_classes(file_path)

        if classes:
            print(f"// From {schema_file}")

            for class_name, class_def in classes:
                # Skip certain classes
                if class_name in ["StandardizedModel", "BaseModel", "Money"]:
                    continue

                fields = extract_fields(class_def)
                if fields:
                    print(generate_typescript_interface(class_name, fields))
                    print()
                    defined_interfaces.add(class_name)

    # Add utility types
    print("// Utility Types")
    print()
    print("export type ApiResponse<T> = {")
    print("  data: T;")
    print("  error?: never;")
    print("} | {")
    print("  data?: never;")
    print("  error: ErrorResponse;")
    print("};")
    print()
    print("export interface PaginatedResponse<T> {")
    print("  items: T[];")
    print("  total: number;")
    print("  page: number;")
    print("  per_page: number;")
    print("  total_pages: number;")
    print("}")
    print()
    print("export interface ErrorResponse {")
    print("  detail: string;")
    print("  code?: string;")
    print("  field?: string;")
    print("}")
    print()
    print("export interface RateLimitError {")
    print("  detail: {")
    print("    message: string;")
    print("    code: 'RATE_LIMIT_EXCEEDED';")
    print("    retry_after: number;")
    print("  };")
    print("}")
    print()

    # Add authentication helpers
    print("// Authentication Types")
    print()
    print("export interface AuthToken {")
    print("  access_token: string;")
    print("  token_type: 'bearer';")
    print("}")
    print()
    print("export interface AuthHeaders {")
    print("  Authorization: string;")
    print("}")
    print()
    print("export function getAuthHeaders(token: string): AuthHeaders {")
    print("  return {")
    print("    Authorization: `Bearer ${token}`")
    print("  };")
    print("}")
    print()

    # Add custom type aliases
    print("// Custom Type Aliases")
    print("export type Money = number;  // Monetary values (serialized as float)")
    print("export type DateType = string;  // ISO date string (YYYY-MM-DD)")
    print("export type TimeType = string;  // Time string (HH:MM:SS)")
    print("export type DateTimeType = string;  // ISO datetime string")
    print()

    # Check for missing interfaces that are referenced but not defined
    # Common missing interfaces based on the errors
    missing_interfaces = {
        "ServiceCreate": [
            ("skill", "string", True),
            ("hourly_rate", "Money", True),
            ("description", "string | null", False),
            ("duration_override", "number | null", False),
        ],
        "ServiceResponse": [
            ("id", "number", True),
            ("skill", "string", True),
            ("hourly_rate", "Money", True),
            ("description", "string | null", False),
            ("duration_override", "number | null", False),
            ("duration", "number", True),
        ],
        "BookingResponse": [
            ("id", "number", True),
            ("student_id", "number", True),
            ("instructor_id", "number", True),
            ("service_id", "number", True),
            ("booking_date", "string", True),
            ("start_time", "string", True),
            ("end_time", "string", True),
            ("service_name", "string", True),
            ("hourly_rate", "Money", True),
            ("total_price", "Money", True),
            ("duration_minutes", "number", True),
            ("status", "BookingStatus", True),
            ("service_area", "string | null", False),
            ("meeting_location", "string | null", False),
            ("location_type", "string | null", False),
            ("student_note", "string | null", False),
            ("instructor_note", "string | null", False),
            ("created_at", "string", True),
            ("confirmed_at", "string | null", False),
            ("completed_at", "string | null", False),
            ("cancelled_at", "string | null", False),
            ("cancelled_by_id", "number | null", False),
            ("cancellation_reason", "string | null", False),
            ("student", "StudentInfo", False),
            ("instructor", "InstructorInfo", False),
            ("service", "ServiceInfo", False),
        ],
        "InstructorProfileCreate": [
            ("bio", "string", True),
            ("areas_of_service", "string[]", True),
            ("years_experience", "number", True),
            ("min_advance_booking_hours", "number", False),
            ("buffer_time_minutes", "number", False),
            ("services", "ServiceCreate[]", True),
        ],
        "InstructorProfileResponse": [
            ("id", "number", True),
            ("user_id", "number", True),
            ("created_at", "string", True),
            ("updated_at", "string | null", False),
            ("user", "UserBasic", True),
            ("services", "ServiceResponse[]", True),
            ("bio", "string", True),
            ("areas_of_service", "string[]", True),
            ("years_experience", "number", True),
            ("min_advance_booking_hours", "number", False),
            ("buffer_time_minutes", "number", False),
        ],
    }

    print("// Missing Interfaces (manually added)")
    print()
    for interface_name, fields in missing_interfaces.items():
        if interface_name not in defined_interfaces:
            print(generate_typescript_interface(interface_name, fields))
            print()
    print("// Date/Time Helpers")
    print()
    print("export function formatDate(date: Date): DateType {")
    print("  return date.toISOString().split('T')[0];")
    print("}")
    print()
    print("export function formatTime(date: Date): TimeType {")
    print("  return date.toTimeString().split(' ')[0];")
    print("}")
    print()
    print("export function parseTime(timeStr: TimeType): Date {")
    print("  const [hours, minutes, seconds] = timeStr.split(':').map(Number);")
    print("  const date = new Date();")
    print("  date.setHours(hours, minutes, seconds || 0, 0);")
    print("  return date;")
    print("}")
    print()
    print("export function parseDate(dateStr: DateType): Date {")
    print("  return new Date(dateStr + 'T00:00:00');")
    print("}")
    print()
    print("export function parseDateTime(dateTimeStr: DateTimeType): Date {")
    print("  return new Date(dateTimeStr);")
    print("}")


if __name__ == "__main__":
    main()
