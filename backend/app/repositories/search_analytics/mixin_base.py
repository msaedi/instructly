"""Shared typing surface for search analytics repository mixins."""

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:

    class SearchAnalyticsRepositoryMixinBase:
        """Typed attribute/method surface supplied by the search analytics facade."""

        db: Session
        logger: logging.Logger

else:

    class SearchAnalyticsRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
