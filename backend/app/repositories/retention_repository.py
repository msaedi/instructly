# backend/app/repositories/retention_repository.py
"""
Repository for retention-oriented soft delete operations.

Provides thin wrappers around the SQL needed to count and purge
soft-deleted records while keeping database access out of the service layer.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import MetaData, Table, inspect, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement, func

from .base_repository import BaseRepository  # re-use transaction helper


class RetentionRepository(BaseRepository[object]):
    """Repository wrapper that exposes soft-delete purge primitives."""

    def __init__(self, db: Session) -> None:
        super().__init__(db, object)  # model unused; BaseRepository needs a placeholder
        self._metadata = MetaData()
        self._inspector = inspect(db.bind)

    def has_table(self, table_name: str) -> bool:
        """Check if the target table exists in the current database."""
        try:
            return bool(self._inspector.has_table(table_name))
        except SQLAlchemyError:
            return False

    def reflect_table(self, table_name: str) -> Optional[Table]:
        """Reflect the table definition for the given name."""
        try:
            return Table(table_name, self._metadata, autoload_with=self.db.bind)
        except SQLAlchemyError:
            return None

    def count_soft_deleted(
        self,
        table: Table,
        deleted_column: ColumnElement,
        cutoff: datetime,
    ) -> int:
        """Count rows where deleted_at is older than the cutoff."""
        stmt = (
            select(func.count())
            .select_from(table)
            .where(deleted_column.isnot(None))
            .where(deleted_column < cutoff)
        )
        result = self.db.execute(stmt).scalar()
        return int(result or 0)

    def fetch_soft_deleted_ids(
        self,
        table: Table,
        pk_column: ColumnElement,
        deleted_column: ColumnElement,
        cutoff: datetime,
        limit: int,
    ) -> list[object]:
        """Fetch primary keys for soft-deleted rows older than cutoff."""
        stmt = (
            select(pk_column)
            .where(deleted_column.isnot(None))
            .where(deleted_column < cutoff)
            .order_by(deleted_column.asc())
            .limit(limit)
        )
        return [row[0] for row in self.db.execute(stmt).all()]

    def delete_rows(self, table: Table, pk_column: ColumnElement, ids: Iterable[object]) -> int:
        """Delete rows by primary key."""
        delete_stmt = table.delete().where(pk_column.in_(list(ids)))
        result = self.db.execute(delete_stmt)
        if result.rowcount is not None:
            return int(result.rowcount)
        return len(list(ids))
