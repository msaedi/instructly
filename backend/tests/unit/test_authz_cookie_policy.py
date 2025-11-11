from app.api.dependencies.authz import _cookie_auth_allowed


def test_cookie_auth_allowed_only_in_dev_like_modes() -> None:
    assert _cookie_auth_allowed("local") is True
    assert _cookie_auth_allowed("dev") is True
    assert _cookie_auth_allowed("ci") is True

    assert not _cookie_auth_allowed("preview")
    assert not _cookie_auth_allowed("staging")
    assert not _cookie_auth_allowed("prod")
    assert not _cookie_auth_allowed("production")


def test_cookie_auth_allowed_env_and_explicit_matrix() -> None:
    # env should not bypass hosted hard-deny
    assert _cookie_auth_allowed("preview", env="development") is False
    assert _cookie_auth_allowed("production", env="production") is False
    # happy paths
    assert _cookie_auth_allowed("dev", env=None) is True
    assert _cookie_auth_allowed("whatever", env="ci") is True
    # explicit overrides
    assert _cookie_auth_allowed("dev", explicit=False) is False
    assert _cookie_auth_allowed("dev", explicit=True) is True
    # explicit cannot force hosted bypass
    assert _cookie_auth_allowed("preview", explicit=True) is False
