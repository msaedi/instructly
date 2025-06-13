#!/usr/bin/env python3
"""
InstaInstru Project Overview Generator
Provides a comprehensive overview of the codebase and database for new developers.

Usage: python scripts/project_overview.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, SessionLocal
from sqlalchemy import inspect, text
from pathlib import Path
import json
from datetime import datetime
import ast

def print_header(title):
    """Print a formatted header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

def extract_module_docstring(file_path):
    """Extract the module-level docstring from a Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse the AST to get the module docstring
        tree = ast.parse(content)
        docstring = ast.get_docstring(tree)
        
        if docstring:
            # Clean up the docstring - get just the first paragraph
            lines = docstring.strip().split('\n')
            # Take lines until we hit an empty line or get 3 lines
            summary_lines = []
            for line in lines:
                if not line.strip() and summary_lines:
                    break
                if line.strip():
                    summary_lines.append(line.strip())
                if len(summary_lines) >= 3:
                    break
            return ' '.join(summary_lines)
        
        # Fallback: try to find comments at the top
        lines = content.split('\n')
        for i, line in enumerate(lines[:10]):  # Check first 10 lines
            if line.strip().startswith('#') and not line.strip().startswith('#!'):
                return line.strip()[1:].strip()
        
        return None
    except Exception as e:
        return None

def extract_frontend_description(file_path):
    """Extract description from frontend files (usually from comments)."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()[:20]  # Check first 20 lines
        
        # Look for component description in comments
        for i, line in enumerate(lines):
            if '// ' in line and any(keyword in line.lower() for keyword in ['component', 'page', 'manages', 'handles', 'provides']):
                return line.split('// ')[-1].strip()
        
        # Look for JSDoc style comments
        in_comment = False
        comment_lines = []
        for line in lines:
            if '/**' in line:
                in_comment = True
                continue
            elif '*/' in line:
                break
            elif in_comment and '*' in line:
                comment_lines.append(line.strip().lstrip('*').strip())
        
        if comment_lines:
            return ' '.join(comment_lines[:2])  # First 2 lines of JSDoc
        
        return None
    except Exception:
        return None

def get_file_structure():
    """Generate a detailed file structure with descriptions."""
    print_header("DETAILED FILE STRUCTURE")
    
    # Find project root
    current_dir = Path.cwd()
    project_root = current_dir
    while project_root.parent != project_root:
        if (project_root / 'backend').exists() and (project_root / 'frontend').exists():
            break
        project_root = project_root.parent
    
    print("\n📁 Backend Structure:")
    print("-" * 60)
    
    # Backend file structure
    backend_root = project_root / 'backend'
    
    # Define the backend structure to explore
    backend_dirs = {
        'app/models': 'Database models (SQLAlchemy)',
        'app/routes': 'API endpoints',
        'app/schemas': 'Pydantic schemas for validation',
        'app/services': 'Business logic services',
        'app/core': 'Core configuration',
        'alembic/versions': 'Database migrations',
        'scripts': 'Utility scripts'
    }
    
    for dir_path, dir_desc in backend_dirs.items():
        full_path = backend_root / dir_path
        if full_path.exists():
            print(f"\n📂 {dir_path}/ - {dir_desc}")
            
            # List Python files in this directory
            py_files = sorted(full_path.glob('*.py'))
            for py_file in py_files:
                if py_file.name == '__init__.py':
                    continue
                
                # Get the module docstring
                docstring = extract_module_docstring(py_file)
                if docstring:
                    # Truncate if too long
                    if len(docstring) > 100:
                        docstring = docstring[:97] + '...'
                    print(f"   📄 {py_file.name:<25} - {docstring}")
                else:
                    print(f"   📄 {py_file.name}")
    
    print("\n\n📁 Frontend Structure:")
    print("-" * 60)
    
    # Frontend file structure
    frontend_root = project_root / 'frontend'
    
    # Define the frontend structure to explore
    frontend_dirs = {
        'app': 'Next.js app directory (pages and layouts)',
        'components': 'Reusable React components',
        'lib': 'Utility functions and API client',
        'types': 'TypeScript type definitions',
        'app/config': 'Configuration files'
    }
    
    for dir_path, dir_desc in frontend_dirs.items():
        full_path = frontend_root / dir_path
        if full_path.exists():
            print(f"\n📂 {dir_path}/ - {dir_desc}")
            
            # For app directory, show page structure
            if dir_path == 'app':
                # Show key pages
                pages = [
                    ('page.tsx', 'Home page'),
                    ('login/page.tsx', 'Login page'),
                    ('register/page.tsx', 'Registration page'),
                    ('dashboard/page.tsx', 'Dashboard router'),
                    ('dashboard/student/page.tsx', 'Student dashboard'),
                    ('dashboard/instructor/page.tsx', 'Instructor dashboard'),
                    ('instructors/page.tsx', 'Browse instructors'),
                    ('instructors/[id]/page.tsx', 'Instructor profile page')
                ]
                for page_path, desc in pages:
                    if (full_path / page_path).exists():
                        print(f"   📄 {page_path:<30} - {desc}")
            else:
                # List TypeScript/JavaScript files
                ts_files = sorted(list(full_path.glob('*.ts')) + list(full_path.glob('*.tsx')))
                for ts_file in ts_files[:10]:  # Limit to 10 files per directory
                    desc = extract_frontend_description(ts_file)
                    if desc:
                        if len(desc) > 80:
                            desc = desc[:77] + '...'
                        print(f"   📄 {ts_file.name:<25} - {desc}")
                    else:
                        print(f"   📄 {ts_file.name}")
                
                if len(ts_files) > 10:
                    print(f"   ... and {len(ts_files) - 10} more files")

