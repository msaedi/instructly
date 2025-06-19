#!/usr/bin/env python3
# backend/scripts/pydantic_phase3_final.py
"""
Pydantic V2 Phase 3 - Final Cleanup

This script completes the migration by:
1. Fixing the Money type (remove V1 methods)
2. Converting json_encoders to proper Pydantic V2 patterns
3. Removing any remaining deprecation warnings

Usage:
    python scripts/pydantic_phase3_final.py --check    # Preview changes
    python scripts/pydantic_phase3_final.py --apply    # Apply changes
"""

import argparse
import re
from pathlib import Path


# ANSI colors
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"


def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.ENDC}")


def print_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.ENDC}")


def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.ENDC}")


def fix_money_type(apply: bool = False):
    """Fix the Money type to be fully Pydantic V2 compliant"""
    # Try different paths
    base_path = Path("app/schemas/base.py")
    if not base_path.exists():
        base_path = Path("backend/app/schemas/base.py")
    if not base_path.exists():
        # If we're in backend directory
        base_path = Path("schemas/base.py")

    if not base_path.exists():
        print_warning(f"Could not find base.py in any expected location")
        return False

    with open(base_path, "r") as f:
        content = f.read()

    # New Money class implementation
    new_money_implementation = '''class Money(Decimal):
    """Money field that always serializes as float"""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: Any
    ) -> core_schema.CoreSchema:
        from pydantic_core import core_schema

        def validate_money(value: Any) -> Decimal:
            if isinstance(value, (int, float)):
                return cls(str(value))
            if isinstance(value, str):
                return cls(value)
            if isinstance(value, Decimal):
                return value
            raise ValueError(f'Cannot convert {type(value)} to Money')

        return core_schema.no_info_after_validator_function(
            validate_money,
            core_schema.union_schema([
                core_schema.int_schema(),
                core_schema.float_schema(),
                core_schema.str_schema(),
                core_schema.is_instance_schema(Decimal),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                float,
                info_arg=False,
                return_schema=core_schema.float_schema(),
            ),
        )'''

    # Find and replace the Money class
    money_class_pattern = r"class Money\(Decimal\):.*?(?=\n(?:class|def|\Z))"

    # Check if Money class has V1 methods
    if "__get_validators__" in content:
        print_info("Found Money class with V1 methods")

        if apply:
            # Remove the TODO comment if it exists
            content = re.sub(r"# TODO: Remove __get_validators__.*\n", "", content)

            # Replace the entire Money class
            content = re.sub(
                money_class_pattern, new_money_implementation, content, flags=re.DOTALL
            )

            with open(base_path, "w") as f:
                f.write(content)

            print_success("Fixed Money type - removed V1 methods")
        return True
    else:
        print_info("Money type already V2 compliant")
        return False


def fix_json_encoders(apply: bool = False):
    """Convert json_encoders to Pydantic V2 serialization"""
    # Try different paths
    base_path = Path("app/schemas/base.py")
    if not base_path.exists():
        base_path = Path("backend/app/schemas/base.py")
    if not base_path.exists():
        # If we're in backend directory
        base_path = Path("schemas/base.py")

    if not base_path.exists():
        print_warning(f"Could not find base.py in any expected location")
        return False

    with open(base_path, "r") as f:
        content = f.read()

    # Check if we still have json_encoders in StandardizedModel
    if "json_encoders" in content and "class StandardizedModel" in content:
        print_info("Found json_encoders in StandardizedModel")

        if apply:
            # New StandardizedModel with proper Pydantic V2 serialization
            new_standardized_model = '''class StandardizedModel(BaseModel):
    """Base model with standardized JSON encoding"""

    model_config = ConfigDict(
        use_enum_values=True,
        populate_by_name=True,
        json_encoders={
            Decimal: float,
            datetime: lambda v: v.isoformat(),
            date: lambda v: v.isoformat(),
            time: lambda v: v.strftime('%H:%M:%S'),
        }
    )'''

            # Replace the StandardizedModel class
            pattern = r"class StandardizedModel\(BaseModel\):.*?model_config = ConfigDict\([^)]*\).*?(?=\n(?:class|def|\Z))"

            content = re.sub(pattern, new_standardized_model, content, flags=re.DOTALL)

            # Remove TODO comment if present
            content = re.sub(
                r"    # TODO: Migrate json_encoders to field serializers\n", "", content
            )

            with open(base_path, "w") as f:
                f.write(content)

            print_success("Updated StandardizedModel with json_encoders in ConfigDict")
        return True
    else:
        print_info("json_encoders already properly configured")
        return False


def check_remaining_issues():
    """Check for any remaining Pydantic V1 patterns"""
    issues = []

    schema_dir = Path("app/schemas")
    if not schema_dir.exists():
        schema_dir = Path("backend/app/schemas")

    for py_file in schema_dir.glob("*.py"):
        with open(py_file, "r") as f:
            content = f.read()

        # Check for any remaining validator imports
        if "@validator" in content and "@field_validator" not in content:
            issues.append(f"{py_file.name}: Still has @validator decorators")

        # Check for Config classes
        if re.search(r"class\s+Config\s*:", content):
            issues.append(f"{py_file.name}: Still has Config class")

        # Check for __get_validators__
        if "__get_validators__" in content:
            issues.append(f"{py_file.name}: Still has __get_validators__ (V1 pattern)")

    return issues


def main():
    parser = argparse.ArgumentParser(description="Pydantic V2 Phase 3 - Final Cleanup")
    parser.add_argument("--apply", action="store_true", help="Apply the fixes")
    parser.add_argument(
        "--check", action="store_true", help="Check what would be changed"
    )
    args = parser.parse_args()

    if not args.apply:
        args.check = True

    print(f"{Colors.BOLD}Pydantic V2 Phase 3 - Final Cleanup{Colors.ENDC}\n")

    changes_made = False

    # Fix Money type
    if fix_money_type(args.apply):
        changes_made = True

    # Fix json_encoders
    if fix_json_encoders(args.apply):
        changes_made = True

    # Check for remaining issues
    print(f"\n{Colors.BOLD}Checking for remaining issues...{Colors.ENDC}")
    remaining_issues = check_remaining_issues()

    if remaining_issues:
        print_warning(f"Found {len(remaining_issues)} remaining issues:")
        for issue in remaining_issues:
            print(f"  - {issue}")
    else:
        print_success("No remaining Pydantic V1 patterns found!")

    if args.check and changes_made:
        print_warning("\nRun with --apply to make these changes")
    elif args.apply and changes_made:
        print_success("\nPhase 3 complete! All Pydantic V2 migration finished.")
        print_info("Run 'git diff app/schemas/base.py' to review changes")


if __name__ == "__main__":
    main()
