"""Shared typing surface for booking repository mixins."""

from datetime import date, datetime
import logging
from typing import TYPE_CHECKING, Any, Optional, Union

from sqlalchemy.orm import Query, Session

from ...models.booking import Booking
from ...models.booking_payment import BookingPayment

if TYPE_CHECKING:

    class BookingRepositoryMixinBase:
        """Typed attribute/method surface supplied by the booking repository façade."""

        db: Session
        logger: logging.Logger
        _external_call_lock_savepoint: Any | None

        def _apply_eager_loading(self, query: Query) -> Query:
            ...

        def _get_user_now(self, user_id: str) -> datetime:
            ...

        def _get_user_today(self, user_id: str) -> date:
            ...

        def get_by_id(self, id: str, load_relationships: bool = True) -> Optional[Booking]:
            ...

        def ensure_payment(self, booking_id: str) -> BookingPayment:
            ...

        def invalidate_entity_cache(self, entity_id: Union[int, str]) -> None:
            ...

else:

    class BookingRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
        _external_call_lock_savepoint: Any | None
