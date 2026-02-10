"""Celery tasks for referral program maintenance."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Dict, ParamSpec, TypeVar

from app.monitoring.sentry_crons import monitor_if_configured
from app.services.referral_unlocker import main as unlocker_main
from app.tasks.celery_app import celery_app

P = ParamSpec("P")
R = TypeVar("R")

if TYPE_CHECKING:

    def celery_task(*args: object, **kwargs: object) -> Callable[[Callable[P, R]], Callable[P, R]]:
        def decorator(func: Callable[P, R]) -> Callable[P, R]:
            return func

        return decorator

else:  # pragma: no cover - runtime registration uses Celery decorator
    celery_task = celery_app.task


@celery_task(name="app.tasks.referrals.run_unlocker")
@monitor_if_configured("referrals-unlock-every-15m")
def run_unlocker(limit: int = 200, dry_run: bool = False) -> Dict[str, int]:
    """Run the referral unlocker once and return its summary."""
    return unlocker_main(limit=limit, dry_run=dry_run)
