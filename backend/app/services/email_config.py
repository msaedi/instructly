"""
Centralized email configuration service for InstaInstru.
Follows repository pattern and dependency injection.
"""
from typing import Dict, Optional

from sqlalchemy.orm import Session

from app.services.base import BaseService


class EmailConfigService(BaseService):
    """Manages email sender configurations by type"""

    EMAIL_SENDERS = {
        "monitoring": "InstaInstru Alerts <alerts@instainstru.com>",
        "transactional": "InstaInstru <hello@instainstru.com>",
        "booking": "InstaInstru Bookings <bookings@instainstru.com>",
        "password_reset": "InstaInstru Security <security@instainstru.com>",
        "default": "InstaInstru <hello@instainstru.com>",
    }

    def __init__(self, db: Session):
        super().__init__(db)

    def get_sender(self, email_type: str = "default") -> str:
        """Get sender for email type"""
        return self.EMAIL_SENDERS.get(email_type, self.EMAIL_SENDERS["default"])

    def get_monitoring_sender(self) -> str:
        """Get monitoring-specific sender"""
        return self.EMAIL_SENDERS["monitoring"]

    def get_transactional_sender(self) -> str:
        """Get transactional email sender"""
        return self.EMAIL_SENDERS["transactional"]

    def get_booking_sender(self) -> str:
        """Get booking-specific sender"""
        return self.EMAIL_SENDERS["booking"]

    def get_security_sender(self) -> str:
        """Get security-specific sender (password resets, etc.)"""
        return self.EMAIL_SENDERS["password_reset"]
