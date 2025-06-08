from sqlalchemy import Column, Integer, String, Float, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from ..database import Base

class Service(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    instructor_profile_id = Column(Integer, ForeignKey("instructor_profiles.id"))
    skill = Column(String, nullable=False)
    hourly_rate = Column(Float, nullable=False)
    description = Column(String, nullable=True)
    
    # Relationships
    instructor_profile = relationship("InstructorProfile", back_populates="services")
    bookings = relationship("Booking", back_populates="service")

    # Constraints
    __table_args__ = (
        UniqueConstraint('instructor_profile_id', 'skill', name='unique_instructor_skill'),
    )