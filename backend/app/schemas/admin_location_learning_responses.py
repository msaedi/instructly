"""Strict response models for admin location learning endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from ._strict_base import StrictModel


class AdminLocationLearningClickCount(StrictModel):
    region_boundary_id: str
    region_name: Optional[str] = None
    count: int


class AdminLocationLearningUnresolvedQueryItem(StrictModel):
    id: str
    query_normalized: str
    search_count: int
    unique_user_count: int
    click_count: int
    clicks: list[AdminLocationLearningClickCount]
    sample_original_queries: list[str]
    first_seen_at: datetime
    last_seen_at: datetime
    status: str


class AdminLocationLearningUnresolvedQueriesResponse(StrictModel):
    queries: list[AdminLocationLearningUnresolvedQueryItem]
    total: int


class AdminLocationLearningPendingAliasItem(StrictModel):
    id: str
    alias_normalized: str
    region_boundary_id: Optional[str] = None
    region_name: Optional[str] = None
    confidence: float
    user_count: int
    status: str
    created_at: datetime


class AdminLocationLearningPendingAliasesResponse(StrictModel):
    aliases: list[AdminLocationLearningPendingAliasItem]


class AdminLocationLearningLearnedAliasItem(StrictModel):
    alias_normalized: str
    region_boundary_id: str
    confidence: float
    status: str
    confirmations: int


class AdminLocationLearningProcessResponse(StrictModel):
    learned: list[AdminLocationLearningLearnedAliasItem]
    learned_count: int


class AdminLocationLearningAliasActionResponse(StrictModel):
    status: Literal["approved", "rejected"]
    alias_id: str


class AdminLocationLearningCreateAliasResponse(StrictModel):
    status: Literal["created"]
    alias_id: str


class AdminLocationLearningDismissQueryResponse(StrictModel):
    status: Literal["dismissed"]
    query_normalized: str


class AdminLocationLearningRegionItem(StrictModel):
    id: str
    name: str
    borough: Optional[str] = None


class AdminLocationLearningRegionsResponse(StrictModel):
    regions: list[AdminLocationLearningRegionItem]


__all__ = [
    "AdminLocationLearningAliasActionResponse",
    "AdminLocationLearningClickCount",
    "AdminLocationLearningCreateAliasResponse",
    "AdminLocationLearningDismissQueryResponse",
    "AdminLocationLearningLearnedAliasItem",
    "AdminLocationLearningPendingAliasItem",
    "AdminLocationLearningPendingAliasesResponse",
    "AdminLocationLearningRegionItem",
    "AdminLocationLearningRegionsResponse",
    "AdminLocationLearningProcessResponse",
    "AdminLocationLearningUnresolvedQueriesResponse",
    "AdminLocationLearningUnresolvedQueryItem",
]
