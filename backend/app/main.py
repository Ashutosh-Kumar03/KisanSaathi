"""KisanSaathi backend.

The irrigation recommendation is computed by deterministic code
(services/irrigation.py). Nothing in the language-model path is allowed to
change the recommendation -- narration only explains a number that already
exists.
"""

from datetime import date, datetime, timezone

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .data import crop_rules
from .models.schemas import (
    AdviceRequest,
    AdviceResponse,
    AdvisoryWindow,
    DayTraceOut,
    ForecastDayOut,
    LocationSearchResponse,
    SavingsOut,
    WeatherForecast,
)
from .services import irrigation, narration, openmeteo

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


@app.post("/api/advice", response_model=AdviceResponse)
async def post_advice(request: AdviceRequest) -> AdviceResponse:
    """The one decision the whole app exists to deliver.

    Order matters here. The crop rules and the sowing date are validated first,
    so a typo in the crop name is a 422 and never a wasted forecast call. The
    weather is fetched with enough past days to cover the season so far, the
    deterministic engine decides, and only then is the decision narrated. If
    the weather service fails this is a 502 -- never an empty or invented
    advice, because "no answer" and "no need to irrigate" must never look the
    same to a farmer deciding whether to run a pump.
    """
    crop = crop_rules.get_crop(request.crop)
    if crop is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported crop '{request.crop}'. Supported: wheat, rice.",
        )

    today = date.today()
    if request.sowing_date > today:
        raise HTTPException(
            status_code=422, detail="Sowing date cannot be in the future."
        )

    if request.soil is not None and crop_rules.get_soil(request.soil).key != request.soil.strip().lower():
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported soil '{request.soil}'. Supported: sandy, loam, clay.",
        )

    if request.last_irrigation_mm is not None and request.last_irrigation_date is None:
        raise HTTPException(
            status_code=422,
            detail="A last irrigation amount needs a last irrigation date.",
        )

    if request.last_irrigation_date is not None:
        # Validate before spending a forecast call, and reject a date the
        # engine would have to silently ignore.
        if request.last_irrigation_date > today:
            raise HTTPException(
                status_code=422,
                detail="Last irrigation date cannot be in the future.",
            )
        if request.last_irrigation_date < request.sowing_date:
            raise HTTPException(
                status_code=422,
                detail="Last irrigation date cannot be before the sowing date.",
            )

    age_days = (today - request.sowing_date).days
    # Cover the season so far, bounded by what the upstream API will give.
    past_days = min(age_days, 92)

    try:
        forecast = await openmeteo.get_forecast(
            request.latitude, request.longitude, days=8, past_days=past_days
        )
    except Exception as exc:  # noqa: BLE001 - any upstream failure is a 502 here
        raise HTTPException(
            status_code=502, detail=f"Weather lookup failed: {exc}"
        ) from exc

    engine_days = [
        irrigation.EngineDay(
            date=date.fromisoformat(day.date),
            et0_mm=day.et0_mm,
            rain_mm=day.rain_mm,
            wind_max_kmh=day.wind_max_kmh,
            rain_probability_pct=day.rain_probability_pct,
        )
        for day in forecast.days
    ]

    try:
        advice = irrigation.advise(
            crop,
            request.sowing_date,
            today,
            engine_days,
            last_irrigation_date=request.last_irrigation_date,
            last_irrigation_mm=request.last_irrigation_mm,
            usual_interval_days=request.usual_interval_days,
            soil=crop_rules.get_soil(request.soil) if request.soil else None,
        )
    except irrigation.EngineInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    hindi, english = narration.narrate(advice)
    headline_hi, headline_en = narration.headline(advice)

    # Savings are computed from the same real weather the advice used, and only
    # when the farmer has stated a habit. Without one this stays None and the UI
    # asks for it: a savings figure against an imagined baseline would be the
    # most misleading number the app could print.
    try:
        savings = irrigation.simulate_savings(
            crop,
            request.sowing_date,
            engine_days,
            soil=crop_rules.get_soil(request.soil) if request.soil else None,
            habit_interval_days=request.usual_interval_days,
            habit_mm_per_irrigation=request.habit_mm_per_irrigation,
            pump_litres_per_hour=request.pump_litres_per_hour,
            cost_per_pump_hour=request.cost_per_pump_hour,
        )
    except irrigation.EngineInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Only days from today onward are shown as "the forecast"; the days behind
    # today are working, not weather to plan around.
    today_iso = today.isoformat()
    upcoming = [day for day in forecast.days if day.date >= today_iso]

    return AdviceResponse(
        action=advice.action,
        headline_hi=headline_hi,
        headline_en=headline_en,
        hindi=hindi,
        english=english,
        crop=advice.crop_key,
        crop_name_hi=advice.crop_name_hi,
        crop_name_en=advice.crop_name_en,
        location_name=request.location_name,
        today=today_iso,
        age_days=advice.age_days,
        stage=advice.stage,
        in_critical_window=advice.in_critical_window,
        critical_window_label=advice.critical_window_label,
        net_mm=advice.net_mm,
        gross_mm=advice.gross_mm,
        litres_per_acre=advice.litres_per_acre,
        depletion_mm=advice.depletion_mm,
        taw_mm=advice.taw_mm,
        raw_mm=advice.raw_mm,
        rain_next_24h_mm=advice.rain_next_24h_mm,
        spray=AdvisoryWindow(
            verdict=advice.spray.verdict,
            reason_hi=advice.spray.reason_hi,
            reason_en=advice.spray.reason_en,
        ),
        urea=AdvisoryWindow(
            verdict=advice.urea.verdict,
            reason_hi=advice.urea.reason_hi,
            reason_en=advice.urea.reason_en,
        ),
        forecast=[
            ForecastDayOut(
                date=day.date,
                et0_mm=day.et0_mm,
                rain_mm=day.rain_mm,
                rain_probability_pct=day.rain_probability_pct,
                t_max_c=day.t_max_c,
                t_min_c=day.t_min_c,
                wind_max_kmh=day.wind_max_kmh,
            )
            for day in upcoming
        ],
        trace=[
            DayTraceOut(
                date=row.date.isoformat(),
                age_days=row.age_days,
                stage=row.stage,
                kc=row.kc,
                et0_mm=row.et0_mm,
                etc_mm=row.etc_mm,
                rain_mm=row.rain_mm,
                effective_rain_mm=row.effective_rain_mm,
                depletion_mm=row.depletion_end_mm,
            )
            for row in advice.trace
        ],
        assumptions=list(advice.assumptions),
        soil=advice.soil_key,
        soil_name_hi=advice.soil_name_hi,
        soil_name_en=advice.soil_name_en,
        soil_available_water_mm_per_m=advice.soil_available_water_mm_per_m,
        soil_is_default=advice.soil_is_default,
        next_irrigation_date=(
            advice.next_irrigation_date.isoformat()
            if advice.next_irrigation_date
            else None
        ),
        next_irrigation_mm=advice.next_irrigation_mm,
        next_irrigation_within_forecast=advice.next_irrigation_within_forecast,
        forecast_covered_until=(
            advice.forecast_covered_until.isoformat()
            if advice.forecast_covered_until
            else None
        ),
        usual_interval_days=advice.usual_interval_days,
        savings=(
            SavingsOut(
                window_start=savings.window_start.isoformat(),
                window_end=savings.window_end.isoformat(),
                habit_interval_days=savings.habit_interval_days,
                habit_mm_per_irrigation=savings.habit_mm_per_irrigation,
                habit_total_mm=savings.habit_total_mm,
                habit_irrigations=savings.habit_irrigations,
                advised_total_mm=savings.advised_total_mm,
                advised_irrigations=savings.advised_irrigations,
                saved_mm=savings.saved_mm,
                saved_litres_per_acre=savings.saved_litres_per_acre,
                pump_hours_saved=savings.pump_hours_saved,
                money_saved=savings.money_saved,
                money_unavailable_reason=savings.money_unavailable_reason,
                assumptions=list(savings.assumptions),
            )
            if savings is not None
            else None
        ),
        last_irrigation_date=(
            advice.last_irrigation_date.isoformat()
            if advice.last_irrigation_date
            else None
        ),
        last_irrigation_mm=advice.last_irrigation_mm,
        last_irrigation_effective_mm=advice.last_irrigation_effective_mm,
        sources=list(advice.sources),
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
