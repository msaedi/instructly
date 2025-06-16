#!/usr/bin/env python3
"""
InstaInstru Project Overview Generator - X-Team Enhanced Version
Provides a COMPLETE overview of the codebase, database, and project state.

Usage: python scripts/project_overview.py [--json] [--check-types] [--check-logging]
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, SessionLocal
from sqlalchemy import inspect, text, MetaData
from pathlib import Path
import json
import ast
import subprocess
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import argparse

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(title, color=Colors.HEADER):
    """Print a formatted header with color"""
    print(f"\n{color}{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}{Colors.ENDC}")

def get_git_info() -> Dict[str, str]:
    """Get current git status and information"""
    try:
        info = {}
        # Current branch
        branch = subprocess.check_output(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], text=True).strip()
        info['branch'] = branch
        
        # Last commit
        last_commit = subprocess.check_output(['git', 'log', '-1', '--oneline'], text=True).strip()
        info['last_commit'] = last_commit
        
        # Uncommitted changes
        status = subprocess.check_output(['git', 'status', '--porcelain'], text=True)
        info['uncommitted_files'] = len(status.strip().split('\n')) if status.strip() else 0
        
        # Remote URL
        try:
            remote = subprocess.check_output(['git', 'remote', 'get-url', 'origin'], text=True).strip()
            info['remote'] = remote
        except:
            info['remote'] = 'No remote configured'
            
        return info
    except Exception as e:
        return {'error': str(e)}

def check_file_for_logging(file_path: Path) -> Dict[str, bool]:
    """Check if a file has proper logging implemented"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        checks = {
            'imports_logger': 'from @/lib/logger' in content or "from '../logger'" in content or 'logger' in content,
            'uses_logger': 'logger.' in content,
            'no_console_log': 'console.log' not in content,
            'has_jsdoc': '/**' in content and '*/' in content,
        }
        
        return checks
    except:
        return {'error': True}

