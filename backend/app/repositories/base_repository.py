# backend/app/repositories/base_repository.py
"""
Base Repository Pattern for InstaInstru Platform

Provides the foundation for all repository classes with:
- Common CRUD operations
- Type safety with generics
- Transaction support (managed by services)
- Query builder helpers
- Performance optimization patterns

The repository pattern separates data access from business logic,
making the code more testable and maintainable.
"""

from abc import ABC, abstractmethod
from contextlib import contextmanager
import logging
from typing import Any, Dict, Generic, Iterator, List, Optional, Type, TypeVar

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Query, Session

from app.database.session_utils import get_dialect_name

from ..core.exceptions import RepositoryException

# Type variable for generic model support
T = TypeVar("T")

logger = logging.getLogger(__name__)


class IRepository(ABC, Generic[T]):
    """
    Abstract repository interface defining core data access methods.

    All repositories must implement these methods to ensure consistency
    across the application.
    """

    @abstractmethod
    def get_by_id(self, id: int, load_relationships: bool = True) -> Optional[T]:
        """
        Retrieve an entity by its primary key.

        Args:
            id: The primary key value
            load_relationships: Whether to eager load relationships

        Returns:
            The entity if found, None otherwise
        """

    @abstractmethod
    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """
        Retrieve all entities with pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return

        Returns:
            List of entities
        """

    @abstractmethod
    def create(self, **kwargs) -> T:
        """
        Create a new entity.

        Args:
            **kwargs: Entity attributes

        Returns:
            The created entity

        Raises:
            RepositoryException: If creation fails
        """

    @abstractmethod
    def update(self, id: int, **kwargs) -> Optional[T]:
        """
        Update an existing entity.

        Args:
            id: The primary key value
            **kwargs: Attributes to update

        Returns:
            The updated entity if found, None otherwise

        Raises:
            RepositoryException: If update fails
        """

    @abstractmethod
    def delete(self, id: int) -> bool:
        """
        Delete an entity by its primary key.

        Args:
            id: The primary key value

        Returns:
            True if deleted, False if not found

        Raises:
            RepositoryException: If deletion fails due to constraints
        """

    @abstractmethod
    def exists(self, **kwargs) -> bool:
        """
        Check if an entity exists with given criteria.

        Args:
            **kwargs: Filter criteria

        Returns:
            True if exists, False otherwise
        """

    @abstractmethod
    def count(self, **kwargs) -> int:
        """
        Count entities matching given criteria.

        Args:
            **kwargs: Filter criteria

        Returns:
            Number of matching entities
        """


