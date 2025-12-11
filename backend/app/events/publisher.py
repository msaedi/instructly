"""Event publisher - queues events for background processing."""
from datetime import datetime
import json
from typing import Any, Dict, Protocol

from app.repositories.job_repository import JobRepository


class Event(Protocol):
    """Protocol for event types."""

    def to_dict(self) -> Dict[str, Any]:
        ...


class EventPublisher:
    """Publishes domain events to the job queue for async processing."""

    def __init__(self, job_repository: JobRepository):
        self.job_repo = job_repository

    def publish(self, event: Event) -> None:
        """
        Queue an event for background processing.

        Events are processed by the background worker, which routes them
        to the appropriate handler based on event type.
        """
        event_type = type(event).__name__
        payload = event.to_dict()

        # Convert datetime objects to ISO strings for JSON serialization
        for key, value in payload.items():
            if isinstance(value, datetime):
                payload[key] = value.isoformat()

        self.job_repo.enqueue(type=f"event:{event_type}", payload=json.dumps(payload))
