#!/usr/bin/env python3
# backend/scripts/project_overview.py
"""
InstaInstru Project Overview Generator - X-Team Enhanced Version
Provides a COMPLETE overview of the codebase, database, and project state.

Usage: python scripts/project_overview.py [--json] [--check-types] [--check-logging]
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple


class Colors:
    """ANSI color codes for terminal output"""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def print_header(text: str, color: str = Colors.HEADER) -> None:
    """Print a formatted header"""
    print(f"\n{color}{'=' * 80}")
    print(f"  {text}")
    print(f"{'=' * 80}{Colors.ENDC}")


def run_command(cmd: List[str], cwd: str = None) -> Tuple[bool, str]:
    """Run a command and return success status and output"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=30)
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def get_git_info() -> Dict[str, str]:
    """Get current git repository information"""
    info = {}

    # Get current branch
    success, output = run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    info["branch"] = output.strip() if success else "unknown"

    # Get last commit
    success, output = run_command(["git", "log", "-1", "--oneline"])
    info["last_commit"] = output.strip() if success else "unknown"

    # Get uncommitted files count
    success, output = run_command(["git", "status", "--porcelain"])
    info["uncommitted_files"] = len(output.strip().split("\n")) if output.strip() else 0

    # Get remote URL
    success, output = run_command(["git", "config", "--get", "remote.origin.url"])
    info["remote"] = output.strip() if success else "unknown"

    return info


def check_dragonfly_status() -> str:
    """Check if DragonflyDB container is running"""
    success, output = run_command(["docker", "ps", "--filter", "name=dragonfly", "--format", "{{.Names}}:{{.Status}}"])
    if success and "dragonfly" in output.lower():
        if "up" in output.lower():
            return f"{Colors.OKGREEN}Running{Colors.ENDC} (instainstru_dragonfly on port 6379)"
        else:
            return f"{Colors.FAIL}Stopped{Colors.ENDC} (run: docker start instainstru_dragonfly)"
    return f"{Colors.WARNING}Not found{Colors.ENDC} (check Docker installation)"


def get_test_status() -> Dict[str, str]:
    """Get current test status"""
    backend_path = Path.cwd() / "backend"

    # Check if we're in the right directory
    if not backend_path.exists():
        return {"status": "Unable to check (not in project root)", "coverage": "Run from project root to check"}

    # Check if output is being redirected (to avoid hanging when writing to file)
    if not sys.stdout.isatty():
        return {
            "status": "Check manually (output redirected)",
            "coverage": "Run 'pytest --cov=app --cov-report=term-missing' for coverage",
        }

    # Try to run pytest with minimal output
    print("  Checking test status... (this may take a moment)")
    success, output = run_command(["python", "-m", "pytest", "--tb=no", "-q", "--no-header"], cwd=str(backend_path))

    if success:
        # Extract test counts from output
        lines = output.strip().split("\n")
        for line in lines:
            if "passed" in line:
                return {
                    "status": f"{Colors.OKGREEN}All passing{Colors.ENDC} - {line.strip()}",
                    "coverage": "Run 'pytest --cov=app --cov-report=term-missing' for coverage",
                }
    elif "failed" in output:
        # Extract failure count
        for line in output.split("\n"):
            if "failed" in line and "passed" in line:
                return {
                    "status": f"{Colors.FAIL}Some failing{Colors.ENDC} - {line.strip()}",
                    "coverage": "Fix tests before checking coverage",
                }

    return {
        "status": f"{Colors.WARNING}Unable to run{Colors.ENDC} (check virtual environment)",
        "coverage": "Activate venv and run 'pytest --cov=app'",
    }


