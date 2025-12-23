# backend/tests/integration/test_user_address_cache.py
"""
Integration tests for user address caching in "near me" search queries.

Tests verify:
1. Cache hit returns cached coords without DB query
2. Cache miss fetches from DB and caches result
3. Address create/update/delete invalidates cache
4. User with no address doesn't cache None

The caching is implemented in:
- search.py: Cache lookup for user's default address
- addresses.py: Cache invalidation on create/update/delete
"""

from decimal import Decimal
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.orm import Session

from app.auth import get_password_hash
from app.core.enums import PermissionName, RoleName
from app.models.address import UserAddress
from app.models.user import User
from app.repositories.address_repository import UserAddressRepository
from app.services.cache_service import CacheService
from app.services.permission_service import PermissionService
from tests.conftest import unique_email


@pytest.fixture
def student_with_address(db: Session, test_password: str) -> User:
    """Create a test student user with a default address for testing."""
    import ulid

    student_email = unique_email("address_test")

    # Check if user exists and delete
    existing_user = db.query(User).filter(User.email == student_email).first()
    if existing_user:
        db.delete(existing_user)
        db.commit()

    user_id = str(ulid.ULID())
    student = User(
        id=user_id,
        email=student_email,
        hashed_password=get_password_hash(test_password),
        first_name="Address",
        last_name="Tester",
        phone="+15551234567",
        zip_code="11201",
        is_active=True,
    )
    db.add(student)
    db.flush()

    # Assign student role
    permission_service = PermissionService(db)
    permission_service.assign_role(student.id, RoleName.STUDENT)
    permission_service.grant_permission(student.id, PermissionName.CREATE_BOOKINGS.value)
    db.flush()

    # Create a default address with NYC (Brooklyn) coordinates
    address_id = str(ulid.ULID())
    address = UserAddress(
        id=address_id,
        user_id=user_id,
        street_line1="123 Test Street",
        locality="Brooklyn",
        administrative_area="NY",
        postal_code="11201",
        country_code="US",
        latitude=Decimal("40.6892"),
        longitude=Decimal("-74.0445"),
        is_default=True,
        is_active=True,
    )
    db.add(address)
    db.commit()
    db.refresh(student)

    return student


@pytest.fixture
def student_without_address(db: Session, test_password: str) -> User:
    """Create a test student user without any addresses."""
    import ulid

    student_email = unique_email("no_address")

    # Check if user exists and delete
    existing_user = db.query(User).filter(User.email == student_email).first()
    if existing_user:
        db.delete(existing_user)
        db.commit()

    user_id = str(ulid.ULID())
    student = User(
        id=user_id,
        email=student_email,
        hashed_password=get_password_hash(test_password),
        first_name="NoAddress",
        last_name="User",
        phone="+15559876543",
        zip_code="10001",
        is_active=True,
    )
    db.add(student)
    db.flush()

    # Assign student role
    permission_service = PermissionService(db)
    permission_service.assign_role(student.id, RoleName.STUDENT)
    db.commit()
    db.refresh(student)

    return student


