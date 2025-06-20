# backend/scripts/fix_areas_corruption.py
"""
Script to fix corrupted areas_of_service data in instructor profiles.
"""

import os
import re
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.instructor import InstructorProfile


def clean_area_string(area):
    """Clean a single area string by removing excessive escaping."""
    if not area:
        return ""

    # Remove excessive escaping and quotes
    cleaned = area

    # Keep removing escape sequences until no more changes
    while True:
        prev = cleaned
        # Remove backslashes before quotes
        cleaned = cleaned.replace('\\"', '"')
        cleaned = cleaned.replace("\\'", "'")
        cleaned = cleaned.replace("\\\\", "\\")

        # Remove surrounding quotes if they exist
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        if cleaned.startswith("'") and cleaned.endswith("'"):
            cleaned = cleaned[1:-1]

        # Remove curly braces that shouldn't be there
        cleaned = cleaned.replace("{", "").replace("}", "")

        if cleaned == prev:
            break

    return cleaned.strip()


def fix_areas_of_service():
    """Fix all corrupted areas_of_service in the database."""
    db = SessionLocal()

    try:
        # Get all instructor profiles
        profiles = db.query(InstructorProfile).all()

        for profile in profiles:
            if not profile.areas_of_service:
                continue

            print(f"\nProcessing profile {profile.id} (user {profile.user_id}):")
            print(f"Current areas: {profile.areas_of_service}")

            # Split by comma (handling various formats)
            # First, try to identify individual areas
            areas_str = profile.areas_of_service

            # Extract areas between various delimiters
            # This regex finds text between quotes or commas
            pattern = r'["\']?([^"\'{}\\,]+)["\']?'
            matches = re.findall(pattern, areas_str)

            # Clean each match
            cleaned_areas = []
            for match in matches:
                cleaned = clean_area_string(match).strip()
                # Only add if it looks like a valid area name
                if cleaned and len(cleaned) > 2 and not cleaned.isdigit():
                    # Remove any remaining special characters at start/end
                    cleaned = cleaned.strip("\\/\"'{}[], ")
                    if cleaned and cleaned not in cleaned_areas:
                        cleaned_areas.append(cleaned)

            # Common NYC areas to validate against
            valid_areas = [
                "Manhattan - Upper East Side",
                "Manhattan - Upper West Side",
                "Manhattan - Midtown",
                "Manhattan - Downtown",
                "Brooklyn",
                "Queens",
                "Bronx",
                "Staten Island",
                "Harlem",
                "Financial District",
                "Chelsea",
                "Greenwich Village",
                "SoHo",
                "Tribeca",
                "East Village",
                "West Village",
                "Lower East Side",
                "Upper Manhattan",
                "Midtown",
                "Downtown",
            ]

            # Try to match cleaned areas to valid areas
            final_areas = []
            for area in cleaned_areas:
                # Direct match
                if area in valid_areas:
                    final_areas.append(area)
                else:
                    # Partial match
                    for valid in valid_areas:
                        if area.lower() in valid.lower() or valid.lower() in area.lower():
                            if valid not in final_areas:
                                final_areas.append(valid)
                                break
                    else:
                        # If no match found, keep the cleaned version if it seems valid
                        if len(area) > 3 and area not in final_areas:
                            final_areas.append(area)

            # Join with proper format
            new_areas = ", ".join(final_areas)
            print(f"Cleaned areas: {new_areas}")

            # Update the profile
            profile.areas_of_service = new_areas

        # Commit all changes
        db.commit()
        print("\n✅ Successfully fixed all areas of service!")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()


def check_current_state():
    """Check current state of areas_of_service."""
    db = SessionLocal()

    try:
        profiles = db.query(InstructorProfile).filter(InstructorProfile.areas_of_service.isnot(None)).all()

        print(f"Found {len(profiles)} profiles with areas of service:\n")

        for profile in profiles:
            print(f"Profile {profile.id}: {profile.areas_of_service}")

    finally:
        db.close()


if __name__ == "__main__":
    print("=== Checking current state ===")
    check_current_state()

    print("\n=== Fixing corrupted areas ===")
    fix_areas_of_service()

    print("\n=== Verifying fix ===")
    check_current_state()