def analyze_database_schema() -> None:
    """Analyze and display database schema from models"""
    print_header("DETAILED DATABASE SCHEMA ANALYSIS", Colors.OKCYAN)

    models_path = Path.cwd() / "backend" / "app" / "models"
    if not models_path.exists():
        print("  Models directory not found")
        return

    # This is a simplified version - in the real implementation,
    # you'd parse the SQLAlchemy models to extract schema info
    # For now, keeping the existing hardcoded schema display

    schemas = {
        "availability_slots": {
            "columns": [
                ("id", "INTEGER", "NOT NULL", "PK"),
                ("availability_id", "INTEGER", "NOT NULL", "FK"),
                ("start_time", "TIME", "NOT NULL", ""),
                ("end_time", "TIME", "NOT NULL", ""),
            ],
            "foreign_keys": ["availability_id -> instructor_availability.id"],
            "indexes": ["idx_availability_slots_availability_id: (availability_id)"],
        },
        "blackout_dates": {
            "columns": [
                ("id", "INTEGER", "NOT NULL", "PK"),
                ("instructor_id", "INTEGER", "NOT NULL", "FK"),
                ("date", "DATE", "NOT NULL", ""),
                ("reason", "VARCHAR(255)", "NULL", ""),
                ("created_at", "TIMESTAMP", "NOT NULL", ""),
            ],
            "foreign_keys": ["instructor_id -> users.id"],
            "indexes": [
                "ix_blackout_dates_instructor_id: (instructor_id)",
                "idx_blackout_dates_instructor_date: (instructor_id, date)",
                "ix_blackout_dates_date: (date)",
            ],
        },
        "bookings": {
            "columns": [
                ("id", "INTEGER", "NOT NULL", "PK"),
                ("student_id", "INTEGER", "NOT NULL", "FK"),
                ("instructor_id", "INTEGER", "NOT NULL", "FK"),
                ("service_id", "INTEGER", "NOT NULL", "FK"),
                ("availability_slot_id", "INTEGER", "NULL", "FK"),
                ("booking_date", "DATE", "NOT NULL", ""),
                ("start_time", "TIME", "NOT NULL", ""),
                ("end_time", "TIME", "NOT NULL", ""),
                ("service_name", "VARCHAR", "NOT NULL", ""),
                ("hourly_rate", "NUMERIC(10, 2)", "NOT NULL", ""),
                ("total_price", "NUMERIC(10, 2)", "NOT NULL", ""),
                ("duration_minutes", "INTEGER", "NOT NULL", ""),
                ("status", "VARCHAR(20)", "NOT NULL", ""),
                ("service_area", "VARCHAR", "NULL", ""),
                ("meeting_location", "TEXT", "NULL", ""),
                ("location_type", "VARCHAR(50)", "NULL", ""),
                ("student_note", "TEXT", "NULL", ""),
                ("instructor_note", "TEXT", "NULL", ""),
                ("created_at", "TIMESTAMP", "NOT NULL", ""),
                ("updated_at", "TIMESTAMP", "NULL", ""),
                ("confirmed_at", "TIMESTAMP", "NULL", ""),
                ("completed_at", "TIMESTAMP", "NULL", ""),
                ("cancelled_at", "TIMESTAMP", "NULL", ""),
                ("cancelled_by_id", "INTEGER", "NULL", "FK"),
                ("cancellation_reason", "TEXT", "NULL", ""),
            ],
            "foreign_keys": [
                "service_id -> services.id",
                "student_id -> users.id",
                "cancelled_by_id -> users.id",
                "availability_slot_id -> availability_slots.id",
                "instructor_id -> users.id",
            ],
            "indexes": [
                "idx_bookings_student_id: (student_id)",
                "idx_bookings_upcoming: (booking_date, status)",
                "idx_bookings_status: (status)",
                "idx_bookings_availability_slot_id: (availability_slot_id)",
                "idx_bookings_instructor_date_status: (instructor_id, booking_date, status)",
                "idx_bookings_date: (booking_date)",
                "idx_bookings_instructor_id: (instructor_id)",
                "idx_bookings_student_date: (student_id, booking_date)",
                "idx_bookings_service_id: (service_id)",
                "idx_bookings_student_status: (student_id, status)",
                "idx_bookings_cancelled_by_id: (cancelled_by_id)",
                "idx_bookings_date_status: (booking_date, status)",
                "idx_bookings_created_at: (created_at)",
            ],
        },
        "instructor_availability": {
            "columns": [
                ("id", "INTEGER", "NOT NULL", "PK"),
                ("instructor_id", "INTEGER", "NOT NULL", "FK"),
                ("date", "DATE", "NOT NULL", ""),
                ("is_cleared", "BOOLEAN", "NOT NULL", ""),
                ("created_at", "TIMESTAMP", "NULL", ""),
                ("updated_at", "TIMESTAMP", "NULL", ""),
            ],
            "foreign_keys": ["instructor_id -> users.id"],
            "indexes": [
                "idx_availability_date: (instructor_id, date)",
                "idx_instructor_availability_instructor_date: (instructor_id, date)",
            ],
        },
        "instructor_profiles": {
            "columns": [
                ("id", "INTEGER", "NOT NULL", "PK"),
                ("user_id", "INTEGER", "NOT NULL", "FK"),
                ("bio", "TEXT", "NULL", ""),
                ("years_experience", "INTEGER", "NULL", ""),
                ("areas_of_service", "VARCHAR", "NULL", ""),
                ("min_advance_booking_hours", "INTEGER", "NOT NULL", ""),
                ("buffer_time_minutes", "INTEGER", "NOT NULL", ""),
                ("created_at", "TIMESTAMP", "NULL", ""),
                ("updated_at", "TIMESTAMP", "NULL", ""),
            ],
            "foreign_keys": ["user_id -> users.id"],
            "indexes": ["idx_instructor_profiles_user_id: (user_id)", "ix_instructor_profiles_id: (id)"],
        },
        "password_reset_tokens": {
            "columns": [
                ("id", "INTEGER", "NOT NULL", "PK"),
                ("user_id", "INTEGER", "NOT NULL", "FK"),
                ("token", "VARCHAR", "NOT NULL", ""),
                ("expires_at", "TIMESTAMP", "NOT NULL", ""),
                ("used", "BOOLEAN", "NOT NULL", ""),
                ("created_at", "TIMESTAMP", "NULL", ""),
            ],
            "foreign_keys": ["user_id -> users.id"],
            "indexes": [
                "idx_password_reset_tokens_user_id: (user_id)",
                "ix_password_reset_tokens_token: (token) UNIQUE",
            ],
        },
        "services": {
            "columns": [
                ("id", "INTEGER", "NOT NULL", "PK"),
                ("instructor_profile_id", "INTEGER", "NULL", "FK"),
                ("skill", "VARCHAR", "NOT NULL", ""),
                ("hourly_rate", "DOUBLE PRECISION", "NOT NULL", ""),
                ("description", "VARCHAR", "NULL", ""),
                ("duration_override", "INTEGER", "NULL", ""),
                ("is_active", "BOOLEAN", "NOT NULL", ""),
            ],
            "foreign_keys": ["instructor_profile_id -> instructor_profiles.id"],
            "indexes": [
                "unique_instructor_skill_active: (instructor_profile_id, skill) UNIQUE",
                "idx_services_active: (instructor_profile_id, is_active)",
                "idx_services_instructor_profile_id: (instructor_profile_id)",
                "ix_services_id: (id)",
            ],
        },
        "users": {
            "columns": [
                ("id", "INTEGER", "NOT NULL", "PK"),
                ("email", "VARCHAR", "NOT NULL", ""),
                ("hashed_password", "VARCHAR", "NOT NULL", ""),
                ("full_name", "VARCHAR", "NOT NULL", ""),
                ("is_active", "BOOLEAN", "NULL", ""),
                ("role", "VARCHAR(10)", "NOT NULL", ""),
                ("created_at", "TIMESTAMP", "NULL", ""),
                ("updated_at", "TIMESTAMP", "NULL", ""),
            ],
            "foreign_keys": [],
            "indexes": ["ix_users_email: (email) UNIQUE", "idx_users_email: (email)", "ix_users_id: (id)"],
        },
    }

    for table_name, table_info in schemas.items():
        print(f"\n{Colors.BOLD}📊 Table: {table_name}{Colors.ENDC}")
        print("  Columns:")
        for col in table_info["columns"]:
            name, dtype, nullable, key = col
            key_icon = "🔑 " if "PK" in key else ("🔗 " if "FK" in key else "")
            print(f"    • {name:<30} {dtype:<20} {nullable:<10} {key_icon}{key}")

        if table_info["foreign_keys"]:
            print("  Foreign Keys:")
            for fk in table_info["foreign_keys"]:
                print(f"    • {fk}")

        if table_info["indexes"]:
            print("  Indexes:")
            for idx in table_info["indexes"]:
                print(f"    • {idx}")


