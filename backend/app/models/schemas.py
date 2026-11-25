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
    soil: str | None = Field(
        default=None,
        description="sandy, loam or clay. Omitted means loam, which the advice states.",
    )
    last_irrigation_mm: float | None = Field(
        default=None,
        ge=0,
        description=(
            "How much water the last irrigation applied, in mm. Capped at the "
            "depletion it meets; the excess drains past the roots. Omit it and "
            "the irrigation is assumed to refill the profile."
        ),
    )
    usual_interval_days: int | None = Field(
        default=None,
        ge=1,
        description=(
            "How often the farmer usually irrigates, in days. Used for the "
            "comparison line and as the 'every N days' of the savings habit; "
            "never in the core water balance."
        ),
    )
    habit_mm_per_irrigation: float | None = Field(
        default=None,
        ge=0,
        description=(
            "How much water the farmer applies at each irrigation, in mm. With "
            "usual_interval_days this enables the savings estimate. Omit it and "
            "no savings are computed at all."
        ),
    )
    pump_litres_per_hour: float | None = Field(
        default=None,
        gt=0,
        description="Pump discharge, litres per hour. Needed for hours and rupees.",
    )
    cost_per_pump_hour: float | None = Field(
        default=None,
        ge=0,
        description="Running cost of the pump, rupees per hour. Needed for rupees.",
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


class SavingsOut(BaseModel):
    """A comparison of the farmer's habit against the advised schedule.

    Every field here is an estimate over the same real weather, and the UI
    labels it as one. `money_saved` is null unless both pump figures were
    supplied; `money_unavailable_reason` then says why in words.
    """

    window_start: str
    window_end: str
    habit_interval_days: int
    habit_mm_per_irrigation: float
    habit_total_mm: float
    habit_irrigations: int
    advised_total_mm: float
    advised_irrigations: int
    saved_mm: float
    saved_litres_per_acre: int
    pump_hours_saved: float | None = None
    money_saved: float | None = None
    money_unavailable_reason: str | None = None
    assumptions: list[str]


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
    last_irrigation_mm: float | None = None
    last_irrigation_effective_mm: float = 0.0

    soil: str
    soil_name_hi: str
    soil_name_en: str
    soil_available_water_mm_per_m: float
    soil_is_default: bool

    # The next date the deficit is expected to reach the stress point, or null
    # when it does not within the forecast. Never extrapolated past the window.
    next_irrigation_date: str | None = None
    next_irrigation_mm: float = 0.0
    next_irrigation_within_forecast: bool = False
    forecast_covered_until: str | None = None

    # The farmer's usual gap between waterings, echoed back so the UI can render
    # the comparison line. Purely presentational.
    usual_interval_days: int | None = None

    assumptions: list[str]
    sources: list[str]
    generated_at: str

    # Null when the farmer has not stated a habit to compare against. The UI
    # then shows a prompt asking for it rather than a savings figure invented
    # against an imaginary baseline.
    savings: SavingsOut | None = None
