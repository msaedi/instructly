# backend/app/models/subcategory.py
"""
Service subcategory model for the 3-level taxonomy system.

Subcategories sit between categories and services:
  Category → Subcategory → Service

Each subcategory belongs to one category and contains one or more services.
"""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class ServiceSubcategory(Base):
    """
    Model representing a service subcategory.

    Subcategories organize services within a category. For example,
    the "Music" category contains subcategories like "Piano", "Guitar",
    "Voice & Singing", etc.

    Attributes:
        id: ULID primary key
        category_id: FK to service_categories
        name: Display name (e.g., "Piano", "Guitar")
        display_order: Order for UI display (lower numbers first)
        created_at: Timestamp when created
        updated_at: Timestamp when last updated

    Relationships:
        category: The ServiceCategory this belongs to
        services: List of ServiceCatalog entries in this subcategory
        subcategory_filters: Filter definitions assigned to this subcategory
    """

    __tablename__ = "service_subcategories"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    category_id = Column(
        String(26),
        ForeignKey("service_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    category = relationship("ServiceCategory", back_populates="subcategories")
    services = relationship(
        "ServiceCatalog",
        back_populates="subcategory",
        order_by="ServiceCatalog.display_order",
    )
    subcategory_filters = relationship(
        "SubcategoryFilter",
        back_populates="subcategory",
        cascade="all, delete-orphan",
        order_by="SubcategoryFilter.display_order",
    )

    __table_args__ = (UniqueConstraint("category_id", "name", name="uq_subcategory_category_name"),)

    def __repr__(self) -> str:
        return f"<ServiceSubcategory {self.name} (category_id={self.category_id})>"

    @property
    def service_count(self) -> int:
        """Count of services in this subcategory."""
        return len(self.services) if self.services else 0

    def to_dict(self, include_services: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        data: Dict[str, Any] = {
            "id": self.id,
            "category_id": self.category_id,
            "name": self.name,
            "display_order": self.display_order,
            "service_count": self.service_count,
        }
        if include_services:
            data["services"] = [s.to_dict() for s in self.services]
        return data
