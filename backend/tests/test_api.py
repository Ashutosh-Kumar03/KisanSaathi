"""Smoke tests for the API surface.

These hit the real app object, so a broken route or a schema that no longer
matches the response is caught here rather than in the browser. They do not
assert on forecast values, because those come from the live weather service and
change; they assert on shape and on the error contract, which is ours to keep.

The one expected to reach the network is the search endpoint. If the upstream
service is unreachable the test is skipped rather than failed: an offline laptop
should not look like a broken app.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_configured_integrations():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # With no environment variables both must degrade, never fail.
    assert body["store"] == "memory"
    assert body["narration"] == "template"


def test_location_search_rejects_a_one_character_query():
    assert client.get("/api/locations/search", params={"q": "P"}).status_code == 422


def test_weather_rejects_out_of_range_coordinates():
    response = client.get("/api/weather", params={"lat": 200, "lon": 85})
    assert response.status_code == 422


def test_location_search_returns_real_indian_places():
    try:
        response = client.get("/api/locations/search", params={"q": "Patna"})
    except Exception as exc:  # noqa: BLE001 - upstream unavailable
        pytest.skip(f"weather service unreachable: {exc}")
    if response.status_code == 502:
        pytest.skip("weather service unreachable")
    assert response.status_code == 200
    results = response.json()["results"]
    assert results, "expected at least one Patna"
    first = results[0]
    assert first["display_name"]
    # Coordinates must be inside India, not a same-named town elsewhere.
    assert 6.0 <= first["latitude"] <= 38.0
    assert 68.0 <= first["longitude"] <= 98.0


def test_advice_requires_a_supported_crop():
    response = client.post(
        "/api/advice",
        json={
            "crop": "maize",
            "sowing_date": str(date.today() - timedelta(days=30)),
            "latitude": 25.594,
            "longitude": 85.136,
            "location_name": "Patna",
        },
    )
    assert response.status_code == 422


def test_advice_rejects_a_future_sowing_date():
    response = client.post(
        "/api/advice",
        json={
            "crop": "wheat",
            "sowing_date": str(date.today() + timedelta(days=5)),
            "latitude": 25.594,
            "longitude": 85.136,
            "location_name": "Patna",
        },
    )
    assert response.status_code == 422


def test_advice_returns_a_real_decision():
    try:
        response = client.post(
            "/api/advice",
            json={
                "crop": "wheat",
                "sowing_date": str(date.today() - timedelta(days=35)),
                "latitude": 25.594,
                "longitude": 85.136,
                "location_name": "Patna, Bihar",
            },
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"weather service unreachable: {exc}")
    if response.status_code == 502:
        pytest.skip("weather service unreachable")

    assert response.status_code == 200
    body = response.json()
    assert body["action"] in {
        "IRRIGATE_TODAY",
        "WAIT_RAIN",
        "SOIL_MOISTURE_OK",
        "SEASON_OVER",
    }
    assert body["hindi"] and body["english"]
    assert body["sources"], "advice must carry its citations"
    if body["action"] == "IRRIGATE_TODAY":
        assert body["litres_per_acre"] > 0
        assert body["gross_mm"] >= body["net_mm"]
