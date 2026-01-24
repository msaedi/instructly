"""
Centralized email configuration service for InstaInstru.
Follows repository pattern and dependency injection.
"""

from sqlalchemy.orm import Session

from app.services.base import BaseService


class EmailConfigService(BaseService):
    """Manages email sender configurations by type"""

    EMAIL_SENDERS = {
        "monitoring": "iNSTAiNSTRU Alerts <alerts@instainstru.com>",
        "transactional": "iNSTAiNSTRU <hello@instainstru.com>",
        "booking": "iNSTAiNSTRU Bookings <bookings@instainstru.com>",
        "security": "iNSTAiNSTRU Security <security@instainstru.com>",  # Used for password reset emails
        "default": "iNSTAiNSTRU <hello@instainstru.com>",
    }

    def __init__(self, db: Session):
        super().__init__(db)

    def get_sender(self, email_type: str = "default") -> str:  # no-metrics
        """Get sender for email type"""
        return self.EMAIL_SENDERS.get(email_type, self.EMAIL_SENDERS["default"])

    def get_monitoring_sender(self) -> str:  # no-metrics
        """Get monitoring-specific sender"""
        return self.EMAIL_SENDERS["monitoring"]

    def get_transactional_sender(self) -> str:  # no-metrics
        """Get transactional email sender"""
        return self.EMAIL_SENDERS["transactional"]

    def get_booking_sender(self) -> str:  # no-metrics
        """Get booking-specific sender"""
        return self.EMAIL_SENDERS["booking"]

    def get_security_sender(self) -> str:  # no-metrics
        """Get security-specific sender (password resets, etc.)"""
        return self.EMAIL_SENDERS["security"]