def analyze_migrations() -> None:
    """Analyze alembic migrations"""
    print_header("DATABASE MIGRATION HISTORY", Colors.OKCYAN)

    migrations_path = Path.cwd() / "backend" / "alembic" / "versions"
    if not migrations_path.exists():
        print("  Migrations directory not found")
        return

    migrations = []
    for file in sorted(migrations_path.glob("*.py")):
        if file.name != "__pycache__":
            with open(file, "r") as f:
                content = f.read()
                # Extract revision - handle both formats
                revision_match = re.search(r'revision[:\s]*(?:str\s*=\s*)?["\']([^"\']+)["\']', content)
                # Extract message from docstring
                message_match = re.search(r'"""([^"]+)', content)
                if revision_match:
                    revision = revision_match.group(1)
                    # Extract just the number part for display
                    rev_num = revision.split("_")[0] if "_" in revision else revision[:3]
                    message = message_match.group(1).strip() if message_match else revision
                    migrations.append({"revision": rev_num, "message": message})

    print(f"\nTotal migrations: {len(migrations)}")
    if migrations:
        print("\nMigration History:")
        for m in migrations:
            print(f"  • {m['revision']}: {m['message']}")


def analyze_backend() -> None:
    """Analyze backend structure and endpoints"""
    print_header("COMPLETE BACKEND ANALYSIS", Colors.OKBLUE)

    routes_path = Path.cwd() / "backend" / "app" / "routes"
    models_path = Path.cwd() / "backend" / "app" / "models"

    # Analyze routes
    print(f"\n{Colors.BOLD}🔌 API Endpoints:{Colors.ENDC}\n")
    if routes_path.exists():
        for route_file in sorted(routes_path.glob("*.py")):
            if route_file.name != "__init__.py":
                print(f"  📄 {route_file.name}")
                with open(route_file, "r") as f:
                    content = f.read()
                    # Extract route definitions
                    routes = re.findall(r'@router\.(get|post|put|patch|delete)\("([^"]+)"', content)
                    for method, path in routes:
                        print(f"    • {method.upper():<8} {path}")

    # Analyze models
    print(f"\n{Colors.BOLD}📊 Database Models:{Colors.ENDC}\n")
    if models_path.exists():
        for model_file in sorted(models_path.glob("*.py")):
            if model_file.name not in ["__init__.py", "base.py"]:
                print(f"  📄 {model_file.name}")
                with open(model_file, "r") as f:
                    content = f.read()
                    # Extract model class names
                    models = re.findall(r"class (\w+)\(.*Base.*\):", content)
                    for model in models:
                        print(f"    • Model: {model}")


