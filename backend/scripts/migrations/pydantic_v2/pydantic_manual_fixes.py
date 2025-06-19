#!/usr/bin/env python3
"""Manual fixes for Pydantic V2 migration"""

# Run this script to see the manual changes needed


# === user.py ===

# Line 30: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:


# === password_reset.py ===

# Line 37: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:


# === booking.py ===

# Line 110: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:

# Line 120: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:

# Line 130: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:

# Line 140: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:

# Line 215: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:


# === instructor.py ===

# Line 67: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:

# Line 76: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:

# Line 219: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:


# === availability_window.py ===

# Line 182: Multi-field validator
# Current: @validator('from_week_start', 'to_week_start')
# Fix: Split into separate validators:
# @field_validator('from_week_start')
# @field_validator('to_week_start')

# Line 100: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:

# Line 130: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:


# === availability.py ===

# Line 103: Multi-field validator
# Current: @validator('from_week_start', 'to_week_start')
# Fix: Split into separate validators:
# @field_validator('from_week_start')
# @field_validator('to_week_start')

# Line 40: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:

# Line 76: Config class
# Current:
#   class Config:
#       from_attributes = True
# Fix:


# === base.py ===

# Line 15: Config class
# Current:
#   class Config:
#       # Ensure Decimal fields serialize as float
#       json_encoders = {
#       Decimal: float,
#       datetime: lambda v: v.isoformat(),
#       date: lambda v: v.isoformat(),
#       time: lambda v: v.strftime('%H:%M:%S'),
#       }
#       # Use enum values instead of names
#       use_enum_values = True
#       # Serialize by alias
#       populate_by_name = True
# Fix:
#   # Note: json_encoders needs custom migration
#   model_config = ConfigDict(use_enum_values=True)

# Line 29: Money type needs V2 migration
# The Money type needs to be updated for Pydantic V2
# See the migration guide for custom types
