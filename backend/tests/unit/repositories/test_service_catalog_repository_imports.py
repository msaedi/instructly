from app.repositories.service_catalog_repository import (
    MinimalServiceInfo,
    PopularServiceMetrics,
    ServiceAnalyticsRepository,
    ServiceCatalogRepository,
    _apply_active_catalog_predicate,
    _apply_instructor_service_active_filter,
    _check_pg_trgm,
    _escape_like,
    _money_to_cents,
)


def test_service_catalog_repository_facade_exports_remain_available():
    assert ServiceCatalogRepository.__name__ == "ServiceCatalogRepository"
    assert ServiceAnalyticsRepository.__name__ == "ServiceAnalyticsRepository"
    assert MinimalServiceInfo.__name__ == "MinimalServiceInfo"
    assert PopularServiceMetrics.__name__ == "PopularServiceMetrics"
    assert callable(_apply_active_catalog_predicate)
    assert callable(_apply_instructor_service_active_filter)
    assert callable(_check_pg_trgm)
    assert callable(_escape_like)
    assert callable(_money_to_cents)
