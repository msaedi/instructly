# backend/app/core/exceptions.py
"""
Domain-specific exceptions for InstaInstru platform.

These exceptions provide clear, business-focused error messages
that can be caught and handled appropriately at the API layer.
"""

from typing import Any, Dict, Optional

from fastapi import HTTPException, status

HTTP_422_UNPROCESSABLE: int = getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422)


class DomainException(Exception):
    """Base exception for all domain-specific errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)

    def to_http_exception(self) -> HTTPException:
        """Default conversion to HTTPException (override in subclasses)."""
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": self.message,
                "code": self.code,
                "details": self.details,
            },
        )


class ValidationException(DomainException):
    """Raised when business validation fails."""

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": self.message,
                "code": self.code,
                "details": self.details,
            },
        )


class NotFoundException(DomainException):
    """Raised when a requested resource is not found."""

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": self.message,
                "code": self.code,
                "details": self.details,
            },
        )


class ConflictException(DomainException):
    """Raised when there's a conflict with existing data."""

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": self.message,
                "code": self.code,
                "details": self.details,
            },
        )


class BusinessRuleException(DomainException):
    """Raised when a business rule is violated."""

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=HTTP_422_UNPROCESSABLE,
            detail={
                "message": self.message,
                "code": self.code,
                "details": self.details,
            },
        )


class UnauthorizedException(DomainException):
    """Raised when user is not authenticated."""

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "message": self.message,
                "code": self.code,
                "details": self.details,
            },
        )


class ForbiddenException(DomainException):
    """Raised when user lacks permission for an action."""

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "message": self.message,
                "code": self.code,
                "details": self.details,
            },
        )


class ServiceException(DomainException):
    """Raised when a service operation fails."""

    def to_http_exception(self) -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": self.message or "An error occurred processing your request",
                "code": self.code,
                "details": self.details if self.details else {},
            },
        )


# Specific business exceptions


class BookingConflictException(ConflictException):
    """Raised when a booking conflicts with existing bookings."""

    def __init__(
        self,
        message: Optional[str] = None,
        *,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message=message or "This time slot conflicts with an existing booking",
            code="BOOKING_CONFLICT",
            details=details or {},
        )


class InsufficientNoticeException(BusinessRuleException):
    """Raised when booking doesn't meet minimum advance notice."""

    def __init__(self, required_hours: int, provided_hours: float):
        super().__init__(
            message=f"Bookings must be made at least {required_hours} hours in advance",
            code="INSUFFICIENT_NOTICE",
            details={
                "required_hours": required_hours,
                "provided_hours": provided_hours,
            },
        )


class AvailabilityOverlapException(ConflictException):
    """Raised when an availability slot overlaps with an existing slot."""

    def __init__(
        self,
        specific_date: str,
        new_range: str,
        conflicting_range: str,
    ):
        super().__init__(
            message=(
                f"Overlapping slot on {specific_date}: {new_range} conflicts with {conflicting_range}"
            ),
            code="AVAILABILITY_OVERLAP",
            details={
                "date": specific_date,
                "new_slot": new_range,
                "conflicting_slot": conflicting_range,
            },
        )


class RepositoryException(Exception):
    """
    Exception raised for repository layer errors.

    This exception is used when data access operations fail,
    such as database connection issues, query failures, or
    constraint violations.
    """


def is_db_pool_exhaustion(exc: Exception) -> bool:
    """
    Check if an exception indicates DB connection pool exhaustion.

    This is a common failure mode under high load when all database
    connections are in use and new requests time out waiting.
    """
    error_str = str(exc).lower()
    return "queuepool" in error_str or (
        "timeout" in error_str and ("connection" in error_str or "pool" in error_str)
    )


def raise_503_if_pool_exhaustion(exc: Exception) -> None:
    """
    Convert DB pool exhaustion errors to HTTP 503 (Service Unavailable).

    Under high load, returning 503 with Retry-After header is more appropriate
    than 500 because it signals to clients that the service is temporarily
    overloaded and they should retry.

    Raises:
        HTTPException: 503 if pool exhaustion detected
        Does not raise if not pool exhaustion (caller should re-raise original)
    """
    if is_db_pool_exhaustion(exc):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily overloaded. Please retry.",
            headers={"Retry-After": "2"},
        )
