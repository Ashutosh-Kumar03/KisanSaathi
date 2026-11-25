"""Deterministic irrigation engine — pure functions, no I/O.

This module is the part of KisanSaathi that is allowed to decide something. It
takes plain values in and returns plain values out: no HTTP, no clock, no
environment, no model. That is deliberate on two counts.

First, agronomic advice has to be testable without a network. A recommendation a
farmer acts on can be checked in a unit test only if computing it requires
nothing but numbers.

Second, and the reason this file exists at all: the language model must never
compute the recommendation. Narration explains the numbers produced here and is
not permitted to change them. Because the engine cannot reach a network, that
rule is enforced by construction rather than by discipline.

The method is the FAO-56 single crop coefficient water balance:

    ETc(i) = Kc(i) x ET0(i)
    Dr(i)  = Dr(i-1) - effective_rain(i) + ETc(i)      (Dr never below 0)
    TAW    = available_water_capacity x root_depth
    RAW    = p x TAW

Irrigation is due when depletion Dr reaches RAW, the point at which the crop
starts to suffer stress. Net application refills to field capacity; gross
divides by the application efficiency, because flood irrigation loses some of
what is applied. Water is reported in mm and in litres per acre, since
"32 mm" means nothing to a farmer standing at a pump but "1,30,000 litres" does.

What this engine cannot know, and therefore states rather than guesses:

  * Depletion before the first day it is given. It starts from
    `depletion_start_mm` (0 = field capacity, the usual state after a sowing
    irrigation) and reports how much of the season it actually covered, so the
    UI can say "assumed" rather than implying measured soil moisture.
  * Soil type. A loam default is used and surfaced as an assumption chip.
  * Anything about the farm's actual water supply, pump, or labour.

Effective rainfall is rain x RAIN_EFFECTIVENESS. A downpour partly runs off and
partly evaporates, so treating every millimetre as stored water would
systematically over-estimate soil moisture and under-advise irrigation -- the
dangerous direction for a crop.
"""

from dataclasses import dataclass
from datetime import date

from ..data import crop_rules
from ..data.crop_rules import CropRules

# Share of forecast rain counted as stored in the root zone. Runoff and
# evaporation take the rest. Operational: no published figure is claimed.
RAIN_EFFECTIVENESS = 0.8

# Litres of water per millimetre spread over one acre (1 mm x 4046.86 m2).
LITRES_PER_MM_ACRE = 4046.86

# Rain in the next 24 h above which irrigating today is wasted effort.
RAIN_SUBSTITUTES_IRRIGATION_MM = 15.0


class EngineInputError(ValueError):
    """Raised when the caller supplies something the engine cannot act on."""


@dataclass(frozen=True)
class EngineDay:
    """One day of weather, already in the units the balance needs.

    Deliberately not the Pydantic model: keeping the engine's input a plain
    dataclass means the balance can be tested without constructing API objects.
    """

    date: date
    et0_mm: float
    rain_mm: float
    wind_max_kmh: float | None = None
    rain_probability_pct: int | None = None


@dataclass(frozen=True)
class DayTrace:
    """One row of the working, so the UI can show why a day looked the way it did."""

    date: date
    age_days: int
    stage: str
    kc: float
    et0_mm: float
    etc_mm: float
    rain_mm: float
    effective_rain_mm: float
    depletion_start_mm: float
    depletion_end_mm: float


@dataclass(frozen=True)
class ActionWindow:
    """Whether a spray or a urea top-dressing should go ahead, and why.

    `verdict` is one of "go", "wait", or "unknown". "unknown" is returned when
    the forecast lacks the field needed to judge, which is honest -- claiming
    "safe to spray" from missing data would cost the farmer the spray.
    """

    verdict: str
    reason_hi: str
    reason_en: str


