"""Minimal test to verify database safety mechanism."""


def test_database_safety_works(db):
    """If this runs, we're using test database. If it fails early, safety worked."""
    # The db fixture will trigger safety checks
    assert db is not None
    print(f"Successfully using test database")
