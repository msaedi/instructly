"""
Pydantic response models for Codebase Metrics endpoints.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CodebaseCategoryStats(BaseModel):
    files: int = Field(..., ge=0)
    lines: int = Field(..., ge=0)


class CodebaseFileInfo(BaseModel):
    path: str
    lines: int = Field(..., ge=0)
    lines_with_blanks: int = Field(..., ge=0)
    size_kb: float = Field(..., ge=0)


class CodebaseSection(BaseModel):
    total_files: int = Field(..., ge=0)
    total_lines: int = Field(..., ge=0)
    total_lines_with_blanks: int = Field(..., ge=0)
    categories: Dict[str, CodebaseCategoryStats] = Field(default_factory=dict)
    largest_files: List[CodebaseFileInfo] = Field(default_factory=list)


class GitStats(BaseModel):
    total_commits: int = Field(..., ge=0)
    unique_contributors: int = Field(..., ge=0)
    first_commit: str
    last_commit: str
    current_branch: str


class CodebaseMetricsSummary(BaseModel):
    total_lines: int = Field(..., ge=0)
    total_files: int = Field(..., ge=0)


class CodebaseMetricsResponse(BaseModel):
    timestamp: datetime
    backend: CodebaseSection
    frontend: CodebaseSection
    git: GitStats
    summary: CodebaseMetricsSummary


class CodebaseHistoryEntry(BaseModel):
    timestamp: datetime
    total_lines: int = Field(..., ge=0)
    total_files: int = Field(..., ge=0)
    backend_lines: int = Field(..., ge=0)
    frontend_lines: int = Field(..., ge=0)
    git_commits: int = Field(..., ge=0)
    # Optional nested categories breakdown from history file
    categories: Optional[Dict[str, Dict[str, CodebaseCategoryStats]]] = None


class CodebaseHistoryResponse(BaseModel):
    items: List[CodebaseHistoryEntry] = Field(default_factory=list)
    current: Optional[CodebaseMetricsResponse] = None


class AppendHistoryResponse(BaseModel):
    status: str
    count: int = Field(..., ge=0)
