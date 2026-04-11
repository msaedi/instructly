"""Shared typing surface for retriever repository mixins."""

import logging
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:

    class RetrieverRepositoryMixinBase:
        """Typed attribute surface supplied by the retriever facade."""

        db: Session
        logger: logging.Logger

else:

    class RetrieverRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
