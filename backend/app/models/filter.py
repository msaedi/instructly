# backend/app/models/filter.py
"""
Flexible filter system for the 3-level taxonomy.

This module defines the filter system that allows subcategories to have
configurable filter options. The schema supports:

  FilterDefinition → FilterOption (global pool of filter types & values)
  SubcategoryFilter → SubcategoryFilterOption (per-subcategory assignments)

For example, the "Math" subcategory might have filters for:
  - grade_level: [Pre-K, Elementary, Middle School, ...]
  - course_level: [Regular, Honors, AP, IB]
  - goal: [Homework Help, Test Prep, Enrichment, ...]
"""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import relationship
import ulid

from ..database import Base


class FilterDefinition(Base):
    """
    A global filter type (e.g., "grade_level", "goal", "style").

    Attributes:
        id: ULID primary key
        key: Unique machine-readable key (e.g., "grade_level")
        display_name: Human-readable name (e.g., "Grade Level")
        filter_type: Type of filter (single_select or multi_select)
        created_at: Timestamp when created

    Relationships:
        options: All possible values for this filter
    """

    __tablename__ = "filter_definitions"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    key = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    filter_type = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    options = relationship(
        "FilterOption",
        back_populates="filter_definition",
        cascade="all, delete-orphan",
        order_by="FilterOption.display_order",
    )

    def __repr__(self) -> str:
        return f"<FilterDefinition {self.key} ({self.filter_type})>"

    def to_dict(self, include_options: bool = False) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "key": self.key,
            "display_name": self.display_name,
            "filter_type": self.filter_type,
        }
        if include_options:
            data["options"] = [o.to_dict() for o in self.options]
        return data


class FilterOption(Base):
    """
    A specific value for a filter definition (e.g., "elementary" for grade_level).

    Attributes:
        id: ULID primary key
        filter_definition_id: FK to filter_definitions
        value: Machine-readable value (e.g., "elementary")
        display_name: Human-readable label (e.g., "Elementary (K-5)")
        display_order: Order for UI display
        created_at: Timestamp when created

    Relationships:
        filter_definition: The parent FilterDefinition
    """

    __tablename__ = "filter_options"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    filter_definition_id = Column(
        String(26),
        ForeignKey("filter_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value = Column(String(100), nullable=False)
    display_name = Column(String(200), nullable=False)
    display_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    filter_definition = relationship("FilterDefinition", back_populates="options")

    __table_args__ = (
        UniqueConstraint("filter_definition_id", "value", name="uq_filter_option_definition_value"),
    )

    def __repr__(self) -> str:
        return f"<FilterOption {self.value} ({self.display_name})>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "value": self.value,
            "display_name": self.display_name,
            "display_order": self.display_order,
        }


class SubcategoryFilter(Base):
    """
    Links a subcategory to a filter definition.

    This junction table determines which filters are available for
    each subcategory. For example, "Math" subcategory gets "grade_level"
    and "course_level" filters, while "Ballet" gets "style" filter.

    Attributes:
        id: ULID primary key
        subcategory_id: FK to service_subcategories
        filter_definition_id: FK to filter_definitions
        display_order: Order for UI display

    Relationships:
        subcategory: The ServiceSubcategory
        filter_definition: The FilterDefinition
        filter_options: Which specific options are valid for this subcategory+filter combo
    """

    __tablename__ = "subcategory_filters"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    subcategory_id = Column(
        String(26),
        ForeignKey("service_subcategories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filter_definition_id = Column(
        String(26),
        ForeignKey("filter_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_order = Column(Integer, nullable=False, default=0)

    # Relationships
    subcategory = relationship("ServiceSubcategory", back_populates="subcategory_filters")
    filter_definition = relationship("FilterDefinition")
    filter_options = relationship(
        "SubcategoryFilterOption",
        back_populates="subcategory_filter",
        cascade="all, delete-orphan",
        order_by="SubcategoryFilterOption.display_order",
    )

    __table_args__ = (
        UniqueConstraint(
            "subcategory_id",
            "filter_definition_id",
            name="uq_subcategory_filter_definition",
        ),
    )

    def __repr__(self) -> str:
        return f"<SubcategoryFilter sub={self.subcategory_id} filter={self.filter_definition_id}>"


class SubcategoryFilterOption(Base):
    """
    Links a subcategory-filter assignment to specific valid options.

    This allows each subcategory to have a curated subset of filter options.
    For example, "Math" might have grade_level options [Pre-K through College],
    while "Test Prep" only has [Middle School, High School, College, Adult].

    Attributes:
        id: ULID primary key
        subcategory_filter_id: FK to subcategory_filters
        filter_option_id: FK to filter_options
        display_order: Order for UI display

    Relationships:
        subcategory_filter: The parent SubcategoryFilter
        filter_option: The specific FilterOption
    """

    __tablename__ = "subcategory_filter_options"

    id = Column(String(26), primary_key=True, default=lambda: str(ulid.ULID()))
    subcategory_filter_id = Column(
        String(26),
        ForeignKey("subcategory_filters.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filter_option_id = Column(
        String(26),
        ForeignKey("filter_options.id", ondelete="CASCADE"),
        nullable=False,
    )
    display_order = Column(Integer, nullable=False, default=0)

    # Relationships
    subcategory_filter = relationship("SubcategoryFilter", back_populates="filter_options")
    filter_option = relationship("FilterOption")

    __table_args__ = (
        UniqueConstraint(
            "subcategory_filter_id",
            "filter_option_id",
            name="uq_subcategory_filter_option",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SubcategoryFilterOption sf={self.subcategory_filter_id} "
            f"opt={self.filter_option_id}>"
        )
