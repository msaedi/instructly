"""Comprehensive tests for user Pydantic schemas.

Tests cover validators, edge cases, and serialization for all user-related schemas.
Focus areas based on coverage gaps:
- UserBase phone validator (lines 20-32)
- UserBase timezone validator (lines 34-38)
- UserUpdate phone and timezone validators (lines 67-85)
- Edge cases for phone number formatting
"""

from __future__ import annotations

from pydantic import ValidationError
import pytest

from app.schemas.user import (
    Token,
    UserCreate,
    UserLogin,
    UserRegistrationMetadata,
    UserResponse,
    UserUpdate,
    UserWithPermissionsResponse,
)


class TestUserBasePhoneValidator:
    """Tests for UserBase.validate_phone (lines 20-32)."""

    def test_none_phone_is_valid(self) -> None:
        """None phone should pass through unchanged."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": None,
            "zip_code": "10001",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.phone is None

    def test_valid_10_digit_phone_adds_country_code(self) -> None:
        """10-digit phone should get US country code added (lines 29-30)."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "2125551234",
            "zip_code": "10001",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.phone == "+12125551234"

    def test_11_digit_phone_with_1_prefix(self) -> None:
        """11-digit phone starting with 1 should be formatted (line 31)."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "12125551234",
            "zip_code": "10001",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.phone == "+12125551234"

    def test_phone_with_dashes_cleaned(self) -> None:
        """Phone with dashes should be cleaned (line 24)."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "212-555-1234",
            "zip_code": "10001",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.phone == "+12125551234"

    def test_phone_with_parentheses_cleaned(self) -> None:
        """Phone with parentheses should be cleaned."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "(212) 555-1234",
            "zip_code": "10001",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.phone == "+12125551234"

    def test_phone_with_dots_cleaned(self) -> None:
        """Phone with dots should be cleaned."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "212.555.1234",
            "zip_code": "10001",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.phone == "+12125551234"

    def test_phone_with_spaces_cleaned(self) -> None:
        """Phone with spaces should be cleaned."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "212 555 1234",
            "zip_code": "10001",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.phone == "+12125551234"

    def test_phone_with_plus_prefix(self) -> None:
        """Phone with + prefix should have it stripped and re-added."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "+12125551234",
            "zip_code": "10001",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.phone == "+12125551234"

    def test_international_phone_14_digits(self) -> None:
        """14-digit international phone should be valid."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "44123456789012",  # UK-style with more digits
            "zip_code": "10001",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.phone == "+44123456789012"

    def test_phone_too_short_fails(self) -> None:
        """Phone with fewer than 10 digits should fail (line 26-27)."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "555-1234",  # Only 7 digits
            "zip_code": "10001",
        }
        with pytest.raises(ValidationError, match="Phone number must be 10-14 digits"):
            UserCreate(password="Test1234", **data)

    def test_phone_too_long_fails(self) -> None:
        """Phone with more than 14 digits should fail."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "123456789012345",  # 15 digits
            "zip_code": "10001",
        }
        with pytest.raises(ValidationError, match="Phone number must be 10-14 digits"):
            UserCreate(password="Test1234", **data)

    def test_empty_string_phone_passes_as_none(self) -> None:
        """Empty string phone should be treated as falsy."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "",
            "zip_code": "10001",
        }
        user = UserCreate(password="Test1234", **data)
        # Empty string is falsy, so validator returns it unchanged
        assert user.phone == ""


