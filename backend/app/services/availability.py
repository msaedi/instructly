from datetime import datetime, timedelta, date, time
from typing import List, Optional
from sqlalchemy.orm import Session
from pytz import timezone

from ..models.booking import TimeSlot, Booking, BookingStatus
from ..models.service import Service
from ..models.instructor import InstructorProfile
from ..schemas.availability import TimeSlotOption

class AvailabilityService:
    """Service for calculating available booking slots"""
    
    def __init__(self, db: Session):
        self.db = db
        self.tz = timezone('America/New_York')  # NYC timezone
    
    def get_available_slots(
        self, 
        instructor_id: int, 
        service_id: int, 
        target_date: date
    ) -> List[TimeSlotOption]:
        """
        Get available booking slots for a specific instructor, service, and date.
        Takes into account:
        - Instructor's availability windows
        - Service duration
        - Buffer time
        - Existing bookings
        - Minimum advance booking time
        """
        
        # Get the service and instructor profile
        service = self.db.query(Service).filter(Service.id == service_id).first()
        if not service:
            return []
            
        instructor = self.db.query(InstructorProfile).filter(
            InstructorProfile.user_id == instructor_id
        ).first()
        if not instructor:
            return []
        
        # Get effective duration and buffer
        duration_minutes = service.duration_override or instructor.default_session_duration
        buffer_minutes = instructor.buffer_time
        
        # Check minimum advance booking - make timezone aware
        now_utc = datetime.now(self.tz).astimezone(timezone('UTC'))
        min_booking_time = now_utc + timedelta(hours=instructor.minimum_advance_hours)
        
        # Create timezone-aware boundaries for the target date
        start_of_day = self.tz.localize(datetime.combine(target_date, time.min))
        end_of_day = self.tz.localize(datetime.combine(target_date + timedelta(days=1), time.min))
        
        # Convert to UTC for database comparison
        start_of_day_utc = start_of_day.astimezone(timezone('UTC'))
        end_of_day_utc = end_of_day.astimezone(timezone('UTC'))
        
        # Get instructor's availability windows for the date
        availability_windows = self.db.query(TimeSlot).filter(
            TimeSlot.instructor_id == instructor_id,
            TimeSlot.is_available == True,
            TimeSlot.start_time >= start_of_day_utc,
            TimeSlot.start_time < end_of_day_utc
        ).all()
        
        if not availability_windows:
            return []
        
        # Get existing bookings for the date
        existing_bookings = self.db.query(Booking).filter(
            Booking.instructor_id == instructor_id,
            Booking.status != BookingStatus.CANCELLED,
            Booking.time_slot.has(
                TimeSlot.start_time >= start_of_day_utc
            ),
            Booking.time_slot.has(
                TimeSlot.start_time < end_of_day_utc
            )
        ).all()
        
        # Generate possible slots
        possible_slots = []
        
        for window in availability_windows:
            # Generate slots in 30-minute increments within this window
            current_time = window.start_time
            
            while current_time + timedelta(minutes=duration_minutes) <= window.end_time:
                slot_end = current_time + timedelta(minutes=duration_minutes)
                
                # Check if this slot meets minimum advance booking
                if current_time >= min_booking_time:
                    # Check if slot conflicts with existing bookings
                    is_available = self._check_slot_availability(
                        current_time, 
                        slot_end, 
                        existing_bookings, 
                        buffer_minutes
                    )
                    
                    possible_slots.append(TimeSlotOption(
                        start_time=current_time,
                        end_time=slot_end,
                        available=is_available
                    ))
                
                # Move to next 30-minute increment
                current_time += timedelta(minutes=30)
        
        return possible_slots
    
    def _check_slot_availability(
        self, 
        start_time: datetime, 
        end_time: datetime, 
        existing_bookings: List[Booking], 
        buffer_minutes: int
    ) -> bool:
        """Check if a time slot conflicts with existing bookings (including buffer)"""
        
        for booking in existing_bookings:
            if not booking.time_slot:
                continue
                
            # Calculate booking time with buffer
            booking_start = booking.time_slot.start_time - timedelta(minutes=buffer_minutes)
            booking_end = booking.time_slot.end_time + timedelta(minutes=buffer_minutes)
            
            # Check for overlap
            if not (end_time <= booking_start or start_time >= booking_end):
                return False
        
        return True