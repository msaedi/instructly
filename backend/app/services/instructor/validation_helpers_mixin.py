from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from ...constants.pricing_defaults import PRICE_FLOOR_CENTS_CONFIG_KEY
from ...core.exceptions import BusinessRuleException
from ...models.service_catalog import SERVICE_FORMAT_ONLINE, ServiceCatalog
from ..base import BaseService
from .mixin_base import PRICE_FLOOR_CONFIG_KEYS, InstructorMixinBase


class InstructorValidationHelpersMixin(InstructorMixinBase):
    """Pure validation helpers shared by instructor offerings flows."""

    def _validate_catalog_ids(self, catalog_ids: List[str]) -> None:
        valid_ids_raw = self.catalog_repository.get_active_catalog_ids(catalog_ids)
        if isinstance(valid_ids_raw, set):
            valid_ids = valid_ids_raw
        elif isinstance(valid_ids_raw, (list, tuple)):
            valid_ids = set(valid_ids_raw)
        else:
            valid_ids = {
                catalog_id
                for catalog_id in catalog_ids
                if bool(self.catalog_repository.exists(id=catalog_id))
            }

        invalid_ids = set(catalog_ids) - valid_ids
        if invalid_ids:
            raise BusinessRuleException(
                f"Invalid service catalog IDs: {', '.join(map(str, invalid_ids))}"
            )

    @staticmethod
    def _normalize_format_prices(format_prices: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for row in format_prices:
            if isinstance(row, dict):
                format_value = row.get("format")
                hourly_rate_value = row.get("hourly_rate")
            else:
                format_value = getattr(row, "format", None)
                hourly_rate_value = getattr(row, "hourly_rate", None)

            format_name = str(format_value).strip()
            if format_name not in PRICE_FLOOR_CONFIG_KEYS:
                raise BusinessRuleException(
                    f"Unsupported service pricing format: {format_name}",
                    code="INVALID_SERVICE_FORMAT",
                )
            if hourly_rate_value is None:
                raise BusinessRuleException(
                    "Hourly rate is required for each format price",
                    code="MISSING_HOURLY_RATE",
                )
            normalized.append(
                {
                    "format": format_name,
                    "hourly_rate": Decimal(str(hourly_rate_value)),
                }
            )
        return normalized

    def _floor_for_format(self, format_name: str) -> Decimal:
        if format_name not in PRICE_FLOOR_CONFIG_KEYS:
            raise BusinessRuleException(
                f"Unknown pricing format: {format_name}",
                code="UNKNOWN_PRICING_FORMAT",
            )
        pricing_config, _ = self.config_service.get_pricing_config()
        floors = pricing_config.get(PRICE_FLOOR_CENTS_CONFIG_KEY, {})
        floor_key = PRICE_FLOOR_CONFIG_KEYS[format_name]
        cents_value = floors.get(floor_key, 0)
        return (Decimal(str(cents_value)) / Decimal("100")).quantize(Decimal("0.01"))

    @staticmethod
    def _validate_age_groups_subset(
        catalog_service: ServiceCatalog,
        age_groups: Optional[List[str]],
    ) -> None:
        if not age_groups:
            return
        eligible = set(catalog_service.eligible_age_groups or [])
        if not eligible:
            return
        invalid = sorted(set(age_groups) - eligible)
        if invalid:
            raise BusinessRuleException(
                f"Age groups {invalid} not eligible for {catalog_service.name}"
            )

    @BaseService.measure_operation("validate_service_format_prices")
    def validate_service_format_prices(
        self,
        *,
        instructor_id: str,
        catalog_service: ServiceCatalog,
        format_prices: Sequence[Dict[str, Any]],
    ) -> None:
        if not format_prices:
            raise BusinessRuleException(
                "Service must offer at least one location option",
                code="NO_LOCATION_OPTIONS",
            )

        seen_formats: set[str] = set()
        for row in format_prices:
            format_name = str(row["format"]).strip()
            if format_name in seen_formats:
                raise BusinessRuleException(
                    f"Duplicate format '{format_name}' is not allowed",
                    code="DUPLICATE_FORMAT_PRICE",
                )
            seen_formats.add(format_name)

            hourly_rate = Decimal(str(row["hourly_rate"]))
            if hourly_rate <= 0:
                raise BusinessRuleException("Hourly rate must be greater than 0")
            if hourly_rate > Decimal("1000"):
                raise BusinessRuleException("Hourly rate must be $1000 or less")

            floor_value = self._floor_for_format(format_name)
            if hourly_rate < floor_value:
                raise BusinessRuleException(
                    f"Minimum price for {format_name} is ${floor_value}",
                    code="PRICE_BELOW_FLOOR",
                )

        if SERVICE_FORMAT_ONLINE in seen_formats and not bool(catalog_service.online_capable):
            raise BusinessRuleException(
                f"{catalog_service.name} cannot be offered online",
                code="ONLINE_NOT_SUPPORTED",
            )