def get_database_overview():
    """Provide a high-level overview of the database structure"""
    inspector = inspect(engine)
    db = SessionLocal()
    
    print_header("DATABASE OVERVIEW - InstaInstru")
    
    print("""
InstaInstru is a TaskRabbit-style marketplace for private instruction in NYC.
The database is designed to support instructors offering services and managing
their availability, with a booking system to be implemented.
""")
    
    print("\n📊 Database Tables:")
    print("-" * 60)
    
    # Define table descriptions
    table_descriptions = {
        'users': 'All platform users (students and instructors)',
        'instructor_profiles': 'Extended profiles for instructor users',
        'services': 'Services offered by instructors (e.g., Piano, Yoga)',
        'instructor_availability': 'Date-specific availability for instructors',
        'availability_slots': 'Time slots for each availability date',
        'blackout_dates': 'Instructor vacation/unavailable dates',
        'password_reset_tokens': 'Temporary tokens for password reset',
        'bookings': 'Lesson bookings between students and instructors'
    }
    
    stats = {}
    for table_name in inspector.get_table_names():
        if table_name == 'alembic_version':
            continue
            
        # Get row count
        result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        count = result.scalar()
        
        desc = table_descriptions.get(table_name, "No description available")
        print(f"\n• {table_name} ({count} rows)")
        print(f"  {desc}")
        
        stats[table_name] = count
    
    # Show key relationships
    print("\n🔗 Key Relationships:")
    print("-" * 60)
    print("""
• User → InstructorProfile (one-to-one)
• InstructorProfile → Services (one-to-many)
• User → InstructorAvailability (one-to-many)
• InstructorAvailability → AvailabilitySlots (one-to-many)
• Booking → User (many-to-one for both student and instructor)
• Booking → Service (many-to-one)
• Booking → AvailabilitySlot (one-to-one)
""")
    
    # Current state summary
    print("\n📈 Current Data Summary:")
    print("-" * 60)
    
    # Get instructor count - using uppercase for enum
    result = db.execute(text("SELECT COUNT(*) FROM users WHERE role = 'INSTRUCTOR'"))
    instructor_count = result.scalar()
    
    # Get student count - using uppercase for enum
    result = db.execute(text("SELECT COUNT(*) FROM users WHERE role = 'STUDENT'"))
    student_count = result.scalar()
    
    print(f"• Total Users: {stats.get('users', 0)}")
    print(f"  - Instructors: {instructor_count}")
    print(f"  - Students: {student_count}")
    print(f"• Services Offered: {stats.get('services', 0)}")
    print(f"• Availability Entries: {stats.get('instructor_availability', 0)}")
    print(f"• Bookings: {stats.get('bookings', 0)}")
    
    db.close()
    return stats

