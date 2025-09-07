"""
Pydantic schemas for favorites functionality.

Defines request and response models for the favorites API endpoints.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .instructor import InstructorProfileResponse


class FavoriteResponse(BaseModel):
    """Response for favorite add/remove operations."""

    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Human-readable message about the operation")
    favorite_id: Optional[str] = Field(
        None, description="ID of the created favorite (for add operations)"
    )
    already_favorited: Optional[bool] = Field(
        None, description="True if already favorited (for add)"
    )
    not_favorited: Optional[bool] = Field(None, description="True if not favorited (for remove)")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Instructor added to favorites",
                "favorite_id": "01K2K8CVN3A55280PFKJD9YHKV",
            }
        }
    )


class FavoritedInstructor(BaseModel):
    """Instructor with favorite metadata."""

    id: str = Field(..., description="Instructor user ID (ULID)")
    email: str = Field(..., description="Instructor email")
    first_name: str = Field(..., description="Instructor first name")
    last_name: str = Field(..., description="Instructor last name")
    profile: Optional[InstructorProfileResponse] = Field(
        None, description="Instructor profile details"
    )
    favorited_at: Optional[datetime] = Field(None, description="When this instructor was favorited")
    is_active: bool = Field(True, description="Whether the instructor is active")

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "01K2K8CVN3A55280PFKJD9YHKV",
                "email": "john.doe@example.com",
                "first_name": "John",
                "last_name": "Doe",
                "profile": {
                    "bio": "Experienced piano teacher",
                    "years_experience": 10,
                    "hourly_rate": 75.0,
                    "rating": 4.8,
                    "total_reviews": 25,
                },
                "favorited_at": "2024-08-13T10:30:00Z",
                "is_active": True,
            }
        },
    )


class FavoritesList(BaseModel):
    """List of favorited instructors."""

    favorites: List[FavoritedInstructor] = Field(..., description="List of favorited instructors")
    total: int = Field(..., description="Total number of favorites")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "favorites": [
                    {
                        "id": "01K2K8CVN3A55280PFKJD9YHKV",
                        "email": "john.doe@example.com",
                        "first_name": "John",
                        "last_name": "Doe",
                        "profile": {
                            "bio": "Experienced piano teacher",
                            "years_experience": 10,
                            "hourly_rate": 75.0,
                            "rating": 4.8,
                            "total_reviews": 25,
                        },
                        "favorited_at": "2024-08-13T10:30:00Z",
                        "is_active": True,
                    }
                ],
                "total": 1,
            }
        }
    )


class FavoriteStatusResponse(BaseModel):
    """Response for single favorite status check."""

    is_favorited: bool = Field(..., description="Whether the instructor is favorited")

    model_config = ConfigDict(json_schema_extra={"example": {"is_favorited": True}})


class BulkFavoriteStatus(BaseModel):
    """Bulk favorite status check response."""

    favorites: dict[str, bool] = Field(..., description="Map of instructor_id to favorited status")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "favorites": {
                    "01K2K8CVN3A55280PFKJD9YHKV": True,
                    "01K2K8CVN3A55280PFKJD9YHKW": False,
                    "01K2K8CVN3A55280PFKJD9YHKX": True,
                }
            }
        }
    )
