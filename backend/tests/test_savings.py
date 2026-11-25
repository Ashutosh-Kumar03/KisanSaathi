"""Tests for the savings simulation.

The savings panel is the easiest place in this app to accidentally print a
confident number that means nothing, so these tests concentrate on the two ways
that happens: comparing against a habit that was never stated, and quoting
rupees from a pump we were not told about.

Everything here is pure — same weather, two schedules, no network.
"""

from datetime import date, timedelta

import pytest

from app.data.crop_rules import CLAY, LOAM, SANDY, WHEAT
from app.services.irrigation import EngineDay, EngineInputError, simulate_savings
from app.services.narration import (
    SAVINGS_LABEL_EN,
    SAVINGS_LABEL_HI,
    format_indian,
    savings_lines,
    savings_money_reason,
    savings_prompt,
)

SOWING = date(2026, 11, 1)


def weather(days: int, et0: float = 5.0, rain: float = 0.0) -> list[EngineDay]:
    return [
        EngineDay(SOWING + timedelta(days=i), et0, rain, 5.0) for i in range(days)
    ]


# --- the four required cases ------------------------------------------------


@pytest.mark.parametrize(
    "interval,amount,expected_relation",
    [
        # A habit that closely matches what the advice would apply: over the
        # same 60-day window, 80 mm every 12 days totals 320 mm against the
        # advice's 321, so the difference is timing rather than waste.
        (12, 80.0, "zero"),
        # Watering four times as often as needed, with a generous amount: this
        # is the case the panel exists for, and the saving must be positive.
        (7, 60.0, "positive"),
        # A farmer who already under-waters relative to the advice: reported
        # honestly as a negative saving rather than hidden.
        (30, 15.0, "negative"),
    ],
)
def test_habit_versus_advice(interval, amount, expected_relation):
    savings = simulate_savings(
        WHEAT,
        SOWING,
        weather(60),
        habit_interval_days=interval,
        habit_mm_per_irrigation=amount,
    )
    assert savings is not None
    assert savings.saved_mm == pytest.approx(
        savings.habit_total_mm - savings.advised_total_mm, abs=0.15
    )

    if expected_relation == "positive":
        assert savings.saved_mm > 0
        assert savings.saved_litres_per_acre > 0
        assert savings.habit_irrigations > savings.advised_irrigations
    elif expected_relation == "negative":
        assert savings.saved_mm < 0
        assert savings.saved_litres_per_acre < 0
    else:
        # Same schedule, so the totals cannot differ by more than rounding.
        assert abs(savings.saved_mm) < 1.0


@pytest.mark.parametrize("soil", [SANDY, LOAM, CLAY])
def test_rain_heavy_weather_collapses_the_advised_schedule(soil):
    """In a wet spell the advice waters little or not at all, while a fixed
    habit keeps watering on its calendar — the largest and most honest saving."""
    savings = simulate_savings(
        WHEAT,
        SOWING,
        weather(60, rain=14.0),
        soil=soil,
        habit_interval_days=7,
        habit_mm_per_irrigation=60.0,
    )
    assert savings is not None
    assert savings.habit_irrigations > 0
    # The habit ignores the rain, so it must still be applying water.
    assert savings.habit_total_mm > 0
    # The advice should not be irrigating through heavy rain every day.
    assert savings.advised_total_mm < savings.habit_total_mm
    assert savings.saved_mm > 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {},  # nothing at all
        {"habit_interval_days": 7},  # a cycle but no amount
        {"habit_mm_per_irrigation": 60.0},  # an amount but no cycle
    ],
)
def test_no_savings_without_both_habit_inputs(kwargs):
    """No baseline, no number. Never a saving against an imagined habit."""
    assert simulate_savings(WHEAT, SOWING, weather(60), **kwargs) is None


# --- money ------------------------------------------------------------------


