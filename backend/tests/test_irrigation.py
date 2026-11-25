"""Tests for the irrigation engine and the crop rule data.

Table-driven on purpose: the interesting cases are "this weather should produce
that decision", and a table makes a new case one line rather than one function.

These tests need no network and no fixtures beyond plain dates. If any of them
ever starts requiring a server, the engine has stopped being pure and the
property that makes it testable at all has been lost.
"""

from datetime import date, timedelta

import pytest

from app.data import crop_rules
from app.data.crop_rules import RICE, WHEAT, get_crop
from app.services.irrigation import (
    LITRES_PER_MM_ACRE,
    EngineDay,
    EngineInputError,
    advise,
)

SOWING = date(2026, 11, 1)


def series(upto: date, et0_fn, rain_fn, wind: float | None = 5.0) -> list[EngineDay]:
    """Daily weather from sowing through `upto`, so the balance has real history."""
    count = (upto - SOWING).days + 1
    return [
        EngineDay(SOWING + timedelta(days=i), et0_fn(i), rain_fn(i), wind)
        for i in range(count)
    ]


def dry(upto: date, et0: float = 5.0) -> list[EngineDay]:
    return series(upto, lambda i: et0, lambda i: 0.0)


# --- the decision table ----------------------------------------------------


@pytest.mark.parametrize(
    "crop,days_after_sowing,et0,rain,rain_mode,expected",
    [
        # A dry month since sowing: depletion has passed RAW, irrigate.
        (WHEAT, 30, 5.0, 0.0, "none", "IRRIGATE_TODAY"),
        # Same season, but 25 mm lands today: the rain does the job, wait.
        (WHEAT, 30, 5.0, 25.0, "today", "WAIT_RAIN"),
        # Steady rain all season keeps the profile near field capacity.
        (WHEAT, 30, 5.0, 6.0, "all", "SOIL_MOISTURE_OK"),
        # A single 6 mm shower on an already-depleted soil is not enough: the
        # profile only wets the top, so the crop is still short of water.
        (WHEAT, 30, 5.0, 6.0, "today", "IRRIGATE_TODAY"),
        # Rice tolerates far less depletion (p=0.20), so it triggers sooner.
        (RICE, 20, 5.0, 0.0, "none", "IRRIGATE_TODAY"),
        # Newly sown crop has barely transpired: nothing to do yet.
        (WHEAT, 1, 3.0, 0.0, "none", "SOIL_MOISTURE_OK"),
    ],
)
def test_decision_table(crop, days_after_sowing, et0, rain, rain_mode, expected):
    today = SOWING + timedelta(days=days_after_sowing)

    if rain_mode == "none":
        rain_fn = lambda i: 0.0  # noqa: E731
    elif rain_mode == "today":
        rain_fn = lambda i: rain if i == days_after_sowing else 0.0  # noqa: E731
    else:
        rain_fn = lambda i: rain  # noqa: E731

    days = series(today + timedelta(days=6), lambda i: et0, rain_fn)
    advice = advise(crop, SOWING, today, days)
    assert advice.action == expected, (
        f"{crop.key} day {days_after_sowing} et0={et0} rain={rain} "
        f"({rain_mode}) -> {advice.action}"
    )


def test_season_over_stops_advising():
    today = SOWING + timedelta(days=WHEAT.stages.total + 10)
    advice = advise(WHEAT, SOWING, today, dry(today))
    assert advice.action == "SEASON_OVER"
    assert advice.net_mm == 0.0
    assert advice.litres_per_acre == 0


# --- agronomy behaves the way the tables say -------------------------------


def test_later_stage_demands_more_water():
    """Mid-season Kc 1.15 must produce a larger ETc than initial-stage Kc 0.70."""
    early = WHEAT.kc_for_age(5) * 5.0
    mid = WHEAT.kc_for_age(60) * 5.0
    assert mid > early
    assert WHEAT.kc_for_age(60) == pytest.approx(WHEAT.kc_mid.value)


