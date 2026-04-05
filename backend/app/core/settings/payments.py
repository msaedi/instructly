from __future__ import annotations

from pydantic import Field, SecretStr


class PaymentsSettingsMixin:
    connect_return_path: str = Field(
        default="/instructor/onboarding/connect?connect_return=1",
        description="Frontend callback path after Stripe Connect onboarding",
    )
    stripe_publishable_key: str = Field(
        default="", description="Stripe publishable key for frontend"
    )
    stripe_secret_key: SecretStr = Field(
        default=SecretStr(""),
        description="Stripe secret key for backend API calls",
    )
    stripe_identity_restricted_key: SecretStr | None = Field(
        default=None,
        alias="STRIPE_IDENTITY_RESTRICTED_KEY",
        description="Restricted API key for accessing sensitive Identity verification data (DOB)",
    )
    stripe_webhook_secret: SecretStr = Field(
        default=SecretStr(""),
        description="Stripe webhook secret for local dev (Stripe CLI)",
    )
    stripe_webhook_secret_platform: SecretStr = Field(
        default=SecretStr(""),
        description="Platform events webhook secret (deployed)",
    )
    stripe_webhook_secret_connect: SecretStr = Field(
        default=SecretStr(""),
        description="Connect events webhook secret (deployed)",
    )
    stripe_platform_fee_percentage: float = Field(
        default=15, description="Platform fee percentage (15 = 15%)"
    )
    stripe_currency: str = Field(default="usd", description="Default currency for payments")

    @property
    def webhook_secrets(self) -> list[str]:
        """Build list of webhook secrets to try in order."""

        secrets: list[str] = []
        for value in (
            self.stripe_webhook_secret,
            self.stripe_webhook_secret_platform,
            self.stripe_webhook_secret_connect,
        ):
            secret_str = (
                value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
            )
            if secret_str:
                secrets.append(secret_str)
        return secrets