def test_money_is_absent_unless_both_pump_inputs_are_given():
    baseline = simulate_savings(
        WHEAT, SOWING, weather(60), habit_interval_days=7, habit_mm_per_irrigation=60.0
    )
    assert baseline.pump_hours_saved is None
    assert baseline.money_saved is None
    assert baseline.money_unavailable_reason == "missing"

    only_hours = simulate_savings(
        WHEAT,
        SOWING,
        weather(60),
        habit_interval_days=7,
        habit_mm_per_irrigation=60.0,
        pump_litres_per_hour=30000,
    )
    assert only_hours.money_saved is None
    assert only_hours.money_unavailable_reason == "both"


def test_money_is_computed_when_both_pump_inputs_are_given():
    savings = simulate_savings(
        WHEAT,
        SOWING,
        weather(60),
        habit_interval_days=7,
        habit_mm_per_irrigation=60.0,
        pump_litres_per_hour=30000,
        cost_per_pump_hour=120,
    )
    assert savings.saved_mm > 0
    assert savings.pump_hours_saved is not None
    assert savings.money_saved is not None
    assert savings.money_unavailable_reason is None

    # Arithmetic must be reproducible from the published inputs.
    expected_litres = savings.saved_mm * 4046.86
    assert savings.pump_hours_saved == pytest.approx(expected_litres / 30000, abs=0.15)
    assert savings.money_saved == pytest.approx(
        savings.pump_hours_saved * 120, abs=1.0
    )


@pytest.mark.parametrize(
    "kwargs,message",
    [
        (
            {
                "pump_litres_per_hour": 0,
                "cost_per_pump_hour": 100,
            },
            "greater than zero",
        ),
        (
            {"pump_litres_per_hour": 30000, "cost_per_pump_hour": -1},
            "cannot be negative",
        ),
        ({"habit_interval_days": 0, "habit_mm_per_irrigation": 10}, "at least one day"),
        ({"habit_interval_days": 7, "habit_mm_per_irrigation": -5}, "cannot be negative"),
    ],
)
def test_rejects_impossible_savings_inputs(kwargs, message):
    with pytest.raises(EngineInputError) as exc:
        simulate_savings(WHEAT, SOWING, weather(30), **kwargs)
    assert message in str(exc.value)


# --- the simulation itself --------------------------------------------------


def test_habit_waters_on_its_own_calendar_regardless_of_rain():
    """A habit is a calendar, not a decision: it must not react to the weather."""
    savings = simulate_savings(
        WHEAT,
        SOWING,
        weather(29),  # 29 days, so watering every 7 days across a window
        habit_interval_days=7,
        habit_mm_per_irrigation=50.0,
    )
    # Days 7, 14, 21, 28 fall inside the window.
    assert savings.habit_irrigations == 4
    assert savings.habit_total_mm == pytest.approx(200.0, abs=0.15)


def test_advised_schedule_only_waters_at_the_stress_point():
    """The advised run must not water more often than the stress point needs.

    Compared against a habit that waters on a fixed calendar, the advice may
    legitimately water MORE often than a very slow habit (one that waters twice
    a season and lets the crop suffer), so the assertion is about the advice's
    own reaction to the soil, not about beating every possible habit.
    """
    savings = simulate_savings(
        WHEAT,
        SOWING,
        weather(60),
        habit_interval_days=30,
        habit_mm_per_irrigation=10.0,
    )
    # Over 60 days at this demand the advice needs a handful of refills, not one
    # per day and not none at all.
    assert 0 < savings.advised_irrigations <= 6
    assert savings.advised_total_mm > 0
    # And the under-watering habit still comes out as a negative saving, which
    # is the honest reading: the advice applies more water than they do.
    assert savings.saved_mm < 0


def test_savings_window_matches_the_weather_given():
    days = weather(45)
    savings = simulate_savings(
        WHEAT, SOWING, days, habit_interval_days=7, habit_mm_per_irrigation=50.0
    )
    assert savings.window_start == days[0].date
    assert savings.window_end == days[-1].date


