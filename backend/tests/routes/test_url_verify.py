# backend/tests/routes/test_url_verify.py
"""
Quick test to verify the correct URL pattern for public routes.
"""


def test_verify_public_url_pattern(client, test_instructor):
    """Test both URL patterns to see which one works."""

    # Try with /api/v1/public
    response1 = client.get(f"/api/v1/public/instructors/{test_instructor.id}/availability?start_date=2025-07-15")
    print(f"\n/api/v1/public pattern - Status: {response1.status_code}")

    # Try with just /public
    response2 = client.get(f"/public/instructors/{test_instructor.id}/availability?start_date=2025-07-15")
    print(f"/public pattern - Status: {response2.status_code}")

    # One of these should work
    assert response1.status_code in [200, 400] or response2.status_code in [200, 400], "Neither URL pattern works!"

    if response1.status_code in [200, 400]:
        print("✅ Use /api/v1/public prefix")
    if response2.status_code in [200, 400]:
        print("✅ Use /public prefix")