def analyze_frontend() -> None:
    """Analyze frontend structure"""
    print_header("COMPLETE FRONTEND FILE ANALYSIS", Colors.OKGREEN)

    frontend_path = Path.cwd() / "frontend"
    if not frontend_path.exists():
        print("  Frontend directory not found")
        return

    # Define directories to analyze
    dirs_to_analyze = ["app", "components", "lib", "types", "public"]

    total_files = 0
    for dir_name in dirs_to_analyze:
        dir_path = frontend_path / dir_name
        if dir_path.exists():
            print(f"\n{Colors.BOLD}📁 {dir_name}/{Colors.ENDC}")

            # Get all TypeScript/JavaScript files
            files = list(dir_path.rglob("*.tsx")) + list(dir_path.rglob("*.ts"))
            files = sorted([f for f in files if "node_modules" not in str(f)])

            for file in files:
                relative_path = file.relative_to(frontend_path)
                size = file.stat().st_size
                size_str = f"{Colors.WARNING}({size//1024}KB){Colors.ENDC}" if size > 10240 else ""
                print(f"  📄 {str(relative_path):<50} {size_str}")
                total_files += 1

    print(f"\n{Colors.BOLD}📊 Frontend Analysis Summary:{Colors.ENDC}")
    print(f"  Total TypeScript files: {total_files}")


