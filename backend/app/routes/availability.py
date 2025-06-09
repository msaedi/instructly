from datetime import date
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.availability import TimeSlotOption
from ..services.availability import AvailabilityService

router = APIRouter()

@router.get("/availability/slots", response_model=List[TimeSlotOption])
def get_available_slots(
    instructor_id: int = Query(..., description="ID of the instructor"),
    service_id: int = Query(..., description="ID of the service"),
    date: date = Query(..., description="Date to check availability (YYYY-MM-DD)"),
    db: Session = Depends(get_db)
):
    """
    Get available booking slots for a specific instructor, service, and date.
    
    This endpoint calculates available time slots considering:
    - Instructor's availability windows
    - Service duration (with possible override)
    - Buffer time between sessions
    - Existing bookings
    - Minimum advance booking time
    
    Returns a list of time slots with their availability status.
    """
    
    # Create availability service instance
    availability_service = AvailabilityService(db)
    
    try:
        # Get available slots
        slots = availability_service.get_available_slots(
            instructor_id=instructor_id,
            service_id=service_id,
            target_date=date
        )
        
        if not slots:
            # This is not an error - instructor might just not be available
            return []
            
        return slots
        
    except Exception as e:
        # Log the error in production
        print(f"Error calculating availability: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error calculating available slots"
        )