@dataclass(frozen=True)
class Advice:
    """The decision, its arithmetic, and the assumptions behind it."""

    # IRRIGATE_TODAY | WAIT_RAIN | SOIL_MOISTURE_OK | SEASON_OVER
    action: str
    crop_key: str
    crop_name_hi: str
    crop_name_en: str
    today: date
    age_days: int
    stage: str
    in_critical_window: bool
    critical_window_label: str | None

    net_mm: float
    gross_mm: float
    litres_per_acre: int

    depletion_mm: float
    taw_mm: float
    raw_mm: float
    rain_next_24h_mm: float

    spray: ActionWindow
    urea: ActionWindow
    critical_window_source: str | None

    # The date the balance was reset by a known irrigation, or None when the
    # farmer did not say. Surfaced to the UI because an unstated assumption
    # about soil moisture is exactly the kind of thing that should be visible.
    last_irrigation_date: date | None

    trace: tuple[DayTrace, ...]
    assumptions: tuple[str, ...]
    sources: tuple[str, ...]


def _round(value: float, places: int = 1) -> float:
    return round(float(value), places)


def _judge_spray(days: list[EngineDay], today: date) -> ActionWindow:
    """Judge the next 24 h for spraying: no rain to wash it off, no wind to drift it."""
    upcoming = [d for d in days if d.date >= today][:1]
    if not upcoming:
        return ActionWindow(
            "unknown",
            "अगले दिन का पूर्वानुमान नहीं है, इसलिए छिड़काव के बारे में कुछ नहीं कहा जा सकता।",
            "No forecast for tomorrow, so nothing can be said about spraying.",
        )

    day = upcoming[0]
    rain_limit = crop_rules.SPRAY_RAIN_MM_24H.value
    wind_limit = crop_rules.SPRAY_WIND_KMH.value

    if day.rain_mm >= rain_limit:
        return ActionWindow(
            "wait",
            f"कल {day.rain_mm:.0f} मिमी बारिश का अनुमान है — छिड़काव बारिश के बाद करें, "
            "अभी करने से दवा बह जाएगी।",
            f"About {day.rain_mm:.0f} mm rain is expected — spray after it passes, or the "
            "chemical will wash off.",
        )

    if day.wind_max_kmh is not None and day.wind_max_kmh > wind_limit:
        return ActionWindow(
            "wait",
            f"कल हवा {day.wind_max_kmh:.0f} किमी/घंटा तक चलेगी — तेज़ हवा में छिड़काव "
            "उड़ जाता है, शांत दिन चुनें।",
            f"Wind is forecast at {day.wind_max_kmh:.0f} km/h — spray drifts in that, so "
            "pick a calmer day.",
        )

    if day.wind_max_kmh is None and day.rain_probability_pct is None:
        return ActionWindow(
            "unknown",
            "मौसम का पूरा ब्योरा नहीं मिला, इसलिए छिड़काव के बारे में कुछ नहीं कहा जा सकता।",
            "The forecast is incomplete, so nothing can be said about spraying.",
        )

    return ActionWindow(
        "go",
        "कल छिड़काव के लिए मौसम ठीक है — बारिश और तेज़ हवा का अनुमान नहीं है।",
        "Tomorrow looks fine for spraying — no rain and no strong wind forecast.",
    )


def _judge_urea(days: list[EngineDay], today: date) -> ActionWindow:
    """Judge the next 48 h for a urea top-dressing: heavy rain would leach it away."""
    upcoming = [d for d in days if d.date >= today][:2]
    if not upcoming:
        return ActionWindow(
            "unknown",
            "आगे का पूर्वानुमान नहीं है, इसलिए खाद के बारे में कुछ नहीं कहा जा सकता।",
            "No forecast ahead, so nothing can be said about fertiliser.",
        )

    total_rain = sum(d.rain_mm for d in upcoming)
    limit = crop_rules.UREA_HEAVY_RAIN_MM_48H.value

    if total_rain >= limit:
        return ActionWindow(
            "wait",
            f"अगले दो दिन में {total_rain:.0f} मिमी बारिश का अनुमान है — यूरिया अभी न "
            "डालें, बारिश के बाद डालें वरना खाद बह जाएगी।",
            f"About {total_rain:.0f} mm rain is expected over two days — hold the urea until "
            "after it, or the nitrogen leaches away.",
        )

    return ActionWindow(
        "go",
        "अगले दो दिन भारी बारिश का अनुमान नहीं है — खाद डालने का समय ठीक है।",
        "No heavy rain is forecast for two days — a fine time to apply fertiliser.",
    )


