import pytest

from app.core.config import assert_env


@pytest.mark.parametrize(
    "site_mode,checkr_env",
    [
        ("prod", "production"),
        ("production", "production"),
        ("live", "production"),
        ("preview", "sandbox"),
        ("local", "sandbox"),
        ("staging", "sandbox"),
        ("PROD", "PRODUCTION"),
        (" local ", "SANDBOX"),
    ],
)
def test_assert_env_allows_safe_pairs(site_mode: str, checkr_env: str) -> None:
    assert_env(site_mode, checkr_env)


@pytest.mark.parametrize(
    "site_mode,checkr_env,expected_message",
    [
        ("prod", "sandbox", "Refusing to start: production requires CHECKR_ENV=production"),
        (
            "production",
            "",
            "Refusing to start: production requires CHECKR_ENV=production",
        ),
        (
            "preview",
            "production",
            "Refusing to start: non-prod requires CHECKR_ENV=sandbox",
        ),
        (
            "local",
            "production",
            "Refusing to start: non-prod requires CHECKR_ENV=sandbox",
        ),
    ],
)
def test_assert_env_rejects_unsafe_pairs(
    site_mode: str, checkr_env: str, expected_message: str
) -> None:
    with pytest.raises(RuntimeError) as exc:
        assert_env(site_mode, checkr_env)

    assert expected_message == str(exc.value)
