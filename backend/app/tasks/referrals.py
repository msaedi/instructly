"""Celery tasks for referral program maintenance."""

from __future__ import annotations

from typing import Dict

from app.services.referral_unlocker import main as unlocker_main
from app.tasks.celery_app import celery_app


@celery_app.task(name="app.tasks.referrals.run_unlocker")
def run_unlocker(limit: int = 200, dry_run: bool = False) -> Dict[str, int]:
    """Run the referral unlocker once and return its summary."""
    return unlocker_main(limit=limit, dry_run=dry_run)
