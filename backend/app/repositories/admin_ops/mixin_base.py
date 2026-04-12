"""Shared typing surface for admin ops repository mixins."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ...models.booking import Booking


class AdminOpsRepositoryMixinBase:
    """Runtime no-op base that keeps mixin MRO clean."""

    db: Session
    logger: logging.Logger
    model: type[Booking]
