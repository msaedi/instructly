"""Repository helpers for per-format instructor service pricing."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, cast

from sqlalchemy import case
from sqlalchemy.orm import Session

from app.core.exceptions import RepositoryException
from app.models.service_catalog import SERVICE_PRICE_FORMAT_ORDER, ServiceFormatPrice

from .base_repository import BaseRepository

# CASE expression to order pricing rows by canonical format order
_FORMAT_ORDER_EXPR = case(
    {fmt: idx for idx, fmt in enumerate(SERVICE_PRICE_FORMAT_ORDER)},
    value=ServiceFormatPrice.format,
    else_=99,
)


class ServiceFormatPricingRepository(BaseRepository[ServiceFormatPrice]):
    """Repository for service_format_pricing access patterns."""

    def __init__(self, db: Session):
        super().__init__(db, ServiceFormatPrice)

    def sync_format_prices(
        self, service_id: str, prices: List[dict[str, Any]]
    ) -> List[ServiceFormatPrice]:
        """Replace all pricing rows for a service within the current transaction."""
        if not prices:
            raise RepositoryException(
                "Cannot sync empty format prices — at least one format required"
            )
        self.db.query(ServiceFormatPrice).filter(
            ServiceFormatPrice.service_id == service_id
        ).delete()
        self.db.flush()  # Ensure deletes execute before inserts to avoid UNIQUE constraint timing issues
        rows: List[ServiceFormatPrice] = []
        for price in prices:
            row = self.create(service_id=service_id, **price)
            rows.append(row)
        return rows

    def get_prices_for_service(self, service_id: str) -> List[ServiceFormatPrice]:
        """Load pricing rows for a single service in stable format order."""
        return cast(
            List[ServiceFormatPrice],
            self.db.query(ServiceFormatPrice)
            .filter(ServiceFormatPrice.service_id == service_id)
            .order_by(_FORMAT_ORDER_EXPR)
            .all(),
        )

    def get_prices_for_services(
        self, service_ids: Iterable[str]
    ) -> Dict[str, List[ServiceFormatPrice]]:
        """Bulk load pricing rows for many services."""
        ids = [service_id for service_id in service_ids if service_id]
        if not ids:
            return {}
        rows = (
            self.db.query(ServiceFormatPrice)
            .filter(ServiceFormatPrice.service_id.in_(ids))
            .order_by(_FORMAT_ORDER_EXPR)
            .all()
        )
        grouped: Dict[str, List[ServiceFormatPrice]] = defaultdict(list)
        for row in rows:
            grouped[row.service_id].append(row)
        return dict(grouped)