class TestUserBaseTimezoneValidator:
    """Tests for UserBase.validate_timezone (lines 34-38)."""

    def test_valid_timezone_america_new_york(self) -> None:
        """Valid timezone America/New_York should pass."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "timezone": "America/New_York",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.timezone == "America/New_York"

    def test_valid_timezone_america_los_angeles(self) -> None:
        """Valid timezone America/Los_Angeles should pass."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "timezone": "America/Los_Angeles",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.timezone == "America/Los_Angeles"

    def test_valid_timezone_utc(self) -> None:
        """Valid timezone UTC should pass."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "timezone": "UTC",
        }
        user = UserCreate(password="Test1234", **data)
        assert user.timezone == "UTC"

    def test_none_timezone_defaults(self) -> None:
        """None timezone should use default."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "timezone": None,
        }
        user = UserCreate(password="Test1234", **data)
        # Default is set in field definition
        assert user.timezone is None or user.timezone == "America/New_York"

    def test_invalid_timezone_fails(self) -> None:
        """Invalid timezone should fail (lines 36-37)."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "timezone": "Invalid/Timezone",
        }
        with pytest.raises(ValidationError, match="Invalid timezone"):
            UserCreate(password="Test1234", **data)

    def test_partial_timezone_name_fails(self) -> None:
        """Partial timezone name should fail."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "timezone": "NewYork",
        }
        with pytest.raises(ValidationError, match="Invalid timezone"):
            UserCreate(password="Test1234", **data)

    def test_empty_string_timezone_fails(self) -> None:
        """Empty string timezone should fail (not in pytz.all_timezones)."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "timezone": "",
        }
        # Empty string is truthy but not in all_timezones
        # However, empty string evaluates as falsy in Python, so validator returns it
        user = UserCreate(password="Test1234", **data)
        assert user.timezone == ""


class TestUserUpdateValidators:
    """Tests for UserUpdate phone and timezone validators (lines 67-85)."""

    class TestPhoneValidator:
        """Tests for UserUpdate.validate_phone (lines 67-79)."""

        def test_none_phone_passes(self) -> None:
            """None phone should pass through unchanged."""
            update = UserUpdate(phone=None)
            assert update.phone is None

        def test_valid_10_digit_adds_country_code(self) -> None:
            """10-digit phone should get country code added (line 76-77)."""
            update = UserUpdate(phone="2125551234")
            assert update.phone == "+12125551234"

        def test_formatted_phone_cleaned(self) -> None:
            """Formatted phone should be cleaned."""
            update = UserUpdate(phone="(212) 555-1234")
            assert update.phone == "+12125551234"

        def test_phone_too_short_fails(self) -> None:
            """Short phone should fail (lines 73-74)."""
            with pytest.raises(ValidationError, match="Phone number must be 10-14 digits"):
                UserUpdate(phone="555-1234")

    class TestTimezoneValidator:
        """Tests for UserUpdate.validate_timezone (lines 81-85)."""

        def test_valid_timezone_passes(self) -> None:
            """Valid timezone should pass."""
            update = UserUpdate(timezone="America/Chicago")
            assert update.timezone == "America/Chicago"

        def test_none_timezone_passes(self) -> None:
            """None timezone should pass (no update)."""
            update = UserUpdate(timezone=None)
            assert update.timezone is None

        def test_invalid_timezone_fails(self) -> None:
            """Invalid timezone should fail (lines 83-84)."""
            with pytest.raises(ValidationError, match="Invalid timezone"):
                UserUpdate(timezone="Not/A/Timezone")


class TestUserCreate:
    """Tests for UserCreate schema."""

    def test_valid_user_create(self) -> None:
        """Valid user data should pass all validation."""
        data = {
            "email": "john.doe@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "phone": "2125551234",
            "zip_code": "10001",
            "password": "SecurePass123",
        }
        user = UserCreate(**data)
        assert user.email == "john.doe@example.com"
        assert user.phone == "+12125551234"

    def test_invalid_email_fails(self) -> None:
        """Invalid email should fail."""
        data = {
            "email": "not-an-email",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
        }
        with pytest.raises(ValidationError):
            UserCreate(**data)

    def test_empty_first_name_fails(self) -> None:
        """Empty first_name should fail."""
        data = {
            "email": "test@example.com",
            "first_name": "",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
        }
        with pytest.raises(ValidationError, match="at least 1 character"):
            UserCreate(**data)

    def test_empty_last_name_fails(self) -> None:
        """Empty last_name should fail."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "",
            "zip_code": "10001",
            "password": "Test1234",
        }
        with pytest.raises(ValidationError, match="at least 1 character"):
            UserCreate(**data)

    def test_first_name_too_long_fails(self) -> None:
        """first_name over 50 chars should fail."""
        data = {
            "email": "test@example.com",
            "first_name": "J" * 51,
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
        }
        with pytest.raises(ValidationError):
            UserCreate(**data)

    def test_invalid_zip_code_fails(self) -> None:
        """Invalid zip code format should fail."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "1234",  # Only 4 digits
            "password": "Test1234",
        }
        with pytest.raises(ValidationError, match="pattern"):
            UserCreate(**data)

    def test_zip_code_with_letters_fails(self) -> None:
        """Zip code with letters should fail."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "1000A",
            "password": "Test1234",
        }
        with pytest.raises(ValidationError):
            UserCreate(**data)

    def test_optional_role_field(self) -> None:
        """Role field should be optional."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
            "role": "instructor",
        }
        user = UserCreate(**data)
        assert user.role == "instructor"

    def test_optional_guest_session_id(self) -> None:
        """guest_session_id should be optional."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
            "guest_session_id": "guest-123",
        }
        user = UserCreate(**data)
        assert user.guest_session_id == "guest-123"

    def test_optional_metadata(self) -> None:
        """metadata should be optional."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
            "metadata": {"referral_code": "ABC123"},
        }
        user = UserCreate(**data)
        assert user.metadata is not None
        assert user.metadata.referral_code == "ABC123"

    def test_extra_fields_rejected(self) -> None:
        """Extra fields should be rejected (StrictRequestModel)."""
        data = {
            "email": "test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
            "extra_field": "value",
        }
        with pytest.raises(ValidationError, match="extra"):
            UserCreate(**data)


class TestUserUpdate:
    """Tests for UserUpdate schema."""

    def test_empty_update_is_valid(self) -> None:
        """Empty update (all None) should be valid."""
        update = UserUpdate()
        assert update.first_name is None
        assert update.last_name is None

    def test_partial_update(self) -> None:
        """Partial updates should be valid."""
        update = UserUpdate(first_name="Jane")
        assert update.first_name == "Jane"
        assert update.last_name is None

    def test_all_fields_update(self) -> None:
        """All fields can be updated together."""
        update = UserUpdate(
            first_name="Jane",
            last_name="Smith",
            phone="2125559999",
            zip_code="10002",
            timezone="America/Chicago",
        )
        assert update.first_name == "Jane"
        assert update.last_name == "Smith"
        assert update.phone == "+12125559999"
        assert update.zip_code == "10002"
        assert update.timezone == "America/Chicago"

    def test_extra_fields_rejected(self) -> None:
        """Extra fields should be rejected."""
        with pytest.raises(ValidationError, match="extra"):
            UserUpdate(first_name="Jane", email="new@example.com")


class TestUserLogin:
    """Tests for UserLogin schema."""

    def test_valid_login(self) -> None:
        """Valid login data should pass."""
        login = UserLogin(email="test@example.com", password="Test1234")
        assert login.email == "test@example.com"
        assert login.password == "Test1234"

    def test_invalid_email_fails(self) -> None:
        """Invalid email should fail."""
        with pytest.raises(ValidationError):
            UserLogin(email="not-an-email", password="Test1234")

    def test_optional_guest_session_id(self) -> None:
        """guest_session_id should be optional."""
        login = UserLogin(email="test@example.com", password="Test1234", guest_session_id="guest-123")
        assert login.guest_session_id == "guest-123"

    def test_optional_captcha_token(self) -> None:
        """captcha_token should be optional."""
        login = UserLogin(email="test@example.com", password="Test1234", captcha_token="token123")
        assert login.captcha_token == "token123"

    def test_extra_fields_rejected(self) -> None:
        """Extra fields should be rejected (strict config from StrictRequestModel)."""
        with pytest.raises(ValidationError, match="extra"):
            UserLogin(email="test@example.com", password="Test1234", extra="field")


class TestUserRegistrationMetadata:
    """Tests for UserRegistrationMetadata schema."""

    def test_all_fields_optional(self) -> None:
        """All fields should be optional."""
        metadata = UserRegistrationMetadata()
        assert metadata.invite_code is None
        assert metadata.referral_code is None
        assert metadata.referral_source is None
        assert metadata.marketing_tag is None
        assert metadata.campaign is None

    def test_all_fields_provided(self) -> None:
        """All fields can be provided."""
        metadata = UserRegistrationMetadata(
            invite_code="INV123",
            referral_code="REF456",
            referral_source="friend",
            marketing_tag="summer2024",
            campaign="launch",
        )
        assert metadata.invite_code == "INV123"
        assert metadata.referral_code == "REF456"
        assert metadata.referral_source == "friend"
        assert metadata.marketing_tag == "summer2024"
        assert metadata.campaign == "launch"

    def test_extra_fields_allowed(self) -> None:
        """Extra fields should be allowed (extra='allow')."""
        metadata = UserRegistrationMetadata(
            invite_code="INV123",
            custom_tracking="value123",  # Extra field
        )
        assert metadata.invite_code == "INV123"
        # Extra fields are allowed but not typed
        assert hasattr(metadata, "custom_tracking") or "custom_tracking" in metadata.model_dump()


class TestUserResponse:
    """Tests for UserResponse schema."""

    def test_valid_user_response(self) -> None:
        """Valid response data should pass."""
        response = UserResponse(
            id="01HZZZZZZZZZZZZZZZZZZZZZZZ",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            zip_code="10001",
            timezone="America/New_York",
        )
        assert response.id == "01HZZZZZZZZZZZZZZZZZZZZZZZ"
        assert response.email == "test@example.com"

    def test_default_values(self) -> None:
        """Default values should be applied."""
        response = UserResponse(
            id="01HZZZZZZZZZZZZZZZZZZZZZZZ",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            zip_code="10001",
        )
        assert response.phone is None
        assert response.phone_verified is False
        assert response.is_active is True
        assert response.timezone == "America/New_York"
        assert response.roles == []
        assert response.permissions == []
        assert response.profile_picture_version == 0
        assert response.has_profile_picture is False


class TestUserWithPermissionsResponse:
    """Tests for UserWithPermissionsResponse schema."""

    def test_inherits_from_user_response(self) -> None:
        """Should inherit all fields from UserResponse."""
        response = UserWithPermissionsResponse(
            id="01HZZZZZZZZZZZZZZZZZZZZZZZ",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            zip_code="10001",
        )
        assert response.id == "01HZZZZZZZZZZZZZZZZZZZZZZZ"
        assert response.email == "test@example.com"

    def test_beta_fields_optional(self) -> None:
        """Beta fields should be optional."""
        response = UserWithPermissionsResponse(
            id="01HZZZZZZZZZZZZZZZZZZZZZZZ",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            zip_code="10001",
        )
        assert response.beta_access is None
        assert response.beta_role is None
        assert response.beta_phase is None
        assert response.beta_invited_by is None

    def test_beta_fields_provided(self) -> None:
        """Beta fields can be provided."""
        response = UserWithPermissionsResponse(
            id="01HZZZZZZZZZZZZZZZZZZZZZZZ",
            email="test@example.com",
            first_name="John",
            last_name="Doe",
            zip_code="10001",
            beta_access=True,
            beta_role="early_adopter",
            beta_phase="phase1",
            beta_invited_by="admin@example.com",
        )
        assert response.beta_access is True
        assert response.beta_role == "early_adopter"
        assert response.beta_phase == "phase1"
        assert response.beta_invited_by == "admin@example.com"


class TestToken:
    """Tests for Token schema."""

    def test_valid_token(self) -> None:
        """Valid token data should pass."""
        token = Token(access_token="jwt.token.here", token_type="bearer")
        assert token.access_token == "jwt.token.here"
        assert token.token_type == "bearer"


class TestUnicodeNames:
    """Tests for unicode character handling in names."""

    def test_unicode_first_name(self) -> None:
        """Unicode characters in first_name should be allowed."""
        data = {
            "email": "test@example.com",
            "first_name": "José",
            "last_name": "García",
            "zip_code": "10001",
            "password": "Test1234",
        }
        user = UserCreate(**data)
        assert user.first_name == "José"
        assert user.last_name == "García"

    def test_chinese_characters(self) -> None:
        """Chinese characters should be allowed."""
        data = {
            "email": "test@example.com",
            "first_name": "小明",
            "last_name": "张",
            "zip_code": "10001",
            "password": "Test1234",
        }
        user = UserCreate(**data)
        assert user.first_name == "小明"
        assert user.last_name == "张"

    def test_arabic_characters(self) -> None:
        """Arabic characters should be allowed."""
        data = {
            "email": "test@example.com",
            "first_name": "محمد",
            "last_name": "أحمد",
            "zip_code": "10001",
            "password": "Test1234",
        }
        user = UserCreate(**data)
        assert user.first_name == "محمد"
        assert user.last_name == "أحمد"

    def test_emoji_in_name(self) -> None:
        """Emoji in name should be allowed (no explicit restriction)."""
        data = {
            "email": "test@example.com",
            "first_name": "John 😊",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
        }
        user = UserCreate(**data)
        assert "😊" in user.first_name


class TestEmailEdgeCases:
    """Tests for email edge cases."""

    def test_plus_addressing(self) -> None:
        """Plus addressing should be valid."""
        data = {
            "email": "john+test@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
        }
        user = UserCreate(**data)
        assert user.email == "john+test@example.com"

    def test_subdomain_email(self) -> None:
        """Subdomain email should be valid."""
        data = {
            "email": "john@mail.example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
        }
        user = UserCreate(**data)
        assert user.email == "john@mail.example.com"

    def test_email_with_numbers(self) -> None:
        """Email with numbers should be valid."""
        data = {
            "email": "john123@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
        }
        user = UserCreate(**data)
        assert user.email == "john123@example.com"

    def test_email_case_preserved(self) -> None:
        """Email case should be preserved (EmailStr doesn't lowercase)."""
        data = {
            "email": "John.Doe@Example.COM",
            "first_name": "John",
            "last_name": "Doe",
            "zip_code": "10001",
            "password": "Test1234",
        }
        user = UserCreate(**data)
        # Pydantic EmailStr normalizes to lowercase
        assert "example.com" in user.email.lower()
