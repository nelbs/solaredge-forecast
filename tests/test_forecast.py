"""Golden results for the preserved monthly historical forecast calculation."""

from calendar import monthrange
from datetime import date

import pytest

from custom_components.solaredge_forecast import _active_forecast_period
from custom_components.solaredge_forecast.solaredgeforecast import (
    SolaredgeForecast,
    _monthly_daily_averages,
)


def constant_history(daily_kwh=10):
    return {
        "energy": {
            "values": [
                {
                    "date": date(year, month, 1).isoformat(),
                    "value": daily_kwh * 1000 * monthrange(year, month)[1],
                }
                for year in (2023, 2024)
                for month in range(1, 13)
            ]
        }
    }


def test_measured_plus_remaining_history_golden():
    result = SolaredgeForecast(
        "20260101",
        "20261231",
        "01012023",
        123,
        constant_history(),
        1900,
        4,
        date(2026, 7, 1),
    )
    assert result.solaredge_produced == 1900
    assert result.solaredge_estimated == 1836
    assert result.solaredge_forecast == 3736
    assert result.solaredge_progress == 86
    assert result.startdate_production == date(2023, 1, 1)


def test_today_above_baseline_does_not_make_remaining_negative():
    result = SolaredgeForecast(
        "20260101",
        "20261231",
        "01012023",
        123,
        constant_history(),
        3800,
        20,
        date(2026, 12, 31),
    )
    assert result.solaredge_estimated == 0
    assert result.solaredge_forecast == 3800
    assert result.solaredge_progress == 150


def test_leap_year_and_null_zero_history_semantics():
    history = constant_history()
    history["energy"]["values"].extend(
        [
            {"date": "2025-02-01", "value": 0},
            {"date": "2022-02-01", "value": None},
        ]
    )
    assert _monthly_daily_averages(history)[2] == 10


def test_missing_calendar_month_is_explicit():
    history = constant_history()
    history["energy"]["values"] = [
        item for item in history["energy"]["values"] if "-12-" not in item["date"]
    ]
    with pytest.raises(ValueError, match="December"):
        SolaredgeForecast(
            "20260101",
            "20261231",
            "01012023",
            123,
            history,
            1900,
            4,
            date(2026, 7, 1),
        )


def test_calendar_and_cross_year_rollover():
    assert _active_forecast_period(1, "January", 31, "December", date(2027, 1, 1)) == (
        date(2027, 1, 1),
        date(2027, 12, 31),
    )
    assert _active_forecast_period(1, "July", 30, "June", date(2026, 11, 8)) == (
        date(2026, 7, 1),
        date(2027, 6, 30),
    )


def test_variable_monthly_history_matches_original_v1_golden():
    history = {
        "energy": {
            "values": [
                {
                    "date": date(year, month, 1).isoformat(),
                    "value": 1000
                    * month
                    * monthrange(year, month)[1]
                    * (1 if year == 2023 else 1.2),
                }
                for year in (2023, 2024)
                for month in range(1, 13)
            ]
        }
    }
    result = SolaredgeForecast(
        "20260101",
        "20261231",
        "01012023",
        123,
        history,
        2000,
        9,
        date(2026, 11, 8),
    )
    assert result.solaredge_produced == 2000
    assert result.solaredge_estimated == 625
    assert result.solaredge_forecast == 2625
    assert result.solaredge_progress == 9
