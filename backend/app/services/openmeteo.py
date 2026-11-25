"""Open-Meteo geocoding and forecast.

Field names below were confirmed against the live API, not guessed:

    GET /v1/forecast?daily=et0_fao_evapotranspiration,precipitation_sum,
        temperature_2m_max,temperature_2m_min,precipitation_probability_max,
        wind_speed_10m_max,wind_gusts_10m_max,relative_humidity_2m_mean
        -> daily.et0_fao_evapotranspiration  (mm)
           daily.precipitation_sum           (mm)
           daily.temperature_2m_max / _min   (degC)
           daily.precipitation_probability_max (%)
           daily.wind_speed_10m_max          (km/h)
           daily.wind_gusts_10m_max          (km/h)
           daily.relative_humidity_2m_mean   (%)

The three wind/humidity fields were added for the spray-window rule in
services/irrigation.py: spraying is unsafe above a wind threshold, and the
farmer is told to wait rather than losing the spray to drift.

    GET geocoding-api /v1/search?name=..&countryCode=IN
        -> results[].{id,name,latitude,longitude,admin1,admin2,timezone}

Open-Meteo needs no API key, which is why it is the weather source: nothing to
sign up for, nothing to leak in a public demo repo.

If the ET0 field is absent or null for a day, ET0 is computed with the
Hargreaves equation (FAO-56 eq. 52), which needs only Tmax, Tmin and the
extraterrestrial radiation Ra computed from latitude and day of year. That
keeps the engine fed instead of silently returning zero water demand, which
would produce dangerous "no need to irrigate" advice.
"""

import math
import time
from datetime import date

import httpx

from ..models.schemas import DayWeather, Location, WeatherForecast

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEZONE = "Asia/Kolkata"
CACHE_TTL_SECONDS = 600  # 10 minutes: a demo re-runs, a forecast does not change in seconds
HTTP_TIMEOUT = 12.0

DAILY_FIELDS = ",".join(
    [
        "et0_fao_evapotranspiration",
        "precipitation_sum",
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_probability_max",
        "wind_speed_10m_max",
        "wind_gusts_10m_max",
        "relative_humidity_2m_mean",
    ]
)

# Process-local cache. Two demo users hitting the same district do not need two
# upstream calls, and Open-Meteo is a free service worth being polite to.
_forecast_cache: dict[str, tuple[float, WeatherForecast]] = {}
_geocode_cache: dict[str, tuple[float, list[Location]]] = {}


def _cache_get(cache: dict, key: str):
    entry = cache.get(key)
    if not entry:
        return None
    stored_at, value = entry
    if time.monotonic() - stored_at > CACHE_TTL_SECONDS:
        cache.pop(key, None)
        return None
    return value


def clear_cache() -> None:
    """Used by tests and available for a manual refresh."""
    _forecast_cache.clear()
    _geocode_cache.clear()


def _display_name(result: dict) -> str:
    parts = [result.get("name")]
    admin2 = result.get("admin2")
    admin1 = result.get("admin1")
    # 'Patna' + 'Patna district' would read as a stutter, so skip a district
    # that merely repeats the town name.
    if admin2 and admin2.lower() not in (parts[0] or "").lower():
        parts.append(admin2)
    if admin1 and admin1.lower() not in (parts[0] or "").lower():
        parts.append(admin1)
    return ", ".join(p for p in parts if p)


