from app.database import engine, Base
from app.models import User, InstructorProfile, Booking

# Create all tables
print("Creating database tables...")
Base.metadata.create_all(bind=engine)
print("✅ Tables created successfully!")