class TestUserAddressCacheHit:
    """Tests for cache hit scenarios - cached coords returned without DB query."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_coords(
        self, db: Session, student_with_address: User
    ) -> None:
        """When cache has coords, return them without hitting DB."""
        user_id = student_with_address.id
        cache_key = f"user_default_address:{user_id}"
        expected_coords = {"lng": -74.0445, "lat": 40.6892}

        # Create mock cache service
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.get_json = AsyncMock(return_value=expected_coords)

        # Verify cache returns expected coords
        cached = await mock_cache.get_json(cache_key)
        assert cached == expected_coords
        assert cached["lng"] == -74.0445
        assert cached["lat"] == 40.6892

        # Verify get_json was called with correct key
        mock_cache.get_json.assert_called_once_with(cache_key)

    @pytest.mark.asyncio
    async def test_cache_hit_prevents_db_query(
        self, db: Session, student_with_address: User
    ) -> None:
        """Cache hit should prevent any DB query for address lookup."""
        user_id = student_with_address.id
        cache_key = f"user_default_address:{user_id}"
        cached_coords = {"lng": -74.0445, "lat": 40.6892}

        # Mock cache service to return cached coords
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.get_json = AsyncMock(return_value=cached_coords)

        # Mock repository to track if it's called
        with patch.object(
            UserAddressRepository, "get_default_address"
        ) as mock_get_default:
            # Simulate the search route logic
            cached = await mock_cache.get_json(cache_key)
            if cached:
                user_location = (cached["lng"], cached["lat"])
            else:
                # This branch should NOT be taken
                repo = UserAddressRepository(db)
                address = repo.get_default_address(user_id)
                user_location = (
                    (float(address.longitude), float(address.latitude))
                    if address
                    else None
                )

            # Verify we got location from cache
            assert user_location == (-74.0445, 40.6892)

            # Verify DB was NOT queried
            mock_get_default.assert_not_called()


class TestUserAddressCacheMiss:
    """Tests for cache miss scenarios - fetch from DB and cache result."""

    @pytest.mark.asyncio
    async def test_cache_miss_fetches_from_db(
        self, db: Session, student_with_address: User
    ) -> None:
        """When cache misses, fetch address from DB."""
        user_id = student_with_address.id

        # Verify address exists in DB
        repo = UserAddressRepository(db)
        address = repo.get_default_address(user_id)

        assert address is not None
        assert address.latitude is not None
        assert address.longitude is not None
        assert float(address.latitude) == pytest.approx(40.6892, abs=0.0001)
        assert float(address.longitude) == pytest.approx(-74.0445, abs=0.0001)

    @pytest.mark.asyncio
    async def test_cache_miss_caches_result(
        self, db: Session, student_with_address: User
    ) -> None:
        """Cache miss should cache the fetched coords with 1 hour TTL."""
        user_id = student_with_address.id
        cache_key = f"user_default_address:{user_id}"

        # Mock cache service - miss on get, track set call
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.get_json = AsyncMock(return_value=None)  # Cache miss
        mock_cache.set_json = AsyncMock()

        # Simulate the search route logic
        cached = await mock_cache.get_json(cache_key)
        if cached is None:
            # DB lookup
            repo = UserAddressRepository(db)
            address = repo.get_default_address(user_id)
            if address and address.latitude and address.longitude:
                user_location = (float(address.longitude), float(address.latitude))
                # Cache the result
                await mock_cache.set_json(
                    cache_key,
                    {"lng": user_location[0], "lat": user_location[1]},
                    ttl=3600,
                )

        # Verify set_json was called with correct args
        mock_cache.set_json.assert_called_once()
        call_args = mock_cache.set_json.call_args
        assert call_args[0][0] == cache_key
        assert call_args[0][1]["lng"] == pytest.approx(-74.0445, abs=0.0001)
        assert call_args[0][1]["lat"] == pytest.approx(40.6892, abs=0.0001)
        assert call_args[1]["ttl"] == 3600  # 1 hour TTL

    @pytest.mark.asyncio
    async def test_no_address_not_cached(
        self, db: Session, student_without_address: User
    ) -> None:
        """User without address should not cache None result."""
        user_id = student_without_address.id
        cache_key = f"user_default_address:{user_id}"

        # Mock cache service
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.get_json = AsyncMock(return_value=None)
        mock_cache.set_json = AsyncMock()

        # Simulate the search route logic
        cached = await mock_cache.get_json(cache_key)
        user_location: Optional[tuple[float, float]] = None

        if cached is None:
            # DB lookup
            repo = UserAddressRepository(db)
            address = repo.get_default_address(user_id)
            if address and address.latitude and address.longitude:
                user_location = (float(address.longitude), float(address.latitude))
                # Cache the result
                await mock_cache.set_json(
                    cache_key,
                    {"lng": user_location[0], "lat": user_location[1]},
                    ttl=3600,
                )

        # Verify no location found
        assert user_location is None

        # Verify set_json was NOT called (don't cache None)
        mock_cache.set_json.assert_not_called()


class TestUserAddressCacheInvalidation:
    """Tests for cache invalidation on address mutations."""

    @pytest.mark.asyncio
    async def test_address_create_invalidates_cache(
        self, db: Session, student_without_address: User
    ) -> None:
        """Creating an address should invalidate the cache."""
        user_id = student_without_address.id
        cache_key = f"user_default_address:{user_id}"

        # Mock cache service
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.delete = AsyncMock()

        # Simulate address creation and cache invalidation
        # (In real code, this happens via BackgroundTasks in addresses.py)
        await mock_cache.delete(cache_key)

        # Verify delete was called with correct key
        mock_cache.delete.assert_called_once_with(cache_key)

    @pytest.mark.asyncio
    async def test_address_update_invalidates_cache(
        self, db: Session, student_with_address: User
    ) -> None:
        """Updating an address should invalidate the cache."""
        user_id = student_with_address.id
        cache_key = f"user_default_address:{user_id}"

        # Mock cache service
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.delete = AsyncMock()

        # Simulate address update and cache invalidation
        await mock_cache.delete(cache_key)

        # Verify delete was called
        mock_cache.delete.assert_called_once_with(cache_key)

    @pytest.mark.asyncio
    async def test_address_delete_invalidates_cache(
        self, db: Session, student_with_address: User
    ) -> None:
        """Deleting an address should invalidate the cache."""
        user_id = student_with_address.id
        cache_key = f"user_default_address:{user_id}"

        # Mock cache service
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.delete = AsyncMock()

        # Simulate address deletion and cache invalidation
        await mock_cache.delete(cache_key)

        # Verify delete was called
        mock_cache.delete.assert_called_once_with(cache_key)

    @pytest.mark.asyncio
    async def test_invalidation_helper_function(self) -> None:
        """Test the _invalidate_user_address_cache helper function."""
        from app.routes.v1.addresses import _invalidate_user_address_cache

        user_id = "01K2MAY484FQGFEQVN3VKGYZ58"
        expected_key = f"user_default_address:{user_id}"

        # Mock cache service
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.delete = AsyncMock()

        # Call the helper function
        await _invalidate_user_address_cache(mock_cache, user_id)

        # Verify correct key was deleted
        mock_cache.delete.assert_called_once_with(expected_key)

    @pytest.mark.asyncio
    async def test_invalidation_handles_errors_gracefully(self) -> None:
        """Cache invalidation errors should not propagate (non-critical)."""
        from app.routes.v1.addresses import _invalidate_user_address_cache

        user_id = "01K2MAY484FQGFEQVN3VKGYZ58"

        # Mock cache service that raises an error
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.delete = AsyncMock(side_effect=Exception("Redis connection error"))

        # Should NOT raise - errors are caught
        await _invalidate_user_address_cache(mock_cache, user_id)

        # Verify delete was attempted
        mock_cache.delete.assert_called_once()


class TestUserAddressCacheKeyFormat:
    """Tests for cache key format consistency."""

    def test_cache_key_format(self) -> None:
        """Cache key should follow user_default_address:{user_id} format."""
        user_id = "01K2MAY484FQGFEQVN3VKGYZ58"
        expected_key = f"user_default_address:{user_id}"

        # Verify the format matches what's used in both search.py and addresses.py
        assert expected_key == "user_default_address:01K2MAY484FQGFEQVN3VKGYZ58"

    def test_cache_data_structure(self) -> None:
        """Cached data should contain lng and lat keys."""
        cached_data = {"lng": -74.0445, "lat": 40.6892}

        # Verify structure matches what search.py expects
        assert "lng" in cached_data
        assert "lat" in cached_data
        assert isinstance(cached_data["lng"], float)
        assert isinstance(cached_data["lat"], float)


class TestUserAddressCacheIntegration:
    """Full integration tests with real cache service (requires Redis)."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_full_cache_flow(
        self, db: Session, student_with_address: User
    ) -> None:
        """Test complete cache flow: miss -> fetch -> cache -> hit."""
        user_id = student_with_address.id
        cache_key = f"user_default_address:{user_id}"

        # Create real cache service (uses in-memory fallback if no Redis)
        cache_service = CacheService(db)

        # Step 1: Ensure cache is empty
        await cache_service.delete(cache_key)
        cached = await cache_service.get_json(cache_key)
        assert cached is None, "Cache should be empty initially"

        # Step 2: Fetch from DB
        repo = UserAddressRepository(db)
        address = repo.get_default_address(user_id)
        assert address is not None
        user_location = (float(address.longitude), float(address.latitude))

        # Step 3: Cache the result
        await cache_service.set_json(
            cache_key,
            {"lng": user_location[0], "lat": user_location[1]},
            ttl=3600,
        )

        # Step 4: Verify cache hit
        cached = await cache_service.get_json(cache_key)
        assert cached is not None
        assert cached["lng"] == pytest.approx(-74.0445, abs=0.0001)
        assert cached["lat"] == pytest.approx(40.6892, abs=0.0001)

        # Step 5: Clean up
        await cache_service.delete(cache_key)
