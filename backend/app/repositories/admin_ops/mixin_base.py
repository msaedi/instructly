"""Shared typing surface for admin ops repository mixins."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from ...models.booking import Booking

if TYPE_CHECKING:

    class AdminOpsRepositoryMixinBase:
        """Typed attribute surface supplied by the admin ops repository facade."""

        db: Session
        logger: logging.Logger
        model: type[Booking]

else:

    class AdminOpsRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
        model: type[Booking]
