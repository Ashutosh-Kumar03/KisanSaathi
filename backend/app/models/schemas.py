"""Pydantic contracts shared by the API, the engine and the frontend.

These models are the single description of the JSON the UI consumes, so a
rename here is a visible API change rather than a silent one.
"""

from pydantic import BaseModel, Field


class Location(BaseModel):
    """A geocoding result, already restricted to India."""

    id: int
    name: str
    admin1: str | None = None  # state
    admin2: str | None = None  # district
    latitude: float
    longitude: float
    timezone: str | None = None
    display_name: str  # human-readable, built server-side so both clients agree


class DayWeather(BaseModel):
    """One forecast day, in the units the engine needs."""

    date: str
    et0_mm: float = Field(description="Reference evapotranspiration, mm")
    rain_mm: float = Field(description="Precipitation total, mm")
    rain_probability_pct: int | None = None
    t_max_c: float
    t_min_c: float
    # Wind and humidity drive the spray-window rule. None means Open-Meteo
    # omitted the field; the engine then says it cannot judge spraying rather
    # than guessing "safe to spray".
    wind_max_kmh: float | None = None
    wind_gust_kmh: float | None = None
    humidity_mean_pct: int | None = None
    et0_source: str = Field(
        default="open-meteo",
        description="open-meteo, or hargreaves when the API omitted ET0",
    )


class WeatherForecast(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    days: list[DayWeather]


class LocationSearchResponse(BaseModel):
    results: list[Location]
