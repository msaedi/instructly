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
    duration_override = Column(Integer, nullable=True)
    
    # Relationships
    instructor_profile = relationship("InstructorProfile", back_populates="services")

    # Constraints
    __table_args__ = (
        UniqueConstraint('instructor_profile_id', 'skill', name='unique_instructor_skill'),
    )

    @property
    def duration(self):
        """Get the effective duration for this service"""
        if self.duration_override is not None:
            return self.duration_override
        return self.instructor_profile.default_session_duration if self.instructor_profile else 60