@pytest.mark.parametrize(
    "crop,anchor_day,expected_kc",
    [
        (WHEAT, 0, 0.70),   # initial
        (WHEAT, 40, 1.15),  # first day of mid season
        (WHEAT, 120, 0.40),  # end of season
        (RICE, 0, 1.05),
        (RICE, 60, 1.20),
        (RICE, 150, 0.90),
    ],
)
def test_kc_hits_tabulated_anchors(crop, anchor_day, expected_kc):
    assert crop.kc_for_age(anchor_day) == pytest.approx(expected_kc)


@pytest.mark.parametrize("crop", [WHEAT, RICE])
def test_kc_stays_inside_the_curve(crop):
    for age in range(0, crop.stages.total + 30):
        assert 0.2 <= crop.kc_for_age(age) <= 1.25


def test_depletion_never_negative_and_never_exceeds_taw():
    """Heavy rain cannot leave negative depletion; drought cannot exceed TAW."""
    today = SOWING + timedelta(days=40)
    for rain in (0.0, 5.0, 200.0):
        advice = advise(WHEAT, SOWING, today, series(today + timedelta(days=5), lambda i: 6.0, lambda i: rain))
        for row in advice.trace:
            assert 0.0 <= row.depletion_end_mm <= advice.taw_mm + 0.05, (
                f"rain={rain} {row.date} {row.depletion_end_mm}"
            )


def test_irrigation_amount_is_net_over_efficiency():
    today = SOWING + timedelta(days=30)
    advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=7)))
    assert advice.action == "IRRIGATE_TODAY"
    assert advice.net_mm > 0
    # gross is always larger than net, because flood irrigation loses some.
    assert advice.gross_mm > advice.net_mm
    assert advice.gross_mm == pytest.approx(
        advice.net_mm / WHEAT.application_efficiency.value, abs=0.15
    )


def test_litres_match_millimetres():
    today = SOWING + timedelta(days=30)
    advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=7)))
    expected = advice.gross_mm * LITRES_PER_MM_ACRE
    assert advice.litres_per_acre == pytest.approx(expected, rel=0.001)


def test_rain_suppresses_a_due_irrigation():
    """The dangerous case: crop is thirsty, but rain is about to arrive."""
    today = SOWING + timedelta(days=30)
    thirsty = advise(WHEAT, SOWING, today, dry(today + timedelta(days=7)))
    assert thirsty.action == "IRRIGATE_TODAY"

    with_rain = advise(
        WHEAT,
        SOWING,
        today,
        series(today + timedelta(days=7), lambda i: 5.0, lambda i: 25.0 if i == 30 else 0.0),
    )
    assert with_rain.action == "WAIT_RAIN"
    assert with_rain.rain_next_24h_mm >= 25.0
    assert with_rain.net_mm == 0.0


# --- spray and fertiliser windows -----------------------------------------


def test_spray_waits_for_rain():
    today = SOWING + timedelta(days=20)
    advice = advise(
        WHEAT, SOWING, today,
        series(today, lambda i: 4.0, lambda i: 12.0 if i == 20 else 0.0),
    )
    assert advice.spray.verdict == "wait"
    assert advice.spray.reason_hi  # the Hindi sentence exists


def test_spray_waits_for_high_wind():
    today = SOWING + timedelta(days=20)
    advice = advise(WHEAT, SOWING, today, series(today, lambda i: 4.0, lambda i: 0.0, wind=25.0))
    assert advice.spray.verdict == "wait"


def test_spray_goes_on_a_calm_dry_day():
    today = SOWING + timedelta(days=20)
    advice = advise(WHEAT, SOWING, today, series(today, lambda i: 4.0, lambda i: 0.0, wind=4.0))
    assert advice.spray.verdict == "go"


def test_spray_is_unknown_without_wind_data():
    """Missing wind must not be read as 'calm', which would risk the spray."""
    today = SOWING + timedelta(days=20)
    days = [EngineDay(today, 4.0, 0.0, None)]
    advice = advise(WHEAT, SOWING, today, days)
    assert advice.spray.verdict == "unknown"