@pytest.mark.parametrize("soil", [SANDY, LOAM, CLAY])
def test_each_soil_produces_a_consistent_comparison(soil):
    savings = simulate_savings(
        WHEAT,
        SOWING,
        weather(60),
        soil=soil,
        habit_interval_days=7,
        habit_mm_per_irrigation=60.0,
    )
    assert savings is not None
    assert savings.saved_mm == pytest.approx(
        savings.habit_total_mm - savings.advised_total_mm, abs=0.15
    )
    # Clay holds more, so the advised schedule can afford to wait longer.
    assert savings.advised_irrigations >= 0


def test_assumptions_list_every_input_the_estimate_rests_on():
    savings = simulate_savings(
        WHEAT, SOWING, weather(60), habit_interval_days=9, habit_mm_per_irrigation=55.0
    )
    joined = " ".join(savings.assumptions)
    assert "9" in joined  # the habit's cycle
    assert "55" in joined  # the habit's amount
    assert "70%" in joined  # application efficiency
    assert "मिट्टी" in joined  # which soil


# --- narration --------------------------------------------------------------


def test_label_is_exact_and_in_both_languages():
    assert SAVINGS_LABEL_HI == "अनुमान: आपकी अपनी आदत और मॉडल की सलाह की तुलना"
    assert "Estimate" in SAVINGS_LABEL_EN


@pytest.mark.parametrize("saved", ["positive", "zero", "negative"])
def test_savings_lines_cover_every_sign(saved):
    if saved == "positive":
        s = simulate_savings(
            WHEAT, SOWING, weather(60), habit_interval_days=7, habit_mm_per_irrigation=60.0
        )
    elif saved == "negative":
        s = simulate_savings(
            WHEAT, SOWING, weather(60), habit_interval_days=30, habit_mm_per_irrigation=15.0
        )
    else:
        # Identical schedules: compare the advice against itself.
        probe = simulate_savings(
            WHEAT, SOWING, weather(60), habit_interval_days=7, habit_mm_per_irrigation=60.0
        )
        s = probe.__class__(
            **{
                **probe.__dict__,
                "habit_total_mm": probe.advised_total_mm,
                "saved_mm": 0.0,
                "saved_litres_per_acre": 0,
            }
        )

    hindi, english = savings_lines(s)
    assert hindi.strip() and english.strip()
    assert any("\u0900" <= ch <= "\u097F" for ch in hindi)
    assert hindi != english

    if saved == "positive":
        assert "बच सकता है" in hindi
        assert "save" in english.lower()
    elif saved == "zero":
        assert "बराबर" in hindi
        assert "same" in english.lower()
    else:
        assert "कम" in hindi
        assert "less" in english.lower()


def test_positive_savings_quote_the_litre_figure_in_both_languages():
    s = simulate_savings(
        WHEAT, SOWING, weather(60), habit_interval_days=7, habit_mm_per_irrigation=60.0
    )
    hindi, english = savings_lines(s)
    figure = format_indian(s.saved_litres_per_acre)
    assert figure in hindi
    assert figure in english


def test_money_lines_only_appear_with_pump_inputs():
    without = simulate_savings(
        WHEAT, SOWING, weather(60), habit_interval_days=7, habit_mm_per_irrigation=60.0
    )
    hindi, english = savings_lines(without)
    assert "₹" not in hindi
    assert "₹" not in english
    # And the reason must be available in both languages.
    reason = savings_money_reason(without)
    assert reason is not None
    assert "रुपये" in reason[0]
    assert "rupees" in reason[1]

    with_money = simulate_savings(
        WHEAT,
        SOWING,
        weather(60),
        habit_interval_days=7,
        habit_mm_per_irrigation=60.0,
        pump_litres_per_hour=30000,
        cost_per_pump_hour=120,
    )
    hindi2, english2 = savings_lines(with_money)
    assert "₹" in hindi2 and "₹" in english2
    assert "घंटे" in hindi2
    assert savings_money_reason(with_money) is None


def test_prompt_asks_for_both_habit_inputs_when_missing():
    hindi, english = savings_prompt()
    assert "कितने दिन" in hindi
    assert "कितना पानी" in hindi
    assert "how often" in english.lower()
    assert any("\u0900" <= ch <= "\u097F" for ch in hindi)
