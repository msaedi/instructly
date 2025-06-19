from app.database import Base, engine

# Create all tables
print("Creating database tables...")
Base.metadata.create_all(bind=engine)
print("✅ Tables created successfully!")
