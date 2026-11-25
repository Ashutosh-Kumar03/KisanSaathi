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


def test_advice_rejects_a_future_last_irrigation_date():
    today = date.today()
    response = client.post(
        "/api/advice",
        json={
            "crop": "wheat",
            "sowing_date": str(today - timedelta(days=30)),
            "last_irrigation_date": str(today + timedelta(days=1)),
            "latitude": 25.594,
            "longitude": 85.136,
        },
    )
    assert response.status_code == 422


def test_advice_rejects_an_irrigation_date_before_sowing():
    today = date.today()
    response = client.post(
        "/api/advice",
        json={
            "crop": "wheat",
            "sowing_date": str(today - timedelta(days=30)),
            "last_irrigation_date": str(today - timedelta(days=40)),
            "latitude": 25.594,
            "longitude": 85.136,
        },
    )
    assert response.status_code == 422


def test_advice_without_a_habit_returns_no_savings():
    """No baseline, no figure: the UI is forced to prompt for the habit."""
    response = client.post(
        "/api/advice",
        json={
            "crop": "wheat",
            "sowing_date": str(date.today() - timedelta(days=60)),
            "latitude": 25.594,
            "longitude": 85.136,
        },
    )
    if response.status_code == 502:
        pytest.skip("weather service unreachable")
    assert response.status_code == 200
    assert response.json()["savings"] is None


def test_advice_with_a_habit_returns_real_savings():
    response = client.post(
        "/api/advice",
        json={
            "crop": "wheat",
            "sowing_date": str(date.today() - timedelta(days=60)),
            "latitude": 25.594,
            "longitude": 85.136,
            "usual_interval_days": 7,
            "habit_mm_per_irrigation": 60,
            "pump_litres_per_hour": 30000,
            "cost_per_pump_hour": 120,
        },
    )
    if response.status_code == 502:
        pytest.skip("weather service unreachable")
    assert response.status_code == 200
    savings = response.json()["savings"]
    assert savings is not None
    assert savings["habit_interval_days"] == 7
    assert savings["habit_total_mm"] > 0
    assert savings["assumptions"], "every estimate must list what it rests on"
    # The difference must equal the two schedules' totals.
    assert savings["saved_mm"] == pytest.approx(
        savings["habit_total_mm"] - savings["advised_total_mm"], abs=0.2
    )
    # Rupees only because both pump inputs were given.
    assert savings["money_saved"] is not None
    assert savings["pump_hours_saved"] is not None


def test_advice_with_pump_hours_but_no_cost_omits_rupees():
    response = client.post(
        "/api/advice",
        json={
            "crop": "wheat",
            "sowing_date": str(date.today() - timedelta(days=60)),
            "latitude": 25.594,
            "longitude": 85.136,
            "usual_interval_days": 7,
            "habit_mm_per_irrigation": 60,
            "pump_litres_per_hour": 30000,
        },
    )
    if response.status_code == 502:
        pytest.skip("weather service unreachable")
    assert response.status_code == 200
    savings = response.json()["savings"]
    assert savings["money_saved"] is None
    assert savings["money_unavailable_reason"] == "both"


def test_advice_rejects_an_unknown_soil():
    today = date.today()
    response = client.post(
        "/api/advice",
        json={
            "crop": "wheat",
            "sowing_date": str(today - timedelta(days=30)),
            "soil": "peat",
            "latitude": 25.594,
            "longitude": 85.136,
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
    # No last-irrigation date was sent, so the response must say it assumed
    # none rather than leaving the assumption implicit.
    assert body["last_irrigation_date"] is None
    assert any("सिंचाई नहीं हुई" in line for line in body["assumptions"])
    # No soil was sent either, so the response must name the loam fallback and
    # flag it as assumed rather than silently presenting it as the farmer's.
    assert body["soil"] == "loam"
    assert body["soil_is_default"] is True
    assert body["soil_available_water_mm_per_m"] > 0
    assert any("नहीं चुना गया" in line for line in body["assumptions"])
    if body["action"] == "IRRIGATE_TODAY":
        assert body["litres_per_acre"] > 0
        assert body["gross_mm"] >= body["net_mm"]
