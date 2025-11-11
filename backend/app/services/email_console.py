from typing import Any, Mapping, Optional, Sequence


class ConsoleEmailService:
    """No-op email service used when real providers are unavailable."""

    def __init__(self, *_: Any, **__: Any) -> None:
        pass

    def send_email(
        self,
        to_email: str,
        subject: str,
        body_html: str,
        *,
        tags: Optional[Sequence[str]] = None,
    ) -> bool:
        return True

    def send_template(
        self,
        to_email: str,
        template_name: str,
        context: Mapping[str, Any],
        *,
        tags: Optional[Sequence[str]] = None,
    ) -> bool:
        return True
