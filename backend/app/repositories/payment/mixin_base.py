"""Shared typing surface for payment repository mixins."""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from sqlalchemy.orm import Session

from ...models.payment import PaymentEvent

if TYPE_CHECKING:

    class PaymentRepositoryMixinBase:
        """Typed attribute/method surface supplied by the payment repository facade."""

        db: Session
        logger: logging.Logger

        def create_payment_event(
            self,
            booking_id: str,
            event_type: str,
            event_data: Optional[Dict[str, Any]] = None,
        ) -> PaymentEvent:
            ...

else:

    class PaymentRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
