"""Shared typing surface for retriever repository mixins."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session


class RetrieverRepositoryMixinBase:
    """Runtime no-op base that keeps mixin MRO clean."""

    db: Session
    logger: logging.Logger
