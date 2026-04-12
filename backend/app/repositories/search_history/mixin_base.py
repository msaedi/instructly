"""Shared typing surface for search history repository mixins."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Query, Session

from ...schemas.search_context import SearchUserContext

if TYPE_CHECKING:

    class SearchHistoryRepositoryMixinBase:
        """Typed attribute surface supplied by the search history facade."""

        db: Session
        logger: logging.Logger

        def _add_user_filter(self, query: Query[Any], context: SearchUserContext) -> Query[Any]:
            ...

else:

    class SearchHistoryRepositoryMixinBase:
        """Runtime no-op base that keeps mixin MRO clean."""

        db: Session
        logger: logging.Logger
