from app.services.geocoding.google_provider import GoogleMapsProvider


def test_google_feature_normalization_extracts_structured_fields():
    provider = GoogleMapsProvider()

    result = {
        "place_id": "ChIJmYQ0QwBZwokR42ZoW1RjP5M",
        "formatted_address": "1600 Amphitheatre Parkway, Mountain View, CA 94043, USA",
        "geometry": {
            "location": {"lat": 37.4220656, "lng": -122.0840897},
        },
        "address_components": [
            {"long_name": "1600", "short_name": "1600", "types": ["street_number"]},
            {"long_name": "Amphitheatre Parkway", "short_name": "Amphitheatre Pkwy", "types": ["route"]},
            {"long_name": "Mountain View", "short_name": "Mountain View", "types": ["locality", "political"]},
            {
                "long_name": "Santa Clara County",
                "short_name": "Santa Clara County",
                "types": ["administrative_area_level_2", "political"],
            },
            {
                "long_name": "California",
                "short_name": "CA",
                "types": ["administrative_area_level_1", "political"],
            },
            {"long_name": "United States", "short_name": "US", "types": ["country", "political"]},
            {"long_name": "94043", "short_name": "94043", "types": ["postal_code"]},
        ],
    }

    parsed = provider._parse_result(result)

    assert parsed.street_number == "1600"
    assert parsed.street_name == "Amphitheatre Parkway"
    assert parsed.city == "Mountain View"
    assert parsed.state == "CA"
    assert parsed.postal_code == "94043"
    assert parsed.formatted_address == result["formatted_address"]
    assert parsed.provider_id == "google:ChIJmYQ0QwBZwokR42ZoW1RjP5M"


def test_google_feature_uses_short_code_state():
    provider = GoogleMapsProvider()

    result = {
        "place_id": "ChIJd8BlQ2BZwokRAFUEcm_qrcA",
        "formatted_address": "320 East 46th Street, New York, NY 10017, USA",
        "geometry": {
            "location": {"lat": 40.752726, "lng": -73.972771},
        },
        "address_components": [
            {"long_name": "320", "short_name": "320", "types": ["street_number"]},
            {"long_name": "East 46th Street", "short_name": "E 46th St", "types": ["route"]},
            {"long_name": "New York", "short_name": "New York", "types": ["locality", "political"]},
            {
                "long_name": "New York County",
                "short_name": "New York County",
                "types": ["administrative_area_level_2", "political"],
            },
            {
                "long_name": "New York",
                "short_name": "NY",
                "types": ["administrative_area_level_1", "political"],
            },
            {"long_name": "United States", "short_name": "US", "types": ["country", "political"]},
            {"long_name": "10017", "short_name": "10017", "types": ["postal_code"]},
        ],
    }

    parsed = provider._parse_result(result)

    assert parsed.street_number == "320"
    assert parsed.street_name == "East 46th Street"
    assert parsed.city == "New York"
    assert parsed.state == "NY"
    assert parsed.postal_code == "10017"
