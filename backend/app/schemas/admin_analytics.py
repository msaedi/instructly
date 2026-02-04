"""Schemas for MCP admin analytics tools."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class RevenuePeriod(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    THIS_QUARTER = "this_quarter"


class RevenueComparisonMode(str, Enum):
    PREVIOUS_PERIOD = "previous_period"
    SAME_PERIOD_LAST_MONTH = "same_period_last_month"
    SAME_PERIOD_LAST_YEAR = "same_period_last_year"


class RevenueBreakdownBy(str, Enum):
    DAY = "day"
    WEEK = "week"
    CATEGORY = "category"


class RevenueComparison(BaseModel):
    period: str
    gmv: Decimal
    gmv_delta: Decimal
    gmv_delta_pct: Decimal
    revenue_delta: Decimal
    revenue_delta_pct: Decimal


class RevenuePeriodBreakdown(BaseModel):
    period_label: str
    gmv: Decimal
    revenue: Decimal
    bookings: int


class RevenueHealth(BaseModel):
    status: str
    alerts: list[str] = Field(default_factory=list)


class RevenueDashboard(BaseModel):
    period: str
    period_start: datetime
    period_end: datetime
    gmv: Decimal
    platform_revenue: Decimal
    instructor_payouts: Decimal
    net_revenue: Decimal
    take_rate: Decimal
    total_bookings: int
    completed_bookings: int
    cancelled_bookings: int
    completion_rate: Decimal
    average_booking_value: Decimal
    comparison: RevenueComparison | None = None
    breakdown: list[RevenuePeriodBreakdown] | None = None
    health: RevenueHealth


class BookingFunnelPeriod(str, Enum):
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    THIS_MONTH = "this_month"


class FunnelSegmentBy(str, Enum):
    DEVICE = "device"
    CATEGORY = "category"
    SOURCE = "source"


class FunnelStage(BaseModel):
    stage: str
    count: int
    conversion_to_next: Decimal | None = None


class BookingFunnel(BaseModel):
    period: str
    stages: list[FunnelStage]
    overall_conversion: Decimal
    biggest_drop_off: str
    drop_off_rate: Decimal
    segments: dict[str, list[FunnelStage]] | None = None
    recommendations: list[str] = Field(default_factory=list)


class FunnelSnapshotPeriod(str, Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    THIS_MONTH = "this_month"


class FunnelSnapshotComparison(str, Enum):
    PREVIOUS_PERIOD = "previous_period"
    SAME_PERIOD_LAST_WEEK = "same_period_last_week"
    SAME_PERIOD_LAST_MONTH = "same_period_last_month"


class FunnelSnapshotStage(BaseModel):
    stage: str
    count: int
    conversion_rate: Decimal | None = None
    drop_off_rate: Decimal | None = None


class FunnelSnapshotPeriodData(BaseModel):
    period_start: datetime
    period_end: datetime
    stages: list[FunnelSnapshotStage]
    overall_conversion: Decimal


class FunnelSnapshotResponse(BaseModel):
    current_period: FunnelSnapshotPeriodData
    comparison_period: FunnelSnapshotPeriodData | None = None
    deltas: dict[str, Decimal] | None = None
    insights: list[str] = Field(default_factory=list)


class SupplyDemandPeriod(str, Enum):
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"


class SupplyMetrics(BaseModel):
    active_instructors: int
    total_availability_hours: Decimal
    avg_availability_per_instructor: Decimal
    new_instructors: int
    churned_instructors: int


class DemandMetrics(BaseModel):
    total_searches: int
    unique_searchers: int
    booking_attempts: int
    successful_bookings: int
    unfulfilled_searches: int


class BalanceMetrics(BaseModel):
    supply_utilization: Decimal
    demand_fulfillment: Decimal
    supply_demand_ratio: Decimal
    status: str


class SupplyGap(BaseModel):
    category: str
    location: str | None = None
    demand_score: Decimal
    supply_score: Decimal
    priority: str


class UnfulfilledSearch(BaseModel):
    query: str
    count: int
    closest_match: str | None = None


class SupplyDemand(BaseModel):
    period: str
    filters_applied: dict[str, str]
    supply: SupplyMetrics
    demand: DemandMetrics
    balance: BalanceMetrics
    gaps: list[SupplyGap] = Field(default_factory=list)
    top_unfulfilled: list[UnfulfilledSearch] = Field(default_factory=list)


class CategoryPerformancePeriod(str, Enum):
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    THIS_MONTH = "this_month"
    LAST_QUARTER = "last_quarter"


class CategorySortBy(str, Enum):
    REVENUE = "revenue"
    BOOKINGS = "bookings"
    GROWTH = "growth"
    CONVERSION = "conversion"


class CategoryMetrics(BaseModel):
    category_id: str
    category_name: str
    bookings: int
    revenue: Decimal
    gmv: Decimal
    avg_price: Decimal
    avg_rating: Decimal
    instructor_count: int
    student_count: int
    conversion_rate: Decimal
    repeat_rate: Decimal
    growth_pct: Decimal
    rank_change: int


class CategoryPerformance(BaseModel):
    period: str
    categories: list[CategoryMetrics]
    top_growing: CategoryMetrics | None = None
    top_revenue: CategoryMetrics | None = None
    needs_attention: list[CategoryMetrics] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)


class CohortUserType(str, Enum):
    STUDENT = "student"
    INSTRUCTOR = "instructor"


class CohortPeriod(str, Enum):
    WEEK = "week"
    MONTH = "month"


class CohortMetric(str, Enum):
    ACTIVE = "active"
    BOOKING = "booking"
    REVENUE = "revenue"


class CohortData(BaseModel):
    cohort_label: str
    cohort_size: int
    retention: list[Decimal]


class CohortRetention(BaseModel):
    user_type: str
    metric: str
    cohorts: list[CohortData]
    avg_retention: dict[int, Decimal]
    benchmark_comparison: str
    insights: list[str] = Field(default_factory=list)


class AlertSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class AlertCategory(str, Enum):
    REVENUE = "revenue"
    OPERATIONS = "operations"
    QUALITY = "quality"
    TECHNICAL = "technical"


class Alert(BaseModel):
    id: str
    severity: str
    category: str
    title: str
    description: str
    metric_name: str
    current_value: Decimal
    threshold_value: Decimal
    triggered_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    recommended_action: str | None = None


class PlatformAlerts(BaseModel):
    total_active: int
    alerts: list[Alert]
    by_severity: dict[str, int]
    by_category: dict[str, int]
