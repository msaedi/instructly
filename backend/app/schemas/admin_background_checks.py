"""Strict response models for admin background check endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from ..utils.strict import model_filter
from ._strict_base import StrictModel


class BGCReviewCountResponse(StrictModel):
    count: int


class BGCReviewItemModel(StrictModel):
    instructor_id: str
    name: str
    email: str
    bgc_status: str | None = None
    bgc_report_id: str | None = None
    bgc_completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    consented_at_recent: bool
    checkr_report_url: str | None = None
    consented_at_recent_at: datetime | None = None
    is_live: bool
    bgc_valid_until: datetime | None = None
    bgc_expires_in_days: int | None = None
    bgc_is_expired: bool = False
    in_dispute: bool = False
    dispute_note: str | None = None
    dispute_opened_at: datetime | None = None
    dispute_resolved_at: datetime | None = None
    bgc_eta: datetime | None = None


class BGCReviewListResponse(StrictModel):
    items: list[BGCReviewItemModel]
    next_cursor: str | None = None


class BGCCaseCountsResponse(StrictModel):
    review: int
    pending: int


class BGCCaseItemModel(StrictModel):
    instructor_id: str
    name: str
    email: str
    is_live: bool
    bgc_status: str | None = None
    bgc_report_id: str | None = None
    bgc_completed_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    checkr_report_url: str | None = None
    consent_recent: bool
    consent_recent_at: datetime | None = None
    bgc_valid_until: datetime | None = None
    bgc_expires_in_days: int | None = None
    bgc_is_expired: bool = False
    in_dispute: bool = False
    dispute_note: str | None = None
    dispute_opened_at: datetime | None = None
    dispute_resolved_at: datetime | None = None
    bgc_eta: datetime | None = None

    def to_review_model(self) -> BGCReviewItemModel:
        payload = {
            "instructor_id": self.instructor_id,
            "name": self.name,
            "email": self.email,
            "bgc_status": self.bgc_status,
            "bgc_report_id": self.bgc_report_id,
            "bgc_completed_at": self.bgc_completed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "consented_at_recent": self.consent_recent,
            "consented_at_recent_at": self.consent_recent_at,
            "checkr_report_url": self.checkr_report_url,
            "is_live": self.is_live,
            "bgc_valid_until": self.bgc_valid_until,
            "bgc_expires_in_days": self.bgc_expires_in_days,
            "bgc_is_expired": self.bgc_is_expired,
            "in_dispute": self.in_dispute,
            "dispute_note": self.dispute_note,
            "dispute_opened_at": self.dispute_opened_at,
            "dispute_resolved_at": self.dispute_resolved_at,
            "bgc_eta": self.bgc_eta,
        }
        return BGCReviewItemModel(**model_filter(BGCReviewItemModel, payload))


class BGCCaseListResponse(StrictModel):
    items: list[BGCCaseItemModel]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool


class BGCHistoryItem(StrictModel):
    id: str
    result: str
    package: str | None = None
    env: str
    completed_at: datetime
    created_at: datetime
    report_id_present: bool


class BGCHistoryResponse(StrictModel):
    items: list[BGCHistoryItem]
    next_cursor: str | None = None


class BGCDisputeResponse(StrictModel):
    ok: bool
    in_dispute: bool
    dispute_note: str | None = None
    dispute_opened_at: datetime | None = None
    dispute_resolved_at: datetime | None = None
    resumed: bool = False
    scheduled_for: datetime | None = None


class BGCExpiringItem(StrictModel):
    instructor_id: str
    email: str | None = None
    bgc_valid_until: datetime | None = None


class BGCOverrideResponse(StrictModel):
    ok: bool
    new_status: Literal["passed", "failed"]


class BGCLatestConsentResponse(StrictModel):
    instructor_id: str
    consented_at: datetime
    consent_version: str
    ip_address: str | None = None


class BGCWebhookLogEntry(StrictModel):
    id: str
    event_type: str
    delivery_id: str | None = None
    resource_id: str | None = None
    result: str | None = None
    http_status: int | None = None
    signature: str | None = None
    created_at: datetime
    payload: dict[str, Any]
    instructor_id: str | None = None
    report_id: str | None = None
    candidate_id: str | None = None
    invitation_id: str | None = None


class BGCWebhookLogListResponse(StrictModel):
    items: list[BGCWebhookLogEntry]
    next_cursor: str | None = None
    error_count_24h: int


class BGCWebhookStatsResponse(StrictModel):
    error_count_24h: int


__all__ = [
    "BGCReviewCountResponse",
    "BGCReviewItemModel",
    "BGCReviewListResponse",
    "BGCCaseCountsResponse",
    "BGCCaseItemModel",
    "BGCCaseListResponse",
    "BGCHistoryItem",
    "BGCHistoryResponse",
    "BGCDisputeResponse",
    "BGCExpiringItem",
    "BGCOverrideResponse",
    "BGCLatestConsentResponse",
    "BGCWebhookLogEntry",
    "BGCWebhookLogListResponse",
    "BGCWebhookStatsResponse",
]
