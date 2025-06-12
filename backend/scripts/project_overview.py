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

def print_header(title):
    """Print a formatted header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)

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
        'password_reset_tokens': 'Temporary tokens for password reset'
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
        'app/routes/': 'API endpoints (auth, instructors, availability)',
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
            "Database audit and seeding scripts"
        ],
        "🚧 In Progress": [
            "Brand migration (Instructly → InstaInstru)",
            "Frontend polish and bug fixes"
        ],
        "❌ Not Started": [
            "Booking system (highest priority)",
            "Payment integration (Stripe)",
            "In-app messaging",
            "Search and filtering",
            "Reviews and ratings",
            "Email notifications for bookings"
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
   • All test instructors: TestPassword123!
   • Check the seed script for specific emails
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
    
    # Feature status
    get_feature_status()
    
    # Quick start guide
    get_quick_start_guide()
    
    print_header("NEXT STEPS FOR NEW DEVELOPERS")
    print("""
1. Review the codebase structure and familiarize yourself with the architecture
2. Run the application locally and test existing features
3. Check the GitHub issues or project board for current tasks
4. The highest priority is implementing the booking system
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