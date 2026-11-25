"""Tests for the Hindi and English narration layer.

The narration cannot be wrong about the number, because it is handed one. These
tests assert exactly that: both languages quote the same figure, every action
has wording, and the two opposite decisions can never share a sentence.
"""

from datetime import date, timedelta

import pytest

from app.data.crop_rules import CLAY, RICE, SANDY, WHEAT
from app.services.irrigation import EngineDay, advise
from app.services.narration import (
    ACTION_IRRIGATE,
    ACTION_OK,
    ACTION_OVER,
    ACTION_WAIT_RAIN,
    format_indian,
    headline,
    irrigation_line,
    narrate,
    next_irrigation_line,
    soil_line,
    usual_interval_line,
)

SOWING = date(2026, 11, 1)


@pytest.mark.parametrize(
    "number,expected",
    [
        (0, "0"),
        (7, "7"),
        (999, "999"),
        (1000, "1,000"),
        (100000, "1,00,000"),
        (130000, "1,30,000"),
        (689701, "6,89,701"),
        (12345678, "1,23,45,678"),
    ],
)
def test_indian_digit_grouping(number, expected):
    assert format_indian(number) == expected


def _advice(crop, days_after_sowing, et0, rain_for_day=0.0, rain_all=None):
    today = SOWING + timedelta(days=days_after_sowing)
    upto = today + timedelta(days=6)
    count = (upto - SOWING).days + 1
    days = []
    for i in range(count):
        rain = rain_all if rain_all is not None else (rain_for_day if i == days_after_sowing else 0.0)
        days.append(EngineDay(SOWING + timedelta(days=i), et0, rain, 5.0))
    return advise(crop, SOWING, today, days)


def test_every_action_narrates_in_both_languages():
    cases = [
        _advice(WHEAT, 30, 5.0),               # irrigate
        _advice(WHEAT, 30, 5.0, rain_for_day=25.0),  # wait for rain
        _advice(RICE, 2, 2.0, rain_all=6.0),   # soil moisture fine
        _advice(WHEAT, 140, 3.0),              # season over
    ]
    for advice in cases:
        hindi, english = narrate(advice)
        assert hindi.strip()
        assert english.strip()
        # Devanagari in the Hindi, Latin in the English: not swapped.
        assert any("\u0900" <= ch <= "\u097F" for ch in hindi), advice.action
        assert hindi != english


def test_both_languages_quote_the_same_litre_figure():
    advice = _advice(WHEAT, 30, 5.0)
    assert advice.action == ACTION_IRRIGATE
    hindi, english = narrate(advice)
    figure = format_indian(advice.litres_per_acre)
    assert figure in hindi
    assert figure in english


def test_opposite_actions_never_share_wording():
    irrigate = narrate(_advice(WHEAT, 30, 5.0))
    wait = narrate(_advice(WHEAT, 30, 5.0, rain_for_day=25.0))
    assert irrigate[0] != wait[0]
    assert irrigate[1] != wait[1]
    # The wait wording must not tell the farmer to irrigate today.
    assert "करें" not in wait[0].split("।")[0] or "न करें" in wait[0]


def test_headlines_differ_per_action():
    actions = [
        _advice(WHEAT, 30, 5.0),
        _advice(WHEAT, 30, 5.0, rain_for_day=25.0),
        _advice(RICE, 2, 2.0, rain_all=6.0),
        _advice(WHEAT, 140, 3.0),
    ]
    expected = {ACTION_IRRIGATE, ACTION_WAIT_RAIN, ACTION_OK, ACTION_OVER}
    assert {a.action for a in actions} == expected
    headlines = [headline(a) for a in actions]
    assert len({h[0] for h in headlines}) == 4
    assert len({h[1] for h in headlines}) == 4


@pytest.mark.parametrize(
    "soil,expected_hi,expected_en",
    [
        (SANDY, "रेतीली", "Sandy"),
        (CLAY, "चिकनी", "Clay"),
    ],
)
def test_soil_line_names_the_chosen_soil_in_both_languages(soil, expected_hi, expected_en):
    today = SOWING + timedelta(days=30)
    days = [
        EngineDay(SOWING + timedelta(days=i), 5.0, 0.0, 5.0)
        for i in range((today + timedelta(days=3) - SOWING).days + 1)
    ]
    advice = advise(WHEAT, SOWING, today, days, soil=soil)

    hindi, english = soil_line(advice)
    assert expected_hi in hindi
    assert expected_en in english
    assert any("\u0900" <= ch <= "\u097F" for ch in hindi)
    assert hindi != english


def test_soil_line_says_when_loam_was_assumed():
    advice = _advice(WHEAT, 30, 5.0)
    assert advice.soil_is_default
    hindi, english = soil_line(advice)
    assert "दोमट" in hindi
    assert "loam" in english.lower()
    assert "नहीं चुनी" in hindi
    assert "assumed" in english.lower()


def test_irrigation_line_reports_the_amount_and_what_was_held():
    today = SOWING + timedelta(days=30)
    days = [
        EngineDay(SOWING + timedelta(days=i), 5.0, 0.0, 5.0)
        for i in range((today + timedelta(days=3) - SOWING).days + 1)
    ]
    advice = advise(
        WHEAT,
        SOWING,
        today,
        days,
        last_irrigation_date=today - timedelta(days=2),
        last_irrigation_mm=500.0,
    )

    hindi, english = irrigation_line(advice)
    assert "500" in hindi and "500" in english
    # Both languages must disclose the loss, not just the happy half.
    assert "बह गया" in hindi
    assert "drained" in english
    assert any("\u0900" <= ch <= "\u097F" for ch in hindi)


