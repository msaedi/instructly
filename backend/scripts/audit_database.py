# backend/scripts/audit_database.py

"""
Database audit script to analyze all tables, columns, and data.
This will help identify unused tables and columns.

Usage: python scripts/audit_database.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, SessionLocal
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
import json

def get_table_info():
    """Get detailed information about all tables"""
    inspector = inspect(engine)
    db = SessionLocal()
    
    print("=" * 80)
    print("DATABASE AUDIT REPORT")
    print("=" * 80)
    
    all_tables = {}
    
    for table_name in inspector.get_table_names():
        if table_name == 'alembic_version':
            continue
            
        print(f"\n📊 TABLE: {table_name}")
        print("-" * 60)
        
        # Get columns
        columns = inspector.get_columns(table_name)
        print("Columns:")
        for col in columns:
            nullable = "NULL" if col['nullable'] else "NOT NULL"
            default = f"DEFAULT {col['default']}" if col.get('default') else ""
            print(f"  - {col['name']:<30} {str(col['type']):<20} {nullable:<10} {default}")
        
        # Get row count
        result = db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        count = result.scalar()
        print(f"\nRow count: {count}")
        
        # Get foreign keys
        foreign_keys = inspector.get_foreign_keys(table_name)
        if foreign_keys:
            print("\nForeign Keys:")
            for fk in foreign_keys:
                print(f"  - {fk['constrained_columns']} -> {fk['referred_table']}.{fk['referred_columns']}")
        
        # Get indexes
        indexes = inspector.get_indexes(table_name)
        if indexes:
            print("\nIndexes:")
            for idx in indexes:
                unique = "UNIQUE" if idx['unique'] else ""
                print(f"  - {idx['name']}: {idx['column_names']} {unique}")
        
        # Sample data for small tables
        if count > 0 and count <= 10:
            print("\nSample data:")
            result = db.execute(text(f"SELECT * FROM {table_name} LIMIT 5"))
            rows = result.fetchall()
            if rows:
                # Get column names
                col_names = result.keys()
                for row in rows:
                    row_dict = dict(zip(col_names, row))
                    # Truncate long values
                    for key, value in row_dict.items():
                        if isinstance(value, str) and len(str(value)) > 50:
                            row_dict[key] = str(value)[:50] + "..."
                    print(f"  {row_dict}")
        
        all_tables[table_name] = {
            "columns": [col['name'] for col in columns],
            "row_count": count,
            "foreign_keys": foreign_keys,
            "indexes": [idx['name'] for idx in indexes]
        }
    
    db.close()
    
    # Analysis summary
    print("\n" + "=" * 80)
    print("ANALYSIS SUMMARY")
    print("=" * 80)
    
    # Check for potentially unused tables
    print("\n🔍 Potentially Unused Tables (0 rows):")
    for table, info in all_tables.items():
        if info['row_count'] == 0:
            print(f"  - {table}")
    
    # Check relationships
    print("\n🔗 Table Relationships:")
    for table, info in all_tables.items():
        if info['foreign_keys']:
            print(f"\n  {table}:")
            for fk in info['foreign_keys']:
                print(f"    -> {fk['referred_table']}")
    
    # Specific checks
    print("\n⚠️  Potential Issues:")
    
    # Check if recurring_availability is actually used
    if 'recurring_availability' in all_tables:
        print(f"\n  - recurring_availability has {all_tables['recurring_availability']['row_count']} rows")
        print("    Question: Is this being used by the frontend week view?")
    
    # Check instructor_profiles columns
    if 'instructor_profiles' in all_tables:
        cols = all_tables['instructor_profiles']['columns']
        old_cols = ['buffer_time', 'minimum_advance_hours', 'default_session_duration']
        found_old = [col for col in old_cols if col in cols]
        if found_old:
            print(f"\n  - instructor_profiles has old booking columns: {found_old}")
            print("    These were from the old slot-based booking system")
    
    # Check for tables that might be obsolete
    obsolete_candidates = ['time_slots', 'availability_windows', 'bookings']
    for table in obsolete_candidates:
        if table in all_tables:
            print(f"\n  - Table '{table}' still exists (from old system?)")
    
    return all_tables

def check_data_relationships():
    """Check how data is actually being used"""
    db = SessionLocal()
    
    print("\n" + "=" * 80)
    print("DATA USAGE ANALYSIS")
    print("=" * 80)
    
    # Check how availability is stored
    print("\n📅 Availability Data Storage:")
    
    # Check recurring vs specific
    recurring_count = db.execute(text("SELECT COUNT(*) FROM recurring_availability")).scalar()
    specific_count = db.execute(text("SELECT COUNT(*) FROM specific_date_availability")).scalar()
    
    print(f"  - Recurring availability entries: {recurring_count}")
    print(f"  - Specific date entries: {specific_count}")
    
    # Check date ranges in specific_date_availability
    result = db.execute(text("""
        SELECT MIN(date) as earliest, MAX(date) as latest, COUNT(DISTINCT instructor_id) as instructors
        FROM specific_date_availability
    """))
    row = result.fetchone()
    if row and row[0]:
        print(f"  - Date range: {row[0]} to {row[1]}")
        print(f"  - Instructors using specific dates: {row[2]}")
    
    # Check if recurring is being overridden
    result = db.execute(text("""
        SELECT COUNT(DISTINCT s.instructor_id) 
        FROM specific_date_availability s
        JOIN recurring_availability r ON s.instructor_id = r.instructor_id
    """))
    overlap_count = result.scalar()
    print(f"  - Instructors with BOTH recurring and specific: {overlap_count}")
    
    db.close()

if __name__ == "__main__":
    try:
        table_info = get_table_info()
        check_data_relationships()
        
        print("\n" + "=" * 80)
        print("Run this output through Claude to get recommendations!")
        print("=" * 80)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()