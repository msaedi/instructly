"""Shared types for service catalog repositories."""

from typing import TypedDict

from ...models.service_catalog import ServiceAnalytics, ServiceCatalog


class PopularServiceMetrics(TypedDict):
    service: ServiceCatalog
    analytics: ServiceAnalytics
    popularity_score: float


class MinimalServiceInfo(TypedDict):
    id: str
    name: str
    slug: str