def check_file_for_types(file_path: Path) -> Dict[str, any]:
    """Check TypeScript file for type usage"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find local interfaces/types
        local_types = re.findall(r'(?:interface|type)\s+(\w+)', content)
        
        # Find imports from types directory
        type_imports = re.findall(r"from\s+['\"]@/types/(\w+)['\"]", content)
        
        return {
            'local_types': local_types,
            'type_imports': type_imports,
            'has_any': ': any' in content,
            'needs_refactor': len(local_types) > 2  # Arbitrary threshold
        }
    except:
        return {'error': True}

def analyze_database_schema():
    """Provide detailed database schema analysis"""
    print_header("DETAILED DATABASE SCHEMA ANALYSIS", Colors.CYAN)
    
    inspector = inspect(engine)
    metadata = MetaData()
    metadata.reflect(bind=engine)
    
    for table_name in sorted(inspector.get_table_names()):
        if table_name == 'alembic_version':
            continue
            
        print(f"\n{Colors.BOLD}📊 Table: {table_name}{Colors.ENDC}")
        table = metadata.tables[table_name]
        
        # Columns
        print("  Columns:")
        for column in table.columns:
            nullable = "NULL" if column.nullable else "NOT NULL"
            pk = "🔑 PK" if column.primary_key else ""
            fk = "🔗 FK" if column.foreign_keys else ""
            print(f"    • {column.name:<25} {str(column.type):<20} {nullable:<10} {pk} {fk}")
        
        # Foreign keys
        if table.foreign_keys:
            print("  Foreign Keys:")
            for fk in table.foreign_keys:
                print(f"    • {fk.parent.name} -> {fk.column.table.name}.{fk.column.name}")
        
        # Indexes
        if table.indexes:
            print("  Indexes:")
            for idx in table.indexes:
                cols = ", ".join([c.name for c in idx.columns])
                unique = "UNIQUE" if idx.unique else ""
                print(f"    • {idx.name}: ({cols}) {unique}")

def analyze_frontend_structure(check_logging=False, check_types=False):
    """Analyze frontend structure in detail"""
    print_header("COMPLETE FRONTEND FILE ANALYSIS", Colors.GREEN)
    
    frontend_root = Path.cwd().parent / 'frontend'
    if not frontend_root.exists():
        frontend_root = Path.cwd() / 'frontend'
    
    stats = {
        'total_files': 0,
        'has_logging': 0,
        'needs_logging': 0,
        'has_types': 0,
        'needs_type_refactor': 0
    }
    
    # Define all directories to scan
    scan_dirs = ['app', 'components', 'lib', 'types', 'public', 'styles']
    
    for scan_dir in scan_dirs:
        dir_path = frontend_root / scan_dir
        if not dir_path.exists():
            continue
            
        print(f"\n{Colors.BOLD}📁 {scan_dir}/{Colors.ENDC}")
        
        # Recursively find all TS/TSX files
        all_files = list(dir_path.rglob('*.ts')) + list(dir_path.rglob('*.tsx'))
        
        for file_path in sorted(all_files):
            relative_path = file_path.relative_to(frontend_root)
            stats['total_files'] += 1
            
            file_info = f"  📄 {str(relative_path):<50}"
            
            # Check logging if requested
            if check_logging and file_path.suffix in ['.ts', '.tsx']:
                log_check = check_file_for_logging(file_path)
                if log_check.get('uses_logger'):
                    file_info += f" {Colors.GREEN}✓ Logging{Colors.ENDC}"
                    stats['has_logging'] += 1
                elif not log_check.get('error'):
                    file_info += f" {Colors.WARNING}⚠ No logging{Colors.ENDC}"
                    stats['needs_logging'] += 1
            
            # Check types if requested
            if check_types and file_path.suffix in ['.ts', '.tsx']:
                type_check = check_file_for_types(file_path)
                if not type_check.get('error'):
                    if type_check.get('needs_refactor'):
                        file_info += f" {Colors.WARNING}🔧 Needs type refactor{Colors.ENDC}"
                        stats['needs_type_refactor'] += 1
                    elif type_check.get('type_imports'):
                        file_info += f" {Colors.GREEN}✓ Uses central types{Colors.ENDC}"
                        stats['has_types'] += 1
            
            # Get file size
            size = file_path.stat().st_size
            if size > 10000:  # Files over 10KB
                file_info += f" {Colors.WARNING}({size//1024}KB){Colors.ENDC}"
            
            print(file_info)
    
    # Print summary
    print(f"\n{Colors.BOLD}📊 Frontend Analysis Summary:{Colors.ENDC}")
    print(f"  Total TypeScript files: {stats['total_files']}")
    if check_logging:
        print(f"  Files with logging: {stats['has_logging']}")
        print(f"  Files needing logging: {stats['needs_logging']}")
    if check_types:
        print(f"  Files using central types: {stats['has_types']}")
        print(f"  Files needing type refactor: {stats['needs_type_refactor']}")

def analyze_backend_structure():
    """Analyze backend structure with API endpoint details"""
    print_header("COMPLETE BACKEND ANALYSIS", Colors.BLUE)
    
    backend_root = Path.cwd()
    if 'backend' not in str(backend_root):
        backend_root = backend_root / 'backend'
    
    # Analyze routes for API endpoints
    print(f"\n{Colors.BOLD}🔌 API Endpoints:{Colors.ENDC}")
    routes_dir = backend_root / 'app' / 'routes'
    
    if routes_dir.exists():
        for route_file in sorted(routes_dir.glob('*.py')):
            if route_file.name == '__init__.py':
                continue
                
            print(f"\n  📄 {route_file.name}")
            try:
                with open(route_file, 'r') as f:
                    content = f.read()
                
                # Extract route decorators
                routes = re.findall(r'@router\.(get|post|put|patch|delete)\("([^"]+)"', content)
                for method, path in routes:
                    print(f"    • {method.upper():<7} {path}")
            except:
                print("    ⚠️  Could not parse routes")
    
    # Analyze models
    print(f"\n{Colors.BOLD}📊 Database Models:{Colors.ENDC}")
    models_dir = backend_root / 'app' / 'models'
    
    if models_dir.exists():
        for model_file in sorted(models_dir.glob('*.py')):
            if model_file.name == '__init__.py':
                continue
                
            print(f"\n  📄 {model_file.name}")
            try:
                with open(model_file, 'r') as f:
                    content = f.read()
                
                # Extract class definitions
                classes = re.findall(r'class\s+(\w+)\([^)]*Base[^)]*\):', content)
                for class_name in classes:
                    print(f"    • Model: {class_name}")
                    
                    # Extract relationships
                    relationships = re.findall(rf'{class_name}.*relationship\("(\w+)"', content)
                    if relationships:
                        print(f"      Relationships: {', '.join(set(relationships))}")
            except:
                print("    ⚠️  Could not parse models")

def analyze_alembic_migrations():
    """Analyze Alembic migration history"""
    print_header("DATABASE MIGRATION HISTORY", Colors.CYAN)
    
    migrations_dir = Path.cwd() / 'alembic' / 'versions'
    if not migrations_dir.exists():
        migrations_dir = Path.cwd() / 'backend' / 'alembic' / 'versions'
    
    if migrations_dir.exists():
        migrations = sorted(migrations_dir.glob('*.py'), key=lambda x: x.name)
        
        print(f"\nTotal migrations: {len(migrations)}")
        print("\nMigration History:")
        
        for migration in migrations:
            # Extract revision info from filename
            parts = migration.stem.split('_')
            if len(parts) > 1:
                revision = parts[0]
                description = ' '.join(parts[1:])
                print(f"  • {revision}: {description}")
                
                # Try to extract the upgrade operations
                try:
                    with open(migration, 'r') as f:
                        content = f.read()
                    
                    # Look for create_table operations
                    tables_created = re.findall(r'create_table\([\'"](\w+)[\'"]', content)
                    if tables_created:
                        print(f"    Creates: {', '.join(tables_created)}")
                    
                    # Look for add_column operations
                    columns_added = re.findall(r'add_column\([\'"](\w+)[\'"].*?[\'"](\w+)[\'"]', content)
                    if columns_added:
                        for table, column in columns_added:
                            print(f"    Adds: {table}.{column}")
                except:
                    pass

def generate_dependency_analysis():
    """Analyze project dependencies"""
    print_header("DEPENDENCY ANALYSIS", Colors.WARNING)
    
    # Backend dependencies
    print(f"\n{Colors.BOLD}🐍 Backend Dependencies:{Colors.ENDC}")
    req_file = Path.cwd() / 'requirements.txt'
    if not req_file.exists():
        req_file = Path.cwd() / 'backend' / 'requirements.txt'
    
    if req_file.exists():
        with open(req_file, 'r') as f:
            deps = f.readlines()
        
        core_deps = ['fastapi', 'sqlalchemy', 'pydantic', 'alembic', 'pytest']
        for dep in deps:
            dep = dep.strip()
            if any(core in dep.lower() for core in core_deps):
                print(f"  • {dep}")
    
    # Frontend dependencies
    print(f"\n{Colors.BOLD}📦 Frontend Dependencies:{Colors.ENDC}")
    package_file = Path.cwd() / 'package.json'
    if not package_file.exists():
        package_file = Path.cwd() / 'frontend' / 'package.json'
    
    if package_file.exists():
        with open(package_file, 'r') as f:
            package_data = json.load(f)
        
        print("  Core dependencies:")
        core_deps = ['next', 'react', 'typescript', 'tailwindcss']
        deps = package_data.get('dependencies', {})
        for dep in core_deps:
            if dep in deps:
                print(f"    • {dep}: {deps[dep]}")

def generate_task_summary():
    """Generate a summary of TODOs and FIXMEs in the codebase"""
    print_header("TASK SUMMARY (TODOs & FIXMEs)", Colors.WARNING)
    
    todos = []
    fixmes = []
    
    # Search both backend and frontend
    for root_dir in [Path.cwd() / 'backend', Path.cwd() / 'frontend']:
        if not root_dir.exists():
            continue
            
        for ext in ['*.py', '*.ts', '*.tsx']:
            for file_path in root_dir.rglob(ext):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    for i, line in enumerate(lines):
                        if 'TODO' in line:
                            todos.append((file_path.relative_to(root_dir.parent), i+1, line.strip()))
                        if 'FIXME' in line:
                            fixmes.append((file_path.relative_to(root_dir.parent), i+1, line.strip()))
                except:
                    pass
    
    if todos:
        print(f"\n{Colors.WARNING}📝 TODOs ({len(todos)}):{Colors.ENDC}")
        for file_path, line_no, content in todos[:10]:  # Show first 10
            print(f"  • {file_path}:{line_no} - {content[:80]}")
        if len(todos) > 10:
            print(f"  ... and {len(todos) - 10} more")
    
    if fixmes:
        print(f"\n{Colors.FAIL}🔧 FIXMEs ({len(fixmes)}):{Colors.ENDC}")
        for file_path, line_no, content in fixmes:
            print(f"  • {file_path}:{line_no} - {content[:80]}")

def generate_json_output(data: dict, filename: str = "project_overview.json"):
    """Generate JSON output for programmatic use"""
    output_path = Path.cwd() / filename
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print(f"\n✅ JSON output saved to: {output_path}")

def main():
    """Generate complete project overview"""
    parser = argparse.ArgumentParser(description='Generate InstaInstru project overview')
    parser.add_argument('--json', action='store_true', help='Output JSON format')
    parser.add_argument('--check-types', action='store_true', help='Check TypeScript type usage')
    parser.add_argument('--check-logging', action='store_true', help='Check logging implementation')
    args = parser.parse_args()
    
    print(f"\n{Colors.BOLD}🎯 " * 20)
    print("    INSTAINSTRU PROJECT OVERVIEW - X-TEAM ENHANCED")
    print("    Generated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("🎯 " * 20 + Colors.ENDC)
    
    overview_data = {}
    
    # Git information
    print_header("GIT REPOSITORY STATUS")
    git_info = get_git_info()
    for key, value in git_info.items():
        print(f"  • {key}: {value}")
    overview_data['git'] = git_info
    
    # Database analysis
    analyze_database_schema()
    analyze_alembic_migrations()
    
    # Backend analysis
    analyze_backend_structure()
    
    # Frontend analysis
    analyze_frontend_structure(
        check_logging=args.check_logging,
        check_types=args.check_types
    )
    
    # Dependencies
    generate_dependency_analysis()
    
    # Tasks
    generate_task_summary()
    
    # Feature status (from original)
    print_header("FEATURE IMPLEMENTATION STATUS")
    features = {
        "✅ Completed": [
            "User authentication (JWT-based)",
            "Instructor profile management",
            "Service offering system",
            "Availability management (week-based UI)",
            "Instant booking system",
            "Password reset via email",
            "Production-ready logging (frontend)",
            "Centralized TypeScript types"
        ],
        "🚧 In Progress": [
            "Type refactoring across frontend",
            "Email notifications"
        ],
        "❌ Not Started": [
            "Payment integration (Stripe)",
            "In-app messaging",
            "Reviews and ratings",
            "Mobile app"
        ]
    }
    
    for status, items in features.items():
        print(f"\n{status}:")
        for item in items:
            print(f"  • {item}")
    
    overview_data['features'] = features
    
    # Environment variables needed
    print_header("REQUIRED ENVIRONMENT VARIABLES")
    print("\nBackend (.env):")
    print("  • DATABASE_URL - PostgreSQL connection string")
    print("  • SECRET_KEY - JWT secret key")
    print("  • RESEND_API_KEY - Email service API key")
    print("  • SUPABASE_URL - Supabase project URL")
    print("  • SUPABASE_ANON_KEY - Supabase anonymous key")
    
    print("\nFrontend (.env.local):")
    print("  • NEXT_PUBLIC_API_URL - Backend API URL")
    print("  • NEXT_PUBLIC_APP_URL - Frontend app URL")
    print("  • NEXT_PUBLIC_ENABLE_LOGGING - Enable logging (true/false)")
    
    # Quick start (from original)
    get_quick_start_guide()
    
    # Summary statistics
    print_header("PROJECT STATISTICS", Colors.GREEN)
    print("  • Backend API endpoints: ~40")
    print("  • Database tables: 8")
    print("  • Frontend pages: ~15")
    print("  • React components: 11")
    print("  • TypeScript type files: 6")
    print("  • Test coverage: TBD")
    
    if args.json:
        generate_json_output(overview_data)
    
    print(f"\n{Colors.BOLD}" + "=" * 80)
    print("Overview generation complete! This is YOUR project - own it! 🚀")
    print("=" * 80 + Colors.ENDC + "\n")

def get_quick_start_guide():
    """Provide quick start instructions"""
    print_header("QUICK START GUIDE")
    
    print("""
1. Backend Setup:
   cd backend
   python -m venv venv
   source venv/bin/activate  # Windows: venv\\Scripts\\activate
   pip install -r requirements.txt
   cp .env.example .env  # Update with your values
   alembic upgrade head
   python scripts/reset_and_seed_database.py
   uvicorn app.main:app --reload

2. Frontend Setup:
   cd frontend
   npm install
   cp .env.local.example .env.local
   npm run dev

3. Access Points:
   • Frontend: http://localhost:3000
   • Backend API: http://localhost:8000
   • API Docs: http://localhost:8000/docs

4. Test Credentials:
   • Students: john.smith@example.com, emma.johnson@example.com  
   • Instructors: sarah.chen@example.com, michael.rodriguez@example.com
   • All passwords: TestPassword123!

5. Development Tools:
   • API Documentation: http://localhost:8000/docs
   • Database GUI: Use TablePlus/pgAdmin with DATABASE_URL
   • Email testing: Check Resend dashboard
""")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"{Colors.FAIL}Error generating overview: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()