def analyze_dependencies() -> None:
    """Analyze project dependencies"""
    print_header("DEPENDENCY ANALYSIS", Colors.WARNING)

    # Backend dependencies
    print(f"\n{Colors.BOLD}🐍 Backend Dependencies:{Colors.ENDC}")
    req_file = Path.cwd() / "backend" / "requirements.txt"
    if req_file.exists():
        with open(req_file, "r") as f:
            deps = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            # Show only major dependencies
            major_deps = [
                d
                for d in deps
                if any(
                    pkg in d for pkg in ["fastapi", "sqlalchemy", "alembic", "pydantic", "pytest", "celery", "redis"]
                )
            ]
            for dep in sorted(major_deps):
                print(f"  • {dep}")

    # Frontend dependencies
    print(f"\n{Colors.BOLD}📦 Frontend Dependencies:{Colors.ENDC}")
    package_file = Path.cwd() / "frontend" / "package.json"
    if package_file.exists():
        with open(package_file, "r") as f:
            data = json.load(f)
            deps = data.get("dependencies", {})
            # Show core dependencies
            print("  Core dependencies:")
            for dep, version in sorted(deps.items())[:10]:
                print(f"    • {dep}: {version}")


def analyze_todos() -> None:
    """Generate a summary of TODOs and FIXMEs in the codebase"""
    print_header("TASK SUMMARY (TODOs & FIXMEs)", Colors.WARNING)

    todos = []
    fixmes = []

    # Search patterns
    patterns = {"python": ["*.py"], "typescript": ["*.ts", "*.tsx"], "javascript": ["*.js", "*.jsx"]}

    for lang, exts in patterns.items():
        for ext in exts:
            for file in Path.cwd().rglob(ext):
                if "node_modules" in str(file) or "venv" in str(file) or ".git" in str(file):
                    continue

                try:
                    with open(file, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f, 1):
                            line_stripped = line.strip()
                            if "TODO" in line:
                                todos.append(
                                    {"file": str(file.relative_to(Path.cwd())), "line": i, "content": line_stripped}
                                )
                            if "FIXME" in line:
                                fixmes.append(
                                    {"file": str(file.relative_to(Path.cwd())), "line": i, "content": line_stripped}
                                )
                except:
                    pass

    # Display results
    print(f"\n{Colors.WARNING}📝 TODOs ({len(todos)}):{Colors.ENDC}")
    for todo in todos[:15]:  # Show first 15
        # Just show the line after the line number
        content = todo["content"]
        # Truncate if too long
        if len(content) > 80:
            content = content[:77] + "..."
        print(f"  • {todo['file']}:{todo['line']} - {content}")
    if len(todos) > 15:
        print(f"  ... and {len(todos) - 15} more")

    print(f"\n{Colors.FAIL}🔧 FIXMEs ({len(fixmes)}):{Colors.ENDC}")
    for fixme in fixmes[:10]:
        content = fixme["content"]
        if len(content) > 80:
            content = content[:77] + "..."
        print(f"  • {fixme['file']}:{fixme['line']} - {content}")


def print_feature_status() -> None:
    """Print current feature implementation status"""
    print_header("FEATURE IMPLEMENTATION STATUS", Colors.HEADER)

    print("\n✅ Completed:")
    completed = [
        "User authentication (JWT-based)",
        "Instructor profile management",
        "Service offering system",
        "Availability management (week-based UI)",
        "Instant booking system",
        "Password reset via email",
        "Production-ready logging (frontend)",
        "Centralized TypeScript types",
    ]
    for feature in completed:
        print(f"  • {feature}")

    print("\n🚧 In Progress:")
    in_progress = ["Type refactoring across frontend", "Email notifications"]
    for feature in in_progress:
        print(f"  • {feature}")

    print("\n❌ Not Started:")
    not_started = ["Payment integration (Stripe)", "In-app messaging", "Reviews and ratings", "Mobile app"]
    for feature in not_started:
        print(f"  • {feature}")


