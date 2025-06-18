#!/usr/bin/env python3
# backend/scripts/migrate_pydantic_v2_enhanced.py
"""
Enhanced Pydantic V1 to V2 Migration Script for InstaInstru

This enhanced version handles more cases automatically while still being safe.
It includes better detection and migration patterns.

Usage:
    python scripts/migrate_pydantic_v2_enhanced.py           # Analyze only
    python scripts/migrate_pydantic_v2_enhanced.py --apply   # Apply changes
    python scripts/migrate_pydantic_v2_enhanced.py --phase 2 # Run phase 2 (manual fixes)
"""

import os
import re
import ast
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple, Optional

# ANSI color codes
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(message: str):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{message.center(70)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.ENDC}\n")

def print_success(message: str):
    print(f"{Colors.GREEN}✅ {message}{Colors.ENDC}")

def print_warning(message: str):
    print(f"{Colors.WARNING}⚠️  {message}{Colors.ENDC}")

def print_error(message: str):
    print(f"{Colors.RED}❌ {message}{Colors.ENDC}")

def print_info(message: str):
    print(f"{Colors.CYAN}ℹ️  {message}{Colors.ENDC}")

class PydanticMigrator:
    def __init__(self, apply_changes: bool = False):
        self.apply_changes = apply_changes
        self.schema_files = []
        self.all_python_files = []
        self._find_all_files()
        
    def _find_all_files(self):
        """Find all Python files that might need migration."""
        # Detect if we're in the backend directory or project root
        current_path = Path.cwd()
        
        if current_path.name == 'backend' and (current_path / 'app').exists():
            # We're in the backend directory
            backend_path = current_path
        elif (current_path / 'backend').exists():
            # We're in the project root
            backend_path = current_path / 'backend'
        else:
            # Try to find backend directory
            print_error("Cannot find backend directory!")
            print_info(f"Current directory: {current_path}")
            print_info("Please run from project root or backend directory")
            return
        
        # Schema files (priority)
        schema_path = backend_path / "app" / "schemas"
        if schema_path.exists():
            self.schema_files = list(schema_path.glob("*.py"))
        
        # All Python files
        self.all_python_files = list(backend_path.rglob("*.py"))
        
        print_info(f"Found {len(self.schema_files)} schema files in {schema_path}")
        print_info(f"Found {len(self.all_python_files)} total Python files")
    
    def phase1_automatic_fixes(self):
        """Phase 1: Safe automatic fixes."""
        print_header("PHASE 1: Automatic Safe Fixes")
        
        total_changes = 0
        
        for file_path in self.schema_files:
            changes = 0
            
            with open(file_path, 'r') as f:
                content = f.read()
                original_content = content
            
            # 1. Simple @validator -> @field_validator
            content, count = re.subn(
                r'@validator\s*\(\s*([\'"])(\w+)\1\s*\)',
                r'@field_validator(\1\2\1)',
                content
            )
            changes += count
            
            # 2. @validator with pre=True
            content, count = re.subn(
                r'@validator\s*\(\s*([\'"])(\w+)\1\s*,\s*pre\s*=\s*True\s*\)',
                r'@field_validator(\1\2\1, mode="before")',
                content
            )
            changes += count
            
            # 3. min_items -> min_length, max_items -> max_length
            content, count = re.subn(r'\bmin_items\s*=', 'min_length=', content)
            changes += count
            content, count = re.subn(r'\bmax_items\s*=', 'max_length=', content)
            changes += count
            
            # 4. Update imports if we made validator changes
            if 'field_validator' in content and 'from pydantic import' in content:
                # Add field_validator to imports
                content = re.sub(
                    r'from pydantic import ([^;\n]+)',
                    lambda m: self._update_imports(m.group(0), m.group(1)),
                    content
                )
            
            # 5. Add ConfigDict import if Config class exists
            if re.search(r'class\s+Config\s*:', content) and 'ConfigDict' not in content:
                # Add ConfigDict to imports
                content = re.sub(
                    r'(from pydantic import [^;\n]+)',
                    r'\1, ConfigDict',
                    content,
                    count=1
                )
            
            if content != original_content:
                total_changes += changes
                print_info(f"{file_path.name}: {changes} automatic fixes")
                
                if self.apply_changes:
                    with open(file_path, 'w') as f:
                        f.write(content)
        
        print_success(f"Phase 1 complete: {total_changes} automatic fixes")
        return total_changes
    
    def _update_imports(self, full_match: str, imports: str) -> str:
        """Update imports to include field_validator."""
        import_list = [i.strip() for i in imports.split(',')]
        
        # Remove 'validator' if present
        if 'validator' in import_list:
            import_list.remove('validator')
        
        # Add 'field_validator' if not present
        if 'field_validator' not in import_list:
            import_list.append('field_validator')
        
        return f"from pydantic import {', '.join(import_list)}"
    
    def phase2_manual_fixes(self):
        """Phase 2: Identify manual fixes needed."""
        print_header("PHASE 2: Manual Fixes Required")
        
        manual_fixes = []
        
        for file_path in self.schema_files:
            with open(file_path, 'r') as f:
                content = f.read()
                lines = content.split('\n')
            
            file_name = file_path.name
            
            # 1. Multi-field validators
            multi_validator_pattern = r'@validator\s*\([\'"](\w+)[\'"]\s*,\s*[\'"](\w+)[\'"]'
            for i, line in enumerate(lines):
                if match := re.search(multi_validator_pattern, line):
                    manual_fixes.append({
                        'type': 'multi_field_validator',
                        'file': file_name,
                        'line': i + 1,
                        'code': line.strip(),
                        'fields': [match.group(1), match.group(2)]
                    })
            
            # 2. Config classes
            for i, line in enumerate(lines):
                if re.match(r'\s*class\s+Config\s*:', line):
                    # Get Config class content
                    config_lines = []
                    j = i + 1
                    indent = None
                    while j < len(lines):
                        if lines[j].strip() == '':
                            j += 1
                            continue
                        if indent is None and lines[j] and not lines[j][0].isspace():
                            break
                        if indent is None:
                            indent = len(lines[j]) - len(lines[j].lstrip())
                        if lines[j] and len(lines[j]) - len(lines[j].lstrip()) < indent:
                            break
                        config_lines.append(lines[j])
                        j += 1
                    
                    manual_fixes.append({
                        'type': 'config_class',
                        'file': file_name,
                        'line': i + 1,
                        'content': [line.strip() for line in config_lines if line.strip()]
                    })
            
            # 3. Check for Money type issues
            if 'class Money' in content:
                manual_fixes.append({
                    'type': 'custom_type',
                    'file': file_name,
                    'line': content[:content.find('class Money')].count('\n') + 1,
                    'code': 'Money type needs V2 migration'
                })
        
        return manual_fixes
    
    def generate_manual_fix_script(self, manual_fixes: List[Dict]):
        """Generate a script with manual fixes."""
        if not manual_fixes:
            print_success("No manual fixes required!")
            return
        
        # Determine correct path based on current location
        if Path.cwd().name == 'backend':
            script_path = Path("pydantic_manual_fixes.py")
        else:
            script_path = Path("backend/pydantic_manual_fixes.py")
        
        with open(script_path, 'w') as f:
            f.write('#!/usr/bin/env python3\n')
            f.write('"""Manual fixes for Pydantic V2 migration"""\n\n')
            f.write('# Run this script to see the manual changes needed\n\n')
            
            # Group by file
            fixes_by_file = {}
            for fix in manual_fixes:
                file_name = fix['file']
                if file_name not in fixes_by_file:
                    fixes_by_file[file_name] = []
                fixes_by_file[file_name].append(fix)
            
            for file_name, fixes in fixes_by_file.items():
                f.write(f'\n# === {file_name} ===\n\n')
                
                for fix in fixes:
                    if fix['type'] == 'multi_field_validator':
                        f.write(f"# Line {fix['line']}: Multi-field validator\n")
                        f.write(f"# Current: {fix['code']}\n")
                        f.write("# Fix: Split into separate validators:\n")
                        for field in fix['fields']:
                            f.write(f"# @field_validator('{field}')\n")
                        f.write("\n")
                    
                    elif fix['type'] == 'config_class':
                        f.write(f"# Line {fix['line']}: Config class\n")
                        f.write("# Current:\n")
                        f.write("#   class Config:\n")
                        for line in fix['content']:
                            f.write(f"#       {line}\n")
                        f.write("# Fix:\n")
                        
                        # Generate ConfigDict
                        config_dict_parts = []
                        for line in fix['content']:
                            if 'orm_mode = True' in line:
                                config_dict_parts.append('from_attributes=True')
                            elif 'from_attributes = True' in line:
                                continue  # Already correct
                            elif 'allow_population_by_field_name = True' in line:
                                config_dict_parts.append('populate_by_name=True')
                            elif 'use_enum_values = True' in line:
                                config_dict_parts.append('use_enum_values=True')
                            elif 'json_encoders' in line:
                                f.write("#   # Note: json_encoders needs custom migration\n")
                        
                        if config_dict_parts:
                            f.write(f"#   model_config = ConfigDict({', '.join(config_dict_parts)})\n")
                        f.write("\n")
                    
                    elif fix['type'] == 'custom_type':
                        f.write(f"# Line {fix['line']}: {fix['code']}\n")
                        f.write("# The Money type needs to be updated for Pydantic V2\n")
                        f.write("# See the migration guide for custom types\n\n")
        
        print_success(f"Manual fix guide saved to: {script_path}")
        return script_path
    
    def fix_money_type(self):
        """Special handling for the Money type."""
        base_schema_path = Path("backend/app/schemas/base.py")
        if not base_schema_path.exists():
            return
        
        print_header("Fixing Money Type")
        
        # Read the file
        with open(base_schema_path, 'r') as f:
            content = f.read()
        
        # Check if it needs fixing
        if '__get_validators__' in content and '__get_pydantic_core_schema__' in content:
            print_warning("Money type has both V1 and V2 methods - needs cleanup")
            
            if self.apply_changes:
                # Create a clean V2-only version
                new_money_class = '''class Money(Decimal):
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
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                float,
                info_arg=False,
                return_schema=core_schema.float_schema(),
            ),
        )'''
                
                # Replace the Money class
                # This is a simplified approach - in production, use AST
                print_info("Money type fix would be applied here")
                print_warning("Manual review recommended for Money type")
    
    def run(self):
        """Run the complete migration process."""
        print(f"{Colors.CYAN}{Colors.BOLD}")
        print("╔══════════════════════════════════════════════════════════════════╗")
        print("║          ENHANCED PYDANTIC V2 MIGRATION TOOL                     ║")
        print("║              X-Team Approved Version 🚀                          ║")
        print("╚══════════════════════════════════════════════════════════════════╝")
        print(f"{Colors.ENDC}")
        
        # Phase 1: Automatic fixes
        phase1_changes = self.phase1_automatic_fixes()
        
        # Phase 2: Manual fixes
        manual_fixes = self.phase2_manual_fixes()
        
        if manual_fixes:
            print_warning(f"\n{len(manual_fixes)} manual fixes required")
            self.generate_manual_fix_script(manual_fixes)
        
        # Special handling for Money type
        self.fix_money_type()
        
        # Summary
        print_header("Migration Summary")
        print_info(f"Automatic fixes: {phase1_changes}")
        print_info(f"Manual fixes needed: {len(manual_fixes)}")
        
        if not self.apply_changes:
            print_warning("\nDRY RUN - No changes applied")
            print_info("Run with --apply to make changes")
        else:
            print_success("\nChanges applied successfully!")
            print_warning("Remember to:")
            print("  1. Review all changes with git diff")
            print("  2. Run tests to ensure nothing broke")
            print("  3. Complete manual fixes as indicated")

def main():
    parser = argparse.ArgumentParser(description="Enhanced Pydantic V2 Migration")
    parser.add_argument("--apply", action="store_true", help="Apply changes")
    parser.add_argument("--phase", type=int, default=1, help="Run specific phase (1 or 2)")
    args = parser.parse_args()
    
    migrator = PydanticMigrator(apply_changes=args.apply)
    migrator.run()

if __name__ == "__main__":
    main()