def advise(
    crop: CropRules,
    sowing_date: date,
    today: date,
    days: list[EngineDay],
    depletion_start_mm: float = 0.0,
    last_irrigation_date: date | None = None,
) -> Advice:
    """Compute today's irrigation decision plus the per-day working behind it.

    `days` must be in chronological order and cover at least today. It may
    begin after the sowing date, in which case the balance starts from
    `depletion_start_mm` and the assumptions say so.

    `last_irrigation_date` is the farmer's own recollection of when they last
    watered, and it matters more than any other optional input. A field that
    was irrigated a week ago is not dry, so without it the balance either piles
    up a month of imaginary deficit (advising water the crop already has) or,
    if the season is short, never reaches the stress point at all. On that date
    the roots are back at field capacity, so depletion restarts from zero and
    only the days after it count. When the date is unknown the engine keeps its
    previous reading and says plainly that it assumed no irrigation.
    """
    if not days:
        raise EngineInputError("no weather days supplied")
    if today < sowing_date:
        raise EngineInputError("sowing date is in the future")
    if last_irrigation_date is not None:
        if last_irrigation_date > today:
            raise EngineInputError("last irrigation date is in the future")
        if last_irrigation_date < sowing_date:
            raise EngineInputError("last irrigation date is before sowing")

    ordered = sorted(days, key=lambda d: d.date)
    if ordered[-1].date < today:
        raise EngineInputError("weather data does not reach today")

    age_today = (today - sowing_date).days

    taw = crop_rules.SOIL_AVAILABLE_WATER_MM_PER_M.value * crop.root_depth_m.value
    raw = crop.depletion_fraction.value * taw
    efficiency = crop.application_efficiency.value

    trace: list[DayTrace] = []
    depletion = max(depletion_start_mm, 0.0)

    for day in ordered:
        age = (day.date - sowing_date).days
        # Before sowing there is no crop taking water: skip rather than
        # attribute the weather to a season that has not begun.
        if age < 0:
            continue

        kc = crop.kc_for_age(age)
        etc = kc * day.et0_mm
        effective_rain = day.rain_mm * RAIN_EFFECTIVENESS

        # A known irrigation refills the root zone to field capacity, so the
        # deficit restarts at zero on that date. Applied before the day's own
        # demand rather than after, so the day the farmer actually watered
        # still counts the water the crop drew that day -- the water was given
        # in the morning, not at midnight.
        if last_irrigation_date is not None and day.date == last_irrigation_date:
            depletion = 0.0

        start_depletion = depletion
        depletion = depletion - effective_rain + etc
        # Water cannot be more than fully available nor more than absent.
        depletion = max(0.0, min(depletion, taw))

        trace.append(
            DayTrace(
                date=day.date,
                age_days=age,
                stage=crop.stage_name(age),
                kc=_round(kc, 2),
                et0_mm=_round(day.et0_mm, 2),
                etc_mm=_round(etc, 2),
                rain_mm=_round(day.rain_mm, 2),
                effective_rain_mm=_round(effective_rain, 2),
                depletion_start_mm=_round(start_depletion, 1),
                depletion_end_mm=_round(depletion, 1),
            )
        )

    if not trace:
        raise EngineInputError("weather data does not overlap the crop season")

    window = crop.critical_window(age_today)
    rain_next_24h = sum(d.rain_mm for d in ordered if d.date == today)

    # The decision depends on soil moisture *now*, not on where the balance
    # lands at the end of the forecast week. Using the end of the trace here
    # would let dry days later in the week pull today's advice forward.
    today_rows = [row for row in trace if row.date == today]
    if not today_rows:
        raise EngineInputError("no weather row for today")
    depletion_today = today_rows[0].depletion_end_mm

    # ---- the decision -------------------------------------------------
    if age_today > crop.stages.total:
        action = "SEASON_OVER"
        net_mm = 0.0
    elif depletion_today >= raw:
        # The crop is at or past the stress point. Irrigating is justified
        # unless substantial rain is about to do the job for free.
        if rain_next_24h >= RAIN_SUBSTITUTES_IRRIGATION_MM:
            action = "WAIT_RAIN"
            net_mm = 0.0
        else:
            action = "IRRIGATE_TODAY"
            net_mm = depletion_today
    elif rain_next_24h >= RAIN_SUBSTITUTES_IRRIGATION_MM:
        action = "WAIT_RAIN"
        net_mm = 0.0
    else:
        action = "SOIL_MOISTURE_OK"
        net_mm = 0.0

    gross_mm = net_mm / efficiency if net_mm > 0 else 0.0
    litres = int(round(gross_mm * LITRES_PER_MM_ACRE))

    assumptions = [
        "मिट्टी: दोमट (loam), जलधारण 150 मिमी प्रति मीटर गहराई",
        "सिंचाई विधि: बहाव/फ्लड, दक्षता 70%",
        "बारिश का 80% ही जड़ तक पहुँचता माना गया है (बहाव व वाष्पीकरण घटाकर)",
    ]
    if trace and trace[0].age_days > 0:
        assumptions.append(
            f"बोने के बाद का पहला पूर्वानुमान {trace[0].age_days} दिन बाद से है; "
            "उससे पहले की मिट्टी की नमी मापी नहीं गई"
        )

    # The soil-moisture assumption is stated in words either way. "We assumed
    # no irrigation" is a very different claim from "we assumed you watered on
    # the 12th", and the farmer is the only one who can tell which is true.
    reset_covered = (
        last_irrigation_date is not None
        and bool(trace)
        and last_irrigation_date >= trace[0].date
    )
    if last_irrigation_date is None:
        assumptions.append(
            "यह सलाह मानती है कि बोने के बाद से अब तक सिंचाई नहीं हुई है। "
            "अगर सिंचाई की थी, तो तारीख डालकर सलाह फिर लें।"
        )
    elif reset_covered:
        assumptions.append(
            f"पिछली सिंचाई {last_irrigation_date.strftime('%d-%m-%Y')} को मानी गई है; "
            "उस दिन मिट्टी में पानी पूरा (कमी शून्य) माना गया है"
        )
    else:
        # The farmer gave a date but the weather we could fetch does not reach
        # back to it, so the reset never happened. Say so instead of quietly
        # presenting a balance that ignores what they told us.
        assumptions.append(
            f"पिछली सिंचाई की तारीख {last_irrigation_date.strftime('%d-%m-%Y')} उपलब्ध "
            "मौसम डेटा की अवधि से पहले है, इसलिए गणना उपलब्ध पहले दिन से शुरू की गई है"
        )

    sources = [
        crop.kc_initial.source,
        crop.root_depth_m.source,
        crop.depletion_fraction.source,
        crop_rules.SOIL_AVAILABLE_WATER_MM_PER_M.source,
    ]
    if window is not None:
        sources.append(window.source)

    return Advice(
        action=action,
        crop_key=crop.key,
        crop_name_hi=crop.name_hi,
        crop_name_en=crop.name_en,
        today=today,
        age_days=age_today,
        stage=crop.stage_name(age_today),
        in_critical_window=window is not None,
        critical_window_label=window.label if window else None,
        net_mm=_round(net_mm),
        gross_mm=_round(gross_mm),
        litres_per_acre=litres,
        depletion_mm=_round(depletion_today),
        taw_mm=_round(taw),
        raw_mm=_round(raw),
        rain_next_24h_mm=_round(rain_next_24h),
        spray=_judge_spray(ordered, today),
        urea=_judge_urea(ordered, today),
        critical_window_source=window.source if window else None,
        last_irrigation_date=last_irrigation_date,
        trace=tuple(trace),
        assumptions=tuple(assumptions),
        sources=tuple(dict.fromkeys(sources)),
    )