def get_codebase_overview():
    """Provide an overview of the codebase structure"""
    print_header("CODEBASE OVERVIEW")
    
    print("""
The project uses a modern web stack with separate backend and frontend:
• Backend: FastAPI (Python) with PostgreSQL via Supabase
• Frontend: Next.js 14 (TypeScript) with Tailwind CSS
""")
    
    # Find project root
    current_dir = Path.cwd()
    project_root = current_dir
    while project_root.parent != project_root:
        if (project_root / 'backend').exists() and (project_root / 'frontend').exists():
            break
        project_root = project_root.parent
    
    print("\n🔧 Backend Structure:")
    print("-" * 60)
    
    backend_structure = {
        'app/': 'Main application code',
        'app/models/': 'SQLAlchemy database models',
        'app/routes/': 'API endpoints (auth, instructors, availability, bookings)',
        'app/schemas/': 'Pydantic schemas for validation',
        'app/services/': 'Business logic (email service, etc.)',
        'app/core/': 'Core configuration and constants',
        'alembic/': 'Database migrations',
        'scripts/': 'Utility scripts for development'
    }
    
    for path, desc in backend_structure.items():
        print(f"• {path:<20} - {desc}")
    
    print("\n💻 Frontend Structure:")
    print("-" * 60)
    
    frontend_structure = {
        'app/': 'Next.js app directory (pages and layouts)',
        'components/': 'Reusable React components',
        'lib/': 'Utility functions and API client',
        'types/': 'TypeScript type definitions',
        'public/': 'Static assets',
        'app/config/': 'Brand and configuration settings'
    }
    
    for path, desc in frontend_structure.items():
        print(f"• {path:<20} - {desc}")

def get_feature_status():
    """Show current feature implementation status"""
    print_header("FEATURE STATUS")
    
    features = {
        "✅ Completed": [
            "User authentication (JWT-based)",
            "Instructor profile management",
            "Service offering system",
            "Availability management (week-based UI)",
            "Password reset via email",
            "Role-based access control",
            "Database audit and seeding scripts",
            "Instant booking system (backend)",
            "Booking management API"
        ],
        "🚧 In Progress": [
            "Booking frontend UI",
            "Search and filtering UI"
        ],
        "❌ Not Started": [
            "Payment integration (Stripe)",
            "In-app messaging",
            "Reviews and ratings",
            "Email notifications for bookings",
            "Mobile app"
        ]
    }
    
    for status, items in features.items():
        print(f"\n{status}:")
        for item in items:
            print(f"  • {item}")

def get_quick_start_guide():
    """Provide quick start instructions for new developers"""
    print_header("QUICK START GUIDE")
    
    print("""
1. Backend Setup:
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\\Scripts\\activate
   pip install -r requirements.txt
   # Copy .env.example to .env and update values
   uvicorn app.main:app --reload

2. Frontend Setup:
   cd frontend
   npm install
   # Copy .env.local.example to .env.local
   npm run dev

3. Database Setup:
   # Run migrations
   cd backend
   alembic upgrade head
   
   # Seed test data
   python scripts/reset_and_seed_database.py

4. Access Points:
   • Frontend: http://localhost:3000
   • Backend API: http://localhost:8000
   • API Docs: http://localhost:8000/docs

5. Test Credentials:
   • Students: john.smith@example.com, emma.johnson@example.com
   • Instructors: sarah.chen@example.com, michael.rodriguez@example.com
   • All passwords: TestPassword123!
""")

def main():
    """Generate complete project overview"""
    print("\n" + "🎯 " * 20)
    print("    INSTAINSTRU PROJECT OVERVIEW    ")
    print("    Generated:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("🎯 " * 20)
    
    # Database overview
    db_stats = get_database_overview()
    
    # Codebase overview
    get_codebase_overview()
    
    # Detailed file structure
    get_file_structure()
    
    # Feature status
    get_feature_status()
    
    # Quick start guide
    get_quick_start_guide()
    
    print_header("NEXT STEPS FOR NEW DEVELOPERS")
    print("""
1. Review the codebase structure and familiarize yourself with the architecture
2. Run the application locally and test existing features
3. Check the GitHub issues or project board for current tasks
4. The highest priority is implementing the booking frontend UI
5. Ask questions! The codebase is well-documented but complex
""")
    
    print("\n" + "=" * 80)
    print("Overview generation complete! Welcome to InstaInstru! 🎉")
    print("=" * 80 + "\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error generating overview: {e}")
        import traceback
        traceback.print_exc()