async def search_locations(query: str, limit: int = 6) -> list[Location]:
    """Search Indian locations by name.

    Restricted to `countryCode=IN` so a farmer typing 'Patna' is never offered
    the other Patnas outside the country, and results are ordered by the
    population weight Open-Meteo already applies. Because several Indian towns
    share a name, the state and district are included in `display_name` so the
    choice is unambiguous.
    """
    query = query.strip()
    if len(query) < 2:
        return []

    cache_key = f"{query.lower()}|{limit}"
    cached = _cache_get(_geocode_cache, cache_key)
    if cached is not None:
        return cached

    params = {
        "name": query,
        "count": max(1, min(limit, 20)),
        "language": "en",
        "countryCode": "IN",
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.get(GEOCODE_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    locations = [
        Location(
            id=item["id"],
            name=item["name"],
            admin1=item.get("admin1"),
            admin2=item.get("admin2"),
            latitude=float(item["latitude"]),
            longitude=float(item["longitude"]),
            timezone=item.get("timezone"),
            display_name=_display_name(item),
        )
        for item in payload.get("results") or []
    ]
    _geocode_cache[cache_key] = (time.monotonic(), locations)
    return locations


def extraterrestrial_radiation(latitude_deg: float, day_of_year: int) -> float:
    """Ra in MJ m^-2 day^-1 (FAO-56 Chapter 3).

    Only needed by the Hargreaves fallback, but kept as a pure public function
    so it can be tested without a network.
    """
    phi = math.radians(latitude_deg)
    dr = 1 + 0.033 * math.cos(2 * math.pi * day_of_year / 365)
    delta = 0.409 * math.sin(2 * math.pi * day_of_year / 365 - 1.39)
    # Clamp guards the arccos domain at high latitudes / solstice extremes.
    x = max(-1.0, min(1.0, -math.tan(phi) * math.tan(delta)))
    omega_s = math.acos(x)
    return (24 * 60 / math.pi) * 0.0820 * dr * (
        omega_s * math.sin(phi) * math.sin(delta)
        + math.cos(phi) * math.cos(delta) * math.sin(omega_s)
    )


def hargreaves_et0(
    latitude_deg: float, day_of_year: int, t_max: float, t_min: float
) -> float:
    """Hargreaves reference ET0 in mm/day (FAO-56 eq. 52)."""
    spread = max(t_max - t_min, 0.0)
    t_mean = (t_max + t_min) / 2
    ra = extraterrestrial_radiation(latitude_deg, day_of_year)
    et0 = 0.0023 * (t_mean + 17.8) * math.sqrt(spread) * ra
    return max(0.0, round(et0, 2))


async def get_forecast(latitude: float, longitude: float, days: int = 7) -> WeatherForecast:
    """Fetch a daily forecast. Cached for 10 minutes per rounded coordinate."""
    days = max(1, min(days, 16))
    # ~1 km rounding: different taps in the same village share a cache entry.
    cache_key = f"{round(latitude, 2)},{round(longitude, 2)},{days}"
    cached = _cache_get(_forecast_cache, cache_key)
    if cached is not None:
        return cached

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": DAILY_FIELDS,
        "forecast_days": days,
        "timezone": TIMEZONE,
    }
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.get(FORECAST_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    daily = payload.get("daily") or {}
    dates = daily.get("time") or []
    et0_values = daily.get("et0_fao_evapotranspiration") or []
    rain_values = daily.get("precipitation_sum") or []
    t_max_values = daily.get("temperature_2m_max") or []
    t_min_values = daily.get("temperature_2m_min") or []
    probability_values = daily.get("precipitation_probability_max") or []
    wind_values = daily.get("wind_speed_10m_max") or []
    gust_values = daily.get("wind_gusts_10m_max") or []
    humidity_values = daily.get("relative_humidity_2m_mean") or []

    day_rows: list[DayWeather] = []
    for index, day_iso in enumerate(dates):
        t_max = _at(t_max_values, index)
        t_min = _at(t_min_values, index)
        if t_max is None or t_min is None:
            # Without temperatures there is no defensible ET0 either way; skip
            # the day rather than invent one.
            continue

        et0 = _at(et0_values, index)
        source = "open-meteo"
        if et0 is None or et0 <= 0:
            et0 = hargreaves_et0(
                latitude, date.fromisoformat(day_iso).timetuple().tm_yday, t_max, t_min
            )
            source = "hargreaves"

        probability = _at(probability_values, index)
        wind = _at(wind_values, index)
        gust = _at(gust_values, index)
        humidity = _at(humidity_values, index)
        day_rows.append(
            DayWeather(
                date=day_iso,
                et0_mm=round(float(et0), 2),
                rain_mm=round(float(_at(rain_values, index) or 0.0), 2),
                rain_probability_pct=int(probability) if probability is not None else None,
                t_max_c=round(float(t_max), 1),
                t_min_c=round(float(t_min), 1),
                wind_max_kmh=round(float(wind), 1) if wind is not None else None,
                wind_gust_kmh=round(float(gust), 1) if gust is not None else None,
                humidity_mean_pct=int(humidity) if humidity is not None else None,
                et0_source=source,
            )
        )

    if not day_rows:
        raise ValueError("Weather service returned no usable daily data")

    forecast = WeatherForecast(
        latitude=float(payload.get("latitude", latitude)),
        longitude=float(payload.get("longitude", longitude)),
        timezone=payload.get("timezone", TIMEZONE),
        days=day_rows,
    )
    _forecast_cache[cache_key] = (time.monotonic(), forecast)
    return forecast


def _at(values: list, index: int):
    """List-index with a None result instead of IndexError.

    Open-Meteo omits trailing values rather than padding them, so parallel
    arrays can be shorter than the time array.
    """
    if index < len(values):
        return values[index]
    return None
