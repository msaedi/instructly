from app.database import engine, SessionLocal
from app.models import InstructorProfile, Service
from sqlalchemy import text

def migrate_data():
    db = SessionLocal()
    
    try:
        # First, check if the old columns still exist
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = 'instructor_profiles' 
                AND column_name IN ('skills', 'hourly_rate', 'location')
            """))
            existing_columns = [row[0] for row in result]
            
            if not existing_columns:
                print("✅ Migration already completed or old columns don't exist!")
                return
        
        # Get data using raw SQL since the model no longer has these fields
        with engine.connect() as conn:
            instructors = conn.execute(text("""
                SELECT id, skills, hourly_rate, location 
                FROM instructor_profiles 
                WHERE skills IS NOT NULL AND hourly_rate IS NOT NULL
            """)).fetchall()
            
            for instructor in instructors:
                # Create services for each skill
                if instructor.skills:
                    for skill in instructor.skills:
                        conn.execute(text("""
                            INSERT INTO services (instructor_profile_id, skill, hourly_rate, description)
                            VALUES (:profile_id, :skill, :rate, :desc)
                        """), {
                            'profile_id': instructor.id,
                            'skill': skill,
                            'rate': instructor.hourly_rate,
                            'desc': f"{skill} lessons"
                        })
                
                # Update areas_of_service
                if instructor.location:
                    conn.execute(text("""
                        UPDATE instructor_profiles 
                        SET areas_of_service = :areas 
                        WHERE id = :id
                    """), {
                        'areas': [instructor.location],
                        'id': instructor.id
                    })
            
            conn.commit()
        
        print("✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    # First, add the new columns if they don't exist
    with engine.connect() as conn:
        # Add areas_of_service column
        try:
            conn.execute(text("ALTER TABLE instructor_profiles ADD COLUMN areas_of_service TEXT[]"))
            conn.commit()
            print("✅ Added areas_of_service column")
        except:
            print("ℹ️  areas_of_service column already exists")
    
    # Create services table
    Service.__table__.create(engine, checkfirst=True)
    print("✅ Services table ready")
    
    # Migrate the data
    migrate_data()
    
    # Drop old columns
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS skills"))
            conn.execute(text("ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS hourly_rate"))
            conn.execute(text("ALTER TABLE instructor_profiles DROP COLUMN IF EXISTS location"))
            conn.commit()
            print("✅ Dropped old columns")
        except Exception as e:
            print(f"ℹ️  Could not drop columns: {e}")