def test_urea_waits_for_heavy_rain():
    today = SOWING + timedelta(days=20)
    advice = advise(
        WHEAT, SOWING, today,
        series(today + timedelta(days=1), lambda i: 4.0, lambda i: 15.0 if i >= 20 else 0.0),
    )
    assert advice.urea.verdict == "wait"


def test_urea_goes_when_no_heavy_rain_ahead():
    today = SOWING + timedelta(days=20)
    advice = advise(WHEAT, SOWING, today, series(today + timedelta(days=1), lambda i: 4.0, lambda i: 0.0))
    assert advice.urea.verdict == "go"


# --- provenance ------------------------------------------------------------


def test_every_number_shown_carries_a_source():
    today = SOWING + timedelta(days=17)
    advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=3)))
    assert advice.sources
    for source in advice.sources:
        assert len(source) > 20, f"citation too thin to check: {source!r}"
    # No citation may be invented: everything traces to FAO-56, TNAU or an
    # explicit statement that it is this app's own threshold.
    for source in advice.sources:
        assert (
            "FAO-56" in source
            or "TNAU" in source
            or "Operational" in source
        ), source


def test_wheat_critical_window_is_reported_with_its_source():
    today = SOWING + timedelta(days=17)  # inside crown root initiation (15-20)
    advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=3)))
    assert advice.in_critical_window is True
    assert advice.critical_window_label == "crown root initiation"
    assert "TNAU" in (advice.critical_window_source or "")


def test_assumptions_are_always_disclosed():
    today = SOWING + timedelta(days=10)
    advice = advise(WHEAT, SOWING, today, dry(today))
    assert advice.assumptions
    joined = " ".join(advice.assumptions)
    assert "दोमट" in joined  # soil type is stated, not hidden


# --- the last-irrigation reset -------------------------------------------


@pytest.mark.parametrize(
    "days_since_irrigation,expected_action,note",
    [
        # Watered yesterday: the profile is refilled, so a month-long dry spell
        # before that no longer justifies watering again today.
        (1, "SOIL_MOISTURE_OK", "reset yesterday clears the accumulated deficit"),
        # Watered 20 days ago: real deficit has built up since, past RAW.
        (20, "IRRIGATE_TODAY", "20 dry days since a reset still reach the stress point"),
        # Watered today: the balance is the day's own demand, never negative.
        (0, "SOIL_MOISTURE_OK", "watering today leaves only today's ETc"),
    ],
)
def test_last_irrigation_resets_the_balance(days_since_irrigation, expected_action, note):
    today = SOWING + timedelta(days=30)
    last = today - timedelta(days=days_since_irrigation)
    advice = advise(
        WHEAT, SOWING, today, dry(today + timedelta(days=7)), last_irrigation_date=last
    )
    assert advice.action == expected_action, f"{note}: got {advice.action}"
    assert advice.last_irrigation_date == last


def test_irrigation_date_changes_the_advice_it_would_give_without_it():
    """The same weather must produce a different decision once the reset is known."""
    today = SOWING + timedelta(days=30)
    days = dry(today + timedelta(days=7))

    without = advise(WHEAT, SOWING, today, days)
    with_recent = advise(
        WHEAT, SOWING, today, days, last_irrigation_date=today - timedelta(days=1)
    )

    assert without.action == "IRRIGATE_TODAY"
    assert with_recent.action == "SOIL_MOISTURE_OK"
    assert with_recent.depletion_mm < without.depletion_mm
    # Irrigating today is a real amount of water; skipping it is zero.
    assert without.litres_per_acre > 0
    assert with_recent.litres_per_acre == 0


def test_reset_applies_only_from_that_date_onwards():
    """Days before the reset still accumulate deficit; the reset day starts at 0."""
    today = SOWING + timedelta(days=30)
    last = today - timedelta(days=10)
    advice = advise(
        WHEAT, SOWING, today, dry(today + timedelta(days=7)), last_irrigation_date=last
    )

    by_date = {row.date: row for row in advice.trace}
    day_before = by_date[last - timedelta(days=1)]
    reset_day = by_date[last]

    # Before the reset the deficit had built up over the season.
    assert day_before.depletion_end_mm > 0
    # The reset day starts from a full profile, then pays its own ETc.
    assert reset_day.depletion_start_mm == 0.0
    assert 0 < reset_day.depletion_end_mm <= reset_day.etc_mm + 0.05


def test_no_irrigation_date_says_so_out_loud():
    today = SOWING + timedelta(days=30)
    advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=7)))

    assert advice.last_irrigation_date is None
    joined = " ".join(advice.assumptions)
    assert "सिंचाई नहीं हुई" in joined


def test_given_irrigation_date_is_disclosed_with_its_date():
    today = SOWING + timedelta(days=30)
    last = today - timedelta(days=5)
    advice = advise(
        WHEAT, SOWING, today, dry(today + timedelta(days=7)), last_irrigation_date=last
    )

    joined = " ".join(advice.assumptions)
    assert last.strftime("%d-%m-%Y") in joined
    # The "no irrigation" line must not also be present, or the two
    # contradictory claims would both be shown to the farmer.
    assert "सिंचाई नहीं हुई" not in joined


def test_irrigation_date_older_than_available_weather_is_disclosed():
    """A reset the forecast cannot reach must not be silently ignored."""
    today = SOWING + timedelta(days=40)
    # Weather only from 20 days after sowing, but the irrigation was earlier.
    days = [
        EngineDay(SOWING + timedelta(days=i), 5.0, 0.0, 5.0)
        for i in range(20, 48)
    ]
    advice = advise(
        WHEAT,
        SOWING,
        today,
        days,
        last_irrigation_date=SOWING + timedelta(days=5),
    )
    joined = " ".join(advice.assumptions)
    assert "उपलब्ध" in joined  # says the date precedes the available data


@pytest.mark.parametrize(
    "offset_days,message",
    [
        (1, "in the future"),
        (-1, "before sowing"),
    ],
)
def test_rejects_impossible_irrigation_dates(offset_days, message):
    today = SOWING + timedelta(days=30)
    bad = today + timedelta(days=offset_days) if offset_days > 0 else SOWING - timedelta(days=1)
    with pytest.raises(EngineInputError) as exc:
        advise(
            WHEAT,
            SOWING,
            today,
            dry(today + timedelta(days=3)),
            last_irrigation_date=bad,
        )
    assert message in str(exc.value)


# --- last irrigation amount --------------------------------------------------


@pytest.mark.parametrize(
    "amount_mm,expected_action,expect_absorbed_full,note",
    [
        # Zero: the record exists but no water was actually applied, so the
        # balance must be identical to never having been reset.
        (0.0, "IRRIGATE_TODAY", None, "zero amount changes nothing"),
        # Partial: 20 mm of a 119 mm deficit clears only part of it.
        (20.0, "IRRIGATE_TODAY", 20.0, "partial amount only partly refills"),
        # Comfortably more than the deficit: capped, and the crop is fine.
        (500.0, "SOIL_MOISTURE_OK", None, "large amount is capped at the deficit"),
    ],
)
def test_last_irrigation_amount(amount_mm, expected_action, expect_absorbed_full, note):
    today = SOWING + timedelta(days=30)
    last = today - timedelta(days=2)
    advice = advise(
        WHEAT,
        SOWING,
        today,
        dry(today + timedelta(days=7)),
        last_irrigation_date=last,
        last_irrigation_mm=amount_mm,
    )
    assert advice.action == expected_action, f"{note}: got {advice.action}"
    # Absorbed water can never exceed what was applied.
    assert advice.last_irrigation_effective_mm <= amount_mm + 0.05
    if expect_absorbed_full is not None:
        assert advice.last_irrigation_effective_mm == pytest.approx(
            expect_absorbed_full, abs=0.15
        )


def test_zero_amount_matches_no_irrigation_information_at_all():
    """A recorded irrigation of 0 mm is the same as having forgotten to water."""
    today = SOWING + timedelta(days=30)
    last = today - timedelta(days=2)
    days = dry(today + timedelta(days=7))

    # With no date the engine assumes a refill, so compare against the dated
    # case with zero, which must keep the deficit rather than wipe it.
    dated_zero = advise(
        WHEAT, SOWING, today, days, last_irrigation_date=last, last_irrigation_mm=0.0
    )
    refilled = advise(WHEAT, SOWING, today, days, last_irrigation_date=last)

    assert dated_zero.depletion_mm > refilled.depletion_mm
    assert dated_zero.last_irrigation_effective_mm == 0.0


def test_amount_larger_than_depletion_is_capped_not_credited():
    """Excess water drains past the roots and must not be banked as soil water."""
    today = SOWING + timedelta(days=30)
    last = today - timedelta(days=2)
    days = dry(today + timedelta(days=7))

    # Find the deficit the irrigation actually meets, by running without an
    # amount but with the date so the reset is at the same point.
    baseline = advise(WHEAT, SOWING, today, days, last_irrigation_date=last)

    fat = advise(
        WHEAT, SOWING, today, days, last_irrigation_date=last, last_irrigation_mm=500.0
    )

    # Absorbed can never exceed the depletion that was there to be filled.
    assert fat.last_irrigation_effective_mm <= fat.taw_mm + 0.05
    # And 500 mm of absorbed water would have been absurd: it was capped.
    assert fat.last_irrigation_effective_mm < 500.0
    # The advice is therefore identical to a full refill, not better than it.
    assert fat.depletion_mm == pytest.approx(baseline.depletion_mm, abs=0.2)


def test_percolation_loss_is_disclosed_only_when_it_happens():
    today = SOWING + timedelta(days=30)
    last = today - timedelta(days=2)
    days = dry(today + timedelta(days=7))

    wasteful = advise(
        WHEAT, SOWING, today, days, last_irrigation_date=last, last_irrigation_mm=500.0
    )
    frugal = advise(
        WHEAT, SOWING, today, days, last_irrigation_date=last, last_irrigation_mm=10.0
    )

    assert "बह गया" in " ".join(wasteful.assumptions)
    assert "बह गया" not in " ".join(frugal.assumptions)


@pytest.mark.parametrize(
    "kwargs,message",
    [
        ({"last_irrigation_mm": 20.0}, "needs a last irrigation date"),
        (
            {"last_irrigation_date": SOWING + timedelta(days=2), "last_irrigation_mm": -5.0},
            "cannot be negative",
        ),
    ],
)
def test_rejects_impossible_irrigation_amounts(kwargs, message):
    today = SOWING + timedelta(days=30)
    with pytest.raises(EngineInputError) as exc:
        advise(WHEAT, SOWING, today, dry(today + timedelta(days=3)), **kwargs)
    assert message in str(exc.value)


# --- next irrigation date ----------------------------------------------------


def test_next_irrigation_is_today_when_already_stressed():
    today = SOWING + timedelta(days=30)
    advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=7)))
    assert advice.action == "IRRIGATE_TODAY"
    assert advice.next_irrigation_date == today
    assert advice.next_irrigation_within_forecast is True


@pytest.mark.parametrize("soil_key", ["sandy", "loam", "clay"])
def test_next_irrigation_lands_inside_the_forecast_window(soil_key):
    today = SOWING + timedelta(days=20)
    advice = advise(
        WHEAT,
        SOWING,
        today,
        dry(today + timedelta(days=9)),
        soil=crop_rules.get_soil(soil_key),
    )
    assert advice.next_irrigation_date is not None, soil_key
    # Never a date the weather does not cover.
    assert today <= advice.next_irrigation_date <= advice.forecast_covered_until
    # When the crop is not already stressed the date must be in the future; a
    # "today" on an unstressed crop would be a projection bug.
    if advice.action != "IRRIGATE_TODAY":
        assert advice.next_irrigation_date > today


def test_next_irrigation_is_reported_as_absent_rather_than_extrapolated():
    """Wet forecast: no date, and the window's end is stated so it is honest."""
    today = SOWING + timedelta(days=20)
    advice = advise(WHEAT, SOWING, today, series(today + timedelta(days=6), lambda i: 5.0, lambda i: 9.0))

    assert advice.next_irrigation_date is None
    assert advice.next_irrigation_within_forecast is False
    assert advice.forecast_covered_until == today + timedelta(days=6)
    assert advice.next_irrigation_mm == 0.0


def test_next_irrigation_moves_later_with_wetter_weather():
    """More rain in the window must not make water needed sooner."""
    today = SOWING + timedelta(days=20)

    def project(rain):
        days = series(today + timedelta(days=9), lambda i: 6.0, lambda i: rain)
        return advise(WHEAT, SOWING, today, days).next_irrigation_date

    dry_date = project(0.0)
    some_rain = project(3.0)
    assert dry_date is not None
    # Either it is pushed later, or rain removed the need inside the window.
    assert some_rain is None or some_rain >= dry_date


def test_next_irrigation_is_none_when_the_season_is_over():
    today = SOWING + timedelta(days=140)
    advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=5)))
    assert advice.action == "SEASON_OVER"
    assert advice.next_irrigation_date is None
    assert advice.next_irrigation_within_forecast is False


def test_next_irrigation_never_exceeds_the_stress_point_water():
    """The projected amount is capped by what the soil can hold."""
    today = SOWING + timedelta(days=20)
    advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=9)))
    if advice.next_irrigation_date is None:
        pytest.skip("no irrigation projected inside this window")
    assert advice.next_irrigation_mm <= advice.taw_mm + 0.05
    # On the projected day the deficit has just reached the stress point, so
    # the amount to refill it is at least RAW.
    assert advice.next_irrigation_mm >= advice.raw_mm - 0.05


# --- inputs the engine must refuse ----------------------------------------


def test_rejects_future_sowing_date():
    with pytest.raises(EngineInputError):
        advise(WHEAT, SOWING, SOWING - timedelta(days=1), dry(SOWING))


def test_rejects_empty_weather():
    with pytest.raises(EngineInputError):
        advise(WHEAT, SOWING, SOWING, [])


def test_rejects_weather_that_does_not_reach_today():
    with pytest.raises(EngineInputError):
        advise(WHEAT, SOWING, SOWING + timedelta(days=10), dry(SOWING))


# --- the data file itself -------------------------------------------------


def test_crop_lookup_is_case_and_space_insensitive():
    assert get_crop("WHEAT") is WHEAT
    assert get_crop("  rice ") is RICE
    assert get_crop("maize") is None


def test_no_unverifiable_citation_crept_into_the_data_file():
    """Guards the rule that a source is either checkable or labelled ours."""
    allowed = ("FAO-56", "TNAU", "Operational")
    for crop in (WHEAT, RICE):
        for rule in (
            crop.kc_initial,
            crop.kc_mid,
            crop.kc_end,
            crop.root_depth_m,
            crop.depletion_fraction,
            crop.application_efficiency,
        ):
            assert any(a in rule.source for a in allowed), rule
        for window in crop.critical_windows:
            assert any(a in window.source for a in allowed), window


def test_stage_lengths_match_the_tables():
    assert WHEAT.stages.total == 120
    assert (WHEAT.stages.initial, WHEAT.stages.development, WHEAT.stages.mid, WHEAT.stages.late) == (15, 25, 50, 30)
    assert RICE.stages.total == 150
    assert (RICE.stages.initial, RICE.stages.development, RICE.stages.mid, RICE.stages.late) == (30, 30, 60, 30)


# --- soil types -------------------------------------------------------------


@pytest.mark.parametrize(
    "soil_key,expected_mm_per_m,expected_class",
    [
        # (theta_FC - theta_WP) x 1000, from the Table 19 midpoints in the
        # data file: sandy (sandy loam) 0.23-0.11, loam 0.25-0.12, clay 0.36-0.22.
        ("sandy", 120.0, "Sandy loam"),
        ("loam", 130.0, "Loam"),
        ("clay", 140.0, "Clay"),
    ],
)
def test_each_soil_has_its_own_water_capacity(soil_key, expected_mm_per_m, expected_class):
    soil = crop_rules.get_soil(soil_key)
    assert soil.available_water_mm_per_m == expected_mm_per_m
    assert soil.fao_class == expected_class
    # Every soil value cites FAO-56 Table 19, not an operational guess.
    assert "Table 19" in soil.field_capacity.source
    assert "Table 19" in soil.wilting_point.source


@pytest.mark.parametrize("soil_key", ["sandy", "loam", "clay"])
def test_soil_changes_taw_but_not_the_rule(soil_key):
    """TAW must follow the soil; the stress rule itself must not move."""
    today = SOWING + timedelta(days=30)
    soil = crop_rules.get_soil(soil_key)
    advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=7)), soil=soil)

    expected_taw = soil.available_water_mm_per_m * WHEAT.root_depth_m.value
    assert advice.taw_mm == pytest.approx(expected_taw, abs=0.15)
    # RAW is still p x TAW for the crop, whatever the soil.
    assert advice.raw_mm == pytest.approx(
        expected_taw * WHEAT.depletion_fraction.value, abs=0.15
    )
    assert advice.soil_key == soil_key
    assert advice.soil_is_default is False


def test_sandy_soil_stresses_sooner_than_clay():
    """The point of the input: less stored water means stress is reached earlier.

    Asserted as "which day first triggers", not "whether it ever does": given a
    long enough dry spell, every soil eventually runs out of water, so a test
    that froze one soil at SOIL_MOISTURE_OK would only be measuring how long the
    spell was.
    """

    def first_irrigation_day(soil):
        for age in range(1, 60):
            today = SOWING + timedelta(days=age)
            advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=3)), soil=soil)
            if advice.action == "IRRIGATE_TODAY":
                return age
        return None

    sandy_day = first_irrigation_day(crop_rules.SANDY)
    loam_day = first_irrigation_day(crop_rules.LOAM)
    clay_day = first_irrigation_day(crop_rules.CLAY)

    assert sandy_day is not None and clay_day is not None
    assert sandy_day < loam_day < clay_day, (sandy_day, loam_day, clay_day)

    # And on the day sandy first needs water, clay is still comfortable.
    today = SOWING + timedelta(days=sandy_day)
    days = dry(today + timedelta(days=3))
    assert advise(WHEAT, SOWING, today, days, soil=crop_rules.SANDY).action == "IRRIGATE_TODAY"
    assert advise(WHEAT, SOWING, today, days, soil=crop_rules.CLAY).action == "SOIL_MOISTURE_OK"


def test_unset_soil_falls_back_to_loam_and_says_so():
    today = SOWING + timedelta(days=30)
    advice = advise(WHEAT, SOWING, today, dry(today + timedelta(days=7)))

    assert advice.soil_key == "loam"
    assert advice.soil_is_default is True
    joined = " ".join(advice.assumptions)
    assert "नहीं चुना गया" in joined  # says the soil was assumed


def test_chosen_soil_does_not_claim_it_was_assumed():
    today = SOWING + timedelta(days=30)
    advice = advise(
        WHEAT, SOWING, today, dry(today + timedelta(days=7)), soil=crop_rules.CLAY
    )
    joined = " ".join(advice.assumptions)
    assert "नहीं चुना गया" not in joined
    assert "चिकनी" in joined


@pytest.mark.parametrize("key,expected", [("SANDY", "sandy"), (" clay ", "clay"), ("loam", "loam")])
def test_soil_lookup_normalises_case_and_space(key, expected):
    assert crop_rules.get_soil(key).key == expected


def test_unknown_soil_falls_back_to_loam():
    assert crop_rules.get_soil("peat").key == "loam"
    assert crop_rules.get_soil(None).key == "loam"
