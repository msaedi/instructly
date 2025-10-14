from app.services.geocoding.mapbox_provider import MapboxProvider


def test_mapbox_feature_normalization_extracts_structured_fields():
    provider = MapboxProvider()

    feature = {
        "id": "address.1234567890",
        "center": [-73.973232, 40.752726],
        "place_name": "320 East 46th Street, New York, New York 10017, United States",
        "text": "East 46th Street",
        "properties": {
            "address": "320",
            "street": "East 46th Street",
        },
        "context": [
            {"id": "neighborhood.midtown", "text": "Midtown"},
            {"id": "locality.12345", "text": "New York"},
            {"id": "place.12345", "text": "New York"},
            {"id": "region.12345", "short_code": "US-NY", "text": "New York"},
            {"id": "postcode.12345", "text": "10017"},
            {"id": "country.12345", "short_code": "us", "text": "United States"},
        ],
        "relevance": 1,
    }

    parsed = provider._parse_feature(feature)

    assert parsed.street_number == "320"
    assert parsed.street_name == "East 46th Street"
    assert parsed.city == "New York"
    assert parsed.state == "NY"
    assert parsed.postal_code == "10017"
    assert parsed.formatted_address == feature["place_name"]
    assert parsed.provider_id == "mapbox:address.1234567890"