class BaseRepository(IRepository[T]):
    """
    Concrete base repository implementation with common data access patterns.

    This class provides default implementations for CRUD operations and
    can be extended by specific repositories to add custom queries.

    Attributes:
        db: SQLAlchemy session
        model: SQLAlchemy model class
    """

    def __init__(self, db: Session, model: Type[T]):
        """
        Initialize repository with database session and model.

        Args:
            db: SQLAlchemy session (managed by service layer)
            model: SQLAlchemy model class
        """
        self.db = db
        self.model = model
        self.logger = logging.getLogger(f"{__name__}.{model.__name__}")

    @property
    def dialect_name(self) -> str:
        return get_dialect_name(self.db)

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Context manager that commits/rolls back the underlying session."""
        try:
            yield self.db
            self.db.commit()
        except SQLAlchemyError as exc:
            self.logger.error("Repository transaction failed: %s", exc)
            self.db.rollback()
            raise
        except Exception:
            self.db.rollback()
            raise

    def get_by_id(self, id: int, load_relationships: bool = True) -> Optional[T]:
        """
        Retrieve an entity by its primary key.

        Implements eager loading for relationships when requested.
        """
        try:
            query = self.db.query(self.model).filter(self.model.id == id)

            # Optionally eager load relationships
            if load_relationships:
                query = self._apply_eager_loading(query)

            return query.first()
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting {self.model.__name__} by id {id}: {str(e)}")
            raise RepositoryException(f"Failed to retrieve {self.model.__name__}: {str(e)}")

    def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        """
        Retrieve all entities with pagination.

        Default limit of 100 to prevent memory issues.
        """
        try:
            return self.db.query(self.model).offset(skip).limit(limit).all()
        except SQLAlchemyError as e:
            self.logger.error(f"Error getting all {self.model.__name__}: {str(e)}")
            raise RepositoryException(f"Failed to retrieve {self.model.__name__} list: {str(e)}")

    def refresh(self, instance: T) -> None:
        """Refresh an instance from the database."""
        self.db.refresh(instance)

    def create(self, **kwargs) -> T:
        """
        Create a new entity.

        Note: Does NOT commit - transaction management is handled by service layer.
        """
        try:
            # Handle special case for created_at if provided
            created_at = kwargs.pop("created_at", None)

            entity = self.model(**kwargs)

            # If created_at was provided, set it explicitly
            if created_at and hasattr(entity, "created_at"):
                entity.created_at = created_at

            self.db.add(entity)
            self.db.flush()  # Get ID without committing
            return entity
        except IntegrityError as exc:
            self.logger.error(
                "Integrity error creating %s: %s", self.model.__name__, exc, exc_info=True
            )
            self.db.rollback()
            raise RepositoryException(f"Integrity constraint violated: {exc}") from exc
        except SQLAlchemyError as e:
            self.logger.error(f"Error creating {self.model.__name__}: {str(e)}")
            self.db.rollback()
            raise RepositoryException(f"Failed to create {self.model.__name__}: {str(e)}")

    def flush(self) -> None:
        """Flush pending ORM changes."""
        self.db.flush()

    def update(self, id: int, **kwargs) -> Optional[T]:
        """
        Update an existing entity.

        Only updates provided fields, preserves others.
        """
        try:
            entity = self.get_by_id(id, load_relationships=False)
            if not entity:
                return None

            # Update only provided fields
            for key, value in kwargs.items():
                if hasattr(entity, key):
                    setattr(entity, key, value)

            self.db.flush()
            return entity
        except SQLAlchemyError as e:
            self.logger.error(f"Error updating {self.model.__name__} {id}: {str(e)}")
            self.db.rollback()
            raise RepositoryException(f"Failed to update {self.model.__name__}: {str(e)}")

    def delete(self, id: int) -> bool:
        """
        Delete an entity by its primary key.

        Returns False if entity not found, raises exception for constraint violations.
        """
        try:
            entity = self.get_by_id(id, load_relationships=False)
            if not entity:
                return False

            self.db.delete(entity)
            self.db.flush()
            return True
        except IntegrityError as e:
            self.logger.error(
                f"Cannot delete {self.model.__name__} {id} due to constraints: {str(e)}"
            )
            self.db.rollback()
            raise RepositoryException(f"Cannot delete due to existing references: {str(e)}")
        except SQLAlchemyError as e:
            self.logger.error(f"Error deleting {self.model.__name__} {id}: {str(e)}")
            self.db.rollback()
            raise RepositoryException(f"Failed to delete {self.model.__name__}: {str(e)}")

    def exists(self, **kwargs) -> bool:
        """Check if an entity exists with given criteria."""
        try:
            return self.db.query(self.model).filter_by(**kwargs).first() is not None
        except SQLAlchemyError as e:
            self.logger.error(f"Error checking existence: {str(e)}")
            raise RepositoryException(f"Failed to check existence: {str(e)}")

    def count(self, **kwargs) -> int:
        """Count entities matching given criteria."""
        try:
            return self.db.query(self.model).filter_by(**kwargs).count()
        except SQLAlchemyError as e:
            self.logger.error(f"Error counting records: {str(e)}")
            raise RepositoryException(f"Failed to count records: {str(e)}")

    def find_by(self, **kwargs) -> List[T]:
        """
        Find entities by given criteria.

        Args:
            **kwargs: Filter criteria (exact match)

        Returns:
            List of matching entities
        """
        try:
            return self.db.query(self.model).filter_by(**kwargs).all()
        except SQLAlchemyError as e:
            self.logger.error(f"Error finding by criteria: {str(e)}")
            raise RepositoryException(f"Failed to find records: {str(e)}")

    def find_one_by(self, **kwargs) -> Optional[T]:
        """
        Find a single entity by given criteria.

        Args:
            **kwargs: Filter criteria (exact match)

        Returns:
            First matching entity or None
        """
        try:
            return self.db.query(self.model).filter_by(**kwargs).first()
        except SQLAlchemyError as e:
            self.logger.error(f"Error finding one by criteria: {str(e)}")
            raise RepositoryException(f"Failed to find record: {str(e)}")

    def bulk_create(self, entities: List[Dict[str, Any]]) -> List[T]:
        """
        Create multiple entities efficiently.

        Args:
            entities: List of entity data dictionaries

        Returns:
            List of created entities
        """
        try:
            db_entities = [self.model(**data) for data in entities]
            self.db.bulk_save_objects(db_entities, return_defaults=True)
            self.db.flush()
            return db_entities
        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk creating: {str(e)}")
            raise RepositoryException(f"Failed to bulk create: {str(e)}")

    def bulk_update(self, updates: List[Dict[str, Any]]) -> int:
        """
        Update multiple entities efficiently.

        Optimized: loads all entities in one query, updates in memory, single flush.

        Args:
            updates: List of dicts with 'id' and fields to update

        Returns:
            Number of entities updated
        """
        if not updates:
            return 0

        try:
            # Extract all IDs and build lookup
            update_lookup = {}
            for update_data in updates:
                entity_id = update_data.get("id")
                if entity_id:
                    update_lookup[entity_id] = {k: v for k, v in update_data.items() if k != "id"}

            if not update_lookup:
                return 0

            # Load all entities in ONE query
            entities = (
                self.db.query(self.model)
                .filter(self.model.id.in_(list(update_lookup.keys())))
                .all()
            )

            # Update in memory
            updated_count = 0
            for entity in entities:
                update_data = update_lookup.get(entity.id)
                if update_data:
                    for key, value in update_data.items():
                        setattr(entity, key, value)
                    updated_count += 1

            # Single flush for all updates
            self.db.flush()
            return updated_count
        except SQLAlchemyError as e:
            self.logger.error(f"Error bulk updating: {str(e)}")
            raise RepositoryException(f"Failed to bulk update: {str(e)}")

    # Protected helper methods for use by subclasses

    def _apply_eager_loading(self, query: Query) -> Query:
        """
        Apply eager loading to relationships.

        Override in subclasses to specify which relationships to load.
        """
        # Default: no eager loading
        # Subclasses can override to add joinedload/selectinload
        return query

    def _build_query(self) -> Query:
        """Get base query for the model."""
        return self.db.query(self.model)

    def _execute_query(self, query: Query) -> List[T]:
        """Execute query with error handling."""
        try:
            return query.all()
        except SQLAlchemyError as e:
            self.logger.error(f"Query execution error: {str(e)}")
            raise RepositoryException(f"Query failed: {str(e)}")

    def _execute_scalar(self, query: Query) -> Any:
        """Execute scalar query with error handling."""
        try:
            return query.scalar()
        except SQLAlchemyError as e:
            self.logger.error(f"Scalar query error: {str(e)}")
            raise RepositoryException(f"Scalar query failed: {str(e)}")