def test_irrigation_line_omits_loss_when_the_soil_held_it_all():
    today = SOWING + timedelta(days=30)
    days = [
        EngineDay(SOWING + timedelta(days=i), 5.0, 0.0, 5.0)
        for i in range((today + timedelta(days=3) - SOWING).days + 1)
    ]
    advice = advise(
        WHEAT,
        SOWING,
        today,
        days,
        last_irrigation_date=today - timedelta(days=2),
        last_irrigation_mm=10.0,
    )
    hindi, english = irrigation_line(advice)
    assert "बह गया" not in hindi
    assert "drained" not in english


def test_irrigation_line_has_a_no_irrigation_case():
    advice = _advice(WHEAT, 30, 5.0)
    hindi, english = irrigation_line(advice)
    assert "सिंचाई नहीं हुई" in hindi
    assert "no irrigation" in english


def test_next_irrigation_line_gives_a_date_within_the_window():
    today = SOWING + timedelta(days=20)
    # Mild but drying weather, chosen so the crop is not yet stressed and the
    # projection lands on a future day rather than today.
    days = [
        EngineDay(SOWING + timedelta(days=i), 4.0, 0.0, 5.0)
        for i in range((today + timedelta(days=12) - SOWING).days + 1)
    ]
    advice = advise(WHEAT, SOWING, today, days)
    assert advice.next_irrigation_date is not None
    assert advice.next_irrigation_date > today

    hindi, english = next_irrigation_line(advice)
    stamp = advice.next_irrigation_date.strftime("%d-%m-%Y")
    assert stamp in hindi and stamp in english
    assert any("\u0900" <= ch <= "\u097F" for ch in hindi)


def test_next_irrigation_line_says_absent_and_never_extrapolates():
    today = SOWING + timedelta(days=20)
    days = [
        EngineDay(SOWING + timedelta(days=i), 5.0, 10.0, 5.0)
        for i in range((today + timedelta(days=5) - SOWING).days + 1)
    ]
    advice = advise(WHEAT, SOWING, today, days)
    assert advice.next_irrigation_date is None

    hindi, english = next_irrigation_line(advice)
    assert "नहीं दिख रही" in hindi
    assert "not" in english.lower() or "no irrigation" in english.lower()
    # Both must say the window is where the claim stops.
    assert "आगे" in hindi
    assert "beyond" in english.lower()


def test_next_irrigation_line_handles_today_and_season_over():
    # Already stressed.
    today = SOWING + timedelta(days=30)
    stressed = advise(WHEAT, SOWING, today, _dry_days(today, 7))
    hindi, english = next_irrigation_line(stressed)
    assert "आज" in hindi
    assert "today" in english.lower()

    # Season over.
    late = SOWING + timedelta(days=140)
    over = advise(WHEAT, SOWING, late, _dry_days(late, 5))
    hindi2, english2 = next_irrigation_line(over)
    assert "अवधि पूरी" in hindi2
    assert "season is over" in english2.lower()


def _dry_days(today, span):
    return [
        EngineDay(SOWING + timedelta(days=i), 5.0, 0.0, 5.0)
        for i in range((today + timedelta(days=span) - SOWING).days + 1)
    ]


def test_usual_interval_line_is_absent_when_no_habit_was_given():
    advice = _advice(WHEAT, 20, 4.0)
    assert advice.usual_interval_days is None
    assert usual_interval_line(advice) is None


@pytest.mark.parametrize(
    "usual,gap_relation",
    [(1, "later"), (60, "sooner")],
)
def test_usual_interval_line_compares_both_ways(usual, gap_relation):
    today = SOWING + timedelta(days=20)
    days = [
        EngineDay(SOWING + timedelta(days=i), 4.0, 0.0, 5.0)
        for i in range((today + timedelta(days=12) - SOWING).days + 1)
    ]
    advice = advise(WHEAT, SOWING, today, days, usual_interval_days=usual)
    assert advice.next_irrigation_date is not None

    line = usual_interval_line(advice)
    assert line is not None
    hindi, english = line
    assert str(usual) in hindi and str(usual) in english
    assert any("\u0900" <= ch <= "\u097F" for ch in hindi)
    if gap_relation == "later":
        assert "रुकना" in hindi
        assert "longer" in english
    else:
        assert "जल्दी" in hindi
        assert "sooner" in english


def test_usual_interval_line_agrees_when_the_gap_matches():
    today = SOWING + timedelta(days=20)
    days = [
        EngineDay(SOWING + timedelta(days=i), 4.0, 0.0, 5.0)
        for i in range((today + timedelta(days=12) - SOWING).days + 1)
    ]
    probe = advise(WHEAT, SOWING, today, days)
    assert probe.next_irrigation_date is not None
    gap = (probe.next_irrigation_date - today).days

    advice = advise(WHEAT, SOWING, today, days, usual_interval_days=gap)
    hindi, english = usual_interval_line(advice)
    assert "मेल खाते" in hindi
    assert "agree" in english.lower()


def test_critical_window_is_mentioned_when_active():
    advice = _advice(WHEAT, 17, 4.0)  # crown root initiation, 15-20 DAS
    assert advice.in_critical_window
    hindi, english = narrate(advice)
    assert "crown root initiation" in english
    assert advice.critical_window_label in hindi