def print_env_vars() -> None:
    """Print required environment variables"""
    print_header("REQUIRED ENVIRONMENT VARIABLES", Colors.HEADER)

    print("\nBackend (.env):")
    backend_vars = [
        "DATABASE_URL - PostgreSQL connection string",
        "SECRET_KEY - JWT secret key",
        "RESEND_API_KEY - Email service API key",
        "SUPABASE_URL - Supabase project URL",
        "SUPABASE_ANON_KEY - Supabase anonymous key",
    ]
    for var in backend_vars:
        print(f"  • {var}")

    print("\nFrontend (.env.local):")
    frontend_vars = [
        "NEXT_PUBLIC_API_URL - Backend API URL",
        "NEXT_PUBLIC_APP_URL - Frontend app URL",
        "NEXT_PUBLIC_ENABLE_LOGGING - Enable logging (true/false)",
    ]
    for var in frontend_vars:
        print(f"  • {var}")


def print_quickstart() -> None:
    """Print quick start guide"""
    print_header("QUICK START GUIDE", Colors.HEADER)

    print(
        """
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
"""
    )


def print_project_stats() -> None:
    """Print project statistics"""
    print_header("PROJECT STATISTICS", Colors.OKGREEN)

    # Get test status for accurate reporting
    test_info = get_test_status()

    stats = {
        "Backend API endpoints": "~40",
        "Database tables": "8",
        "Frontend pages": "~15",
        "React components": "11",
        "TypeScript type files": "6",
        "Test status": test_info["status"],
        "Test coverage": test_info["coverage"],
    }

    for key, value in stats.items():
        print(f"  • {key}: {value}")


def print_infrastructure_status() -> None:
    """Print infrastructure and service status"""
    print_header("INFRASTRUCTURE STATUS", Colors.OKCYAN)

    # Check DragonflyDB
    dragonfly_status = check_dragonfly_status()
    print(f"\n  • DragonflyDB (Cache): {dragonfly_status}")

    # Database info
    print(f"  • PostgreSQL: Version 17.4 (via Supabase)")
    print(f"  • Backend Framework: FastAPI")
    print(f"  • Frontend Framework: Next.js 14")

    # Git info
    git_info = get_git_info()
    if git_info["uncommitted_files"] > 0:
        print(f"\n  {Colors.WARNING}⚠️  Uncommitted changes: {git_info['uncommitted_files']} files{Colors.ENDC}")


def main():
    """Main function to generate project overview"""
    # Print header with timestamp
    print(f"{Colors.BOLD}🎯 " * 20)
    print(f"    INSTAINSTRU PROJECT OVERVIEW - X-TEAM ENHANCED")
    print(f"    Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯 " * 20 + f"{Colors.ENDC}")

    # Git repository status
    print_header("GIT REPOSITORY STATUS", Colors.HEADER)
    git_info = get_git_info()
    print(f"  • branch: {git_info['branch']}")
    print(f"  • last_commit: {git_info['last_commit']}")
    print(f"  • uncommitted_files: {git_info['uncommitted_files']}")
    print(f"  • remote: {git_info['remote']}")

    # Infrastructure status
    print_infrastructure_status()

    # Database schema
    analyze_database_schema()

    # Migration history
    analyze_migrations()

    # Backend analysis
    analyze_backend()

    # Frontend analysis
    analyze_frontend()

    # Dependencies
    analyze_dependencies()

    # TODOs and FIXMEs
    analyze_todos()

    # Feature status
    print_feature_status()

    # Environment variables
    print_env_vars()

    # Quick start guide
    print_quickstart()

    # Project statistics
    print_project_stats()

    # Footer
    print(f"\n{Colors.BOLD}{'=' * 80}")
    print("Overview generation complete! This is YOUR project - own it! 🚀")
    print(f"{'=' * 80}{Colors.ENDC}")


if __name__ == "__main__":
    main()
