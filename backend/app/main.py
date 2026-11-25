"""KisanSaathi backend.

The irrigation recommendation is computed by deterministic code
(services/irrigation.py). Nothing in the language-model path is allowed to
change the recommendation -- narration only explains a number that already
exists.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models.schemas import LocationSearchResponse, WeatherForecast
from .services import openmeteo

app = FastAPI(
    title="KisanSaathi API",
    description="Weather-to-irrigation advisory for Indian farmers.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    """Liveness plus which optional integrations are actually configured.

    Surfacing this lets the frontend (and a demo debugger) see at a glance
    whether it is running on the in-memory store and template narration.
    """
    return {
        "status": "ok",
        "store": "supabase" if settings.supabase_enabled else "memory",
        "narration": "llm" if settings.llm_enabled else "template",
    }


@app.get("/api/locations/search", response_model=LocationSearchResponse)
async def search_locations(
    q: str = Query(min_length=2, description="Town or district name"),
    limit: int = Query(6, ge=1, le=20),
) -> LocationSearchResponse:
    """Search Indian locations by name.

    Upstream failures are surfaced as 502 rather than an empty list, so the UI
    can tell 'no such village' apart from 'weather service is down'.
    """
    try:
        results = await openmeteo.search_locations(q, limit)
    except Exception as exc:  # noqa: BLE001 - any upstream/parse failure is a 502 here
        raise HTTPException(
            status_code=502, detail=f"Location lookup failed: {exc}"
        ) from exc
    return LocationSearchResponse(results=results)


@app.get("/api/weather", response_model=WeatherForecast)
async def get_weather(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
    days: int = Query(7, ge=1, le=16),
) -> WeatherForecast:
    """Daily ET0/rain/temperature forecast for a point."""
    try:
        return await openmeteo.get_forecast(lat, lon, days)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Weather lookup failed: {exc}") from exc
