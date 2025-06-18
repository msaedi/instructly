#!/usr/bin/env python3
# backend/scripts/pydantic_phase2_manual_fixes.py
"""
Pydantic V2 Phase 2 - Manual Fixes Implementation

This script applies the manual fixes that couldn't be done automatically.
It handles:
1. Config class conversions
2. Multi-field validator splitting
3. Money type cleanup
4. json_encoders migration

Usage:
    python scripts/pydantic_phase2_manual_fixes.py --check    # Preview changes
    python scripts/pydantic_phase2_manual_fixes.py --apply    # Apply changes
"""

import re
import argparse
from pathlib import Path
from typing import List, Tuple

# ANSI colors
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_change(file: str, line: int, change: str):
    print(f"{Colors.BLUE}{file}:{line}{Colors.ENDC} - {change}")

def print_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.ENDC}")

def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.ENDC}")

def fix_config_classes(file_path: Path, apply: bool = False) -> List[Tuple[int, str, str]]:
    """Fix Config classes by converting to model_config = ConfigDict(...)"""
    changes = []
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check for Config class
        if re.match(r'\s*class\s+Config\s*:', line):
            indent = len(line) - len(line.lstrip())
            indent_str = ' ' * indent
            
            # Find the Config class content
            config_content = []
            j = i + 1
            while j < len(lines) and (lines[j].strip() == '' or lines[j].startswith(indent_str + ' ')):
                if lines[j].strip():
                    config_content.append(lines[j].strip())
                j += 1
            
            # Generate ConfigDict
            config_dict_parts = []
            has_json_encoders = False
            
            for content_line in config_content:
                if 'from_attributes = True' in content_line:
                    config_dict_parts.append('from_attributes=True')
                elif 'orm_mode = True' in content_line:
                    config_dict_parts.append('from_attributes=True')
                elif 'populate_by_name = True' in content_line:
                    config_dict_parts.append('populate_by_name=True')
                elif 'use_enum_values = True' in content_line:
                    config_dict_parts.append('use_enum_values=True')
                elif 'json_encoders' in content_line:
                    has_json_encoders = True
            
            # Create the new line
            if config_dict_parts:
                new_line = f"{indent_str}model_config = ConfigDict({', '.join(config_dict_parts)})\n"
            else:
                new_line = f"{indent_str}model_config = ConfigDict()\n"
            
            changes.append((i + 1, "Config class", f"model_config = ConfigDict({', '.join(config_dict_parts)})"))
            
            if has_json_encoders:
                print_warning(f"{file_path.name}:{i+1} - json_encoders found, needs manual migration")
            
            # Replace the Config class with model_config
            new_lines.append(new_line)
            if has_json_encoders:
                new_lines.append(f"{indent_str}# TODO: Migrate json_encoders to field serializers\n")
            
            # Skip the old Config class lines
            i = j
        else:
            new_lines.append(line)
            i += 1
    
    if apply and changes:
        with open(file_path, 'w') as f:
            f.writelines(new_lines)
    
    return changes

def fix_multi_field_validators(file_path: Path, apply: bool = False) -> List[Tuple[int, str, str]]:
    """Split multi-field validators into separate field validators"""
    changes = []
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Pattern for multi-field validators
    pattern = r"@validator\s*\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)"
    
    def replace_multi_validator(match):
        field1, field2 = match.group(1), match.group(2)
        # The replacement will be handled line by line
        return match.group(0)  # Keep original for now
    
    # Find all multi-field validators
    for match in re.finditer(pattern, content):
        line_num = content[:match.start()].count('\n') + 1
        changes.append((line_num, "Multi-field validator", f"Split {match.group(1)}, {match.group(2)}"))
    
    if apply and changes:
        # More complex replacement needed here
        lines = content.split('\n')
        new_lines = []
        
        for i, line in enumerate(lines):
            if match := re.search(pattern, line):
                # Get the function that follows
                indent = len(line) - len(line.lstrip())
                indent_str = ' ' * indent
                
                # Add both validators
                field1, field2 = match.group(1), match.group(2)
                new_lines.append(f"{indent_str}@field_validator('{field1}')")
                new_lines.append(f"{indent_str}@classmethod")
                
                # The actual function will be on the next line
                # We need to duplicate it for the second field
                func_lines = []
                j = i + 1
                while j < len(lines) and (lines[j].strip() == '' or not lines[j].startswith(indent_str[:-4])):
                    func_lines.append(lines[j])
                    j += 1
                
                # Add the function
                new_lines.extend(func_lines)
                
                # Add second validator
                new_lines.append(f"{indent_str}@field_validator('{field2}')")
                new_lines.append(f"{indent_str}@classmethod")
                new_lines.extend(func_lines)
                
                # Skip the original lines
                for _ in range(j - i - 1):
                    next(iter(lines), None)
            else:
                new_lines.append(line)
        
        with open(file_path, 'w') as f:
            f.write('\n'.join(new_lines))
    
    return changes

