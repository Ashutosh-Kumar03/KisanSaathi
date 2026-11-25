"""Pydantic contracts shared by the API, the engine and the frontend.

These models are the single description of the JSON the UI consumes, so a
rename here is a visible API change rather than a silent one.
"""

from datetime import date

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


# --- advice ---------------------------------------------------------------


class AdviceRequest(BaseModel):
    """What the single screen sends when the farmer asks for advice."""

    crop: str = Field(description="wheat or rice")
    sowing_date: date
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    location_name: str = Field(
        default="", description="Display name of the chosen village, echoed back"
    )
    last_irrigation_date: date | None = Field(
        default=None,
        description=(
            "When the farmer last irrigated, if they know. Depletion restarts from "
            "zero on that date. Omit it and the advice assumes no irrigation since "
            "sowing, which it then says out loud."
        ),
    )


class AdvisoryWindow(BaseModel):
    """Whether a spray or a urea dose should go ahead, and the reason why."""

    verdict: str = Field(description="go, wait, or unknown")
    reason_hi: str
    reason_en: str


class ForecastDayOut(BaseModel):
    """One day of the forecast as the UI shows it."""

    date: str
    et0_mm: float
    rain_mm: float
    rain_probability_pct: int | None = None
    t_max_c: float
    t_min_c: float
    wind_max_kmh: float | None = None


class DayTraceOut(BaseModel):
    """One row of the water balance, so the advice can be shown its own working."""

    date: str
    age_days: int
    stage: str
    kc: float
    et0_mm: float
    etc_mm: float
    rain_mm: float
    effective_rain_mm: float
    depletion_mm: float


class AdviceResponse(BaseModel):
    """The whole result for the single screen: decision, sentences, citations."""

    action: str = Field(
        description="IRRIGATE_TODAY, WAIT_RAIN, SOIL_MOISTURE_OK or SEASON_OVER"
    )
    headline_hi: str
    headline_en: str
    hindi: str
    english: str

    crop: str
    crop_name_hi: str
    crop_name_en: str
    location_name: str
    today: str
    age_days: int
    stage: str
    in_critical_window: bool
    critical_window_label: str | None = None

    net_mm: float
    gross_mm: float
    litres_per_acre: int
    depletion_mm: float
    taw_mm: float
    raw_mm: float
    rain_next_24h_mm: float

    spray: AdvisoryWindow
    urea: AdvisoryWindow
    forecast: list[ForecastDayOut]
    trace: list[DayTraceOut]

    # Null means the farmer did not say, and the advice therefore assumes no
    # irrigation since sowing. The UI states that assumption rather than
    # leaving it implicit.
    last_irrigation_date: str | None = None

    assumptions: list[str]
    sources: list[str]
    generated_at: str