def fix_money_type(file_path: Path, apply: bool = False) -> List[Tuple[int, str, str]]:
    """Fix the Money type to use only Pydantic V2 patterns"""
    changes = []
    
    if 'base.py' not in str(file_path):
        return changes
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    if 'class Money' in content and '__get_validators__' in content:
        line_num = content[:content.find('class Money')].count('\n') + 1
        changes.append((line_num, "Money type", "Remove V1 methods, keep only V2"))
        
        if apply:
            # This is complex enough that we should do it carefully
            print_warning("Money type fix needs careful manual review")
            # For now, just add a TODO comment
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if 'class Money' in line:
                    lines.insert(i, "# TODO: Remove __get_validators__ method, keep only __get_pydantic_core_schema__")
                    break
            
            with open(file_path, 'w') as f:
                f.write('\n'.join(lines))
    
    return changes

def fix_base_json_encoders(file_path: Path, apply: bool = False) -> List[Tuple[int, str, str]]:
    """Convert json_encoders in StandardizedModel to use field_serializer"""
    changes = []
    
    if 'base.py' not in str(file_path):
        return changes
    
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    new_lines = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Look for StandardizedModel class
        if 'class StandardizedModel' in line:
            new_lines.append(line)
            i += 1
            
            # Skip to Config class
            while i < len(lines) and 'class Config:' not in lines[i]:
                new_lines.append(lines[i])
                i += 1
            
            if i < len(lines):
                # Found Config class
                indent = len(lines[i]) - len(lines[i].lstrip())
                indent_str = ' ' * indent
                
                # Replace with model_config
                new_lines.append(f"{indent_str}model_config = ConfigDict(\n")
                new_lines.append(f"{indent_str}    use_enum_values=True,\n")
                new_lines.append(f"{indent_str}    populate_by_name=True,\n")
                new_lines.append(f"{indent_str}    json_encoders={{\n")
                new_lines.append(f"{indent_str}        Decimal: float,\n")
                new_lines.append(f"{indent_str}        datetime: lambda v: v.isoformat(),\n")
                new_lines.append(f"{indent_str}        date: lambda v: v.isoformat(),\n")
                new_lines.append(f"{indent_str}        time: lambda v: v.strftime('%H:%M:%S'),\n")
                new_lines.append(f"{indent_str}    }}\n")
                new_lines.append(f"{indent_str})\n")
                
                changes.append((i + 1, "StandardizedModel Config", "Converted to ConfigDict with json_encoders"))
                
                # Skip old Config content
                i += 1
                while i < len(lines) and lines[i].startswith(indent_str + ' '):
                    i += 1
        else:
            new_lines.append(line)
            i += 1
    
    if apply and changes:
        with open(file_path, 'w') as f:
            f.writelines(new_lines)
    
    return changes

def main():
    parser = argparse.ArgumentParser(description="Apply Pydantic V2 Phase 2 manual fixes")
    parser.add_argument('--apply', action='store_true', help='Apply the fixes (default is check only)')
    parser.add_argument('--check', action='store_true', help='Check what would be changed')
    args = parser.parse_args()
    
    if not args.apply:
        args.check = True
    
    print(f"{Colors.BOLD}Pydantic V2 Phase 2 - Manual Fixes{Colors.ENDC}\n")
    
    # Get all schema files
    schema_dir = Path('app/schemas')
    if not schema_dir.exists():
        schema_dir = Path('backend/app/schemas')
    
    schema_files = list(schema_dir.glob('*.py'))
    
    total_changes = []
    
    for file_path in schema_files:
        file_changes = []
        
        # Fix Config classes
        file_changes.extend(fix_config_classes(file_path, args.apply))
        
        # Fix multi-field validators (only for specific files)
        if file_path.name in ['availability.py', 'availability_window.py']:
            file_changes.extend(fix_multi_field_validators(file_path, args.apply))
        
        # Fix Money type
        if file_path.name == 'base.py':
            file_changes.extend(fix_money_type(file_path, args.apply))
            file_changes.extend(fix_base_json_encoders(file_path, args.apply))
        
        if file_changes:
            print(f"\n{Colors.BOLD}{file_path.name}:{Colors.ENDC}")
            for line, issue, fix in file_changes:
                print_change(file_path.name, line, f"{issue} → {fix}")
            total_changes.extend(file_changes)
    
    print(f"\n{Colors.BOLD}Summary:{Colors.ENDC}")
    print(f"Total changes: {len(total_changes)}")
    
    if args.check:
        print_warning("Run with --apply to make these changes")
    else:
        print_success("Changes applied! Review with git diff")

if __name__ == "__main__":
    main()