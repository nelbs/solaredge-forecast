"""Create a SolarEdge production forecast."""

from __future__ import annotations

from calendar import month_name, monthrange
from datetime import date, datetime, timedelta
from typing import Any

import solaredge

DATE_FORMAT = "%Y%m%d"
PRODUCTION_DATE_FORMAT = "%d%m%Y"
WH_PER_KWH = 1000


class SolaredgeForecast:
    """SolarEdge forecast data."""

    def __init__(
        self,
        startdate: str,
        enddate: str,
        startdate_production: str,
        site_id: int,
        account_key: str,
    ) -> None:
        """Initialize forecast data."""
        self.startdate = datetime.strptime(startdate, DATE_FORMAT).date()
        self.enddate = datetime.strptime(enddate, DATE_FORMAT).date()
        self.site_id = site_id
        self.account_key = account_key
        self.startdate_production = _production_start_date(startdate_production)

        data = self.get_solar_forecast()

        self.solaredge_estimated = data["Solar energy estimated"]
        self.solaredge_produced = data["Solar energy produced"]
        self.solaredge_forecast = data["Solar energy forecast"]
        self.solaredge_progress = data["Solar energy progress"]

    def get_solar_forecast(self) -> dict[str, int]:
        """Calculate solar energy forecast."""
        now = datetime.now()
        yesterday = now.date() - timedelta(days=1)
        today = now.date()
        tomorrow = now.date() + timedelta(days=1)
        last_month = today.replace(day=1) - timedelta(days=1)

        client = solaredge.Solaredge(self.account_key)

        if self.startdate_production is None:
            data_period = client.get_data_period(site_id=self.site_id)
            start_production = data_period["dataPeriod"]["startDate"]
            self.startdate_production = _first_day_next_month(
                _parse_api_date(start_production)
            )

        if self.startdate_production > last_month:
            raise ValueError(
                "At least one complete month of production history is required"
            )

        energy_month_average = client.get_energy(
            site_id=self.site_id,
            start_date=self.startdate_production,
            end_date=last_month,
            time_unit="MONTH",
        )
        averages = _monthly_daily_averages(energy_month_average)
        interpolation_points = _interpolation_points(
            averages,
            _add_months(self.startdate, -1),
            _add_months(self.enddate, 1),
        )

        energy_estimated_from_tomorrow = _sum_daily_energy(
            tomorrow, self.enddate, interpolation_points
        )
        energy_estimated_until_yesterday = _sum_daily_energy(
            self.startdate, yesterday, interpolation_points
        )
        energy_estimated_today = _sum_daily_energy(today, today, interpolation_points)

        energy_production_until_now = _time_frame_energy_kwh(
            client,
            site_id=self.site_id,
            start_date=self.startdate,
            end_date=tomorrow,
            time_unit="YEAR",
        )
        energy_produced_today = _time_frame_energy_kwh(
            client,
            site_id=self.site_id,
            start_date=today,
            end_date=tomorrow,
            time_unit="DAY",
        )

        energy_estimated_period = energy_estimated_from_tomorrow + max(
            0, energy_estimated_today - energy_produced_today
        )

        energy_produced_until_yesterday = (
            energy_production_until_now - energy_produced_today
        )

        energy_production_progress = (
            energy_produced_until_yesterday
            - energy_estimated_until_yesterday
            + max(0, energy_produced_today - energy_estimated_today)
        )

        forecast = energy_estimated_period + energy_production_until_now

        return {
            "Solar energy produced": round(energy_production_until_now),
            "Solar energy estimated": round(energy_estimated_period),
            "Solar energy forecast": round(forecast),
            "Solar energy progress": round(energy_production_progress),
        }


def _production_start_date(value: str) -> date | None:
    """Return the first complete production month from a user supplied date."""
    if not value:
        return None

    parsed = datetime.strptime(value, PRODUCTION_DATE_FORMAT).date()
    if parsed.day > 1:
        return _first_day_next_month(parsed)
    return parsed


def _parse_api_date(value: Any) -> date:
    """Parse a date returned by the SolarEdge API."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value).split()[0], "%Y-%m-%d").date()


def _first_day_next_month(value: date) -> date:
    """Return the first day of the month after value."""
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def _add_months(value: date, months: int) -> date:
    """Add months while keeping the date valid."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _date_range(start_date: date, end_date: date):
    """Yield every date in an inclusive range."""
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _monthly_daily_averages(payload: dict[str, Any]) -> dict[int, float]:
    """Return average daily kWh per calendar month from SolarEdge data."""
    monthly_values: dict[int, list[float]] = {}
    values = payload.get("energy", {}).get("values", [])

    for item in values:
        energy = item.get("value") or 0
        if energy == 0:
            continue

        item_date = _parse_api_date(item["date"])
        days_in_month = monthrange(item_date.year, item_date.month)[1]
        monthly_values.setdefault(item_date.month, []).append(
            energy / days_in_month / WH_PER_KWH
        )

    if not monthly_values:
        raise ValueError("SolarEdge returned no historical monthly production data")

    return {
        month: sum(values) / len(values)
        for month, values in monthly_values.items()
        if values
    }


def _interpolation_points(
    averages: dict[int, float], start_date: date, end_date: date
) -> list[tuple[date, float]]:
    """Return monthly interpolation points on the 15th day of each month."""
    points: list[tuple[date, float]] = []
    missing_months: set[int] = set()

    for current in _date_range(start_date, end_date):
        if current.day != 15:
            continue
        if current.month not in averages:
            missing_months.add(current.month)
            continue
        points.append((current, averages[current.month]))

    if missing_months:
        missing = ", ".join(month_name[month] for month in sorted(missing_months))
        raise ValueError(f"Missing historical production data for: {missing}")
    if not points:
        raise ValueError("No monthly production data available for interpolation")

    return points


def _interpolated_daily_energy(day: date, points: list[tuple[date, float]]) -> float:
    """Return the interpolated daily energy for a date."""
    if day <= points[0][0]:
        return points[0][1]
    if day >= points[-1][0]:
        return points[-1][1]

    previous_point = points[0]
    for next_point in points[1:]:
        previous_date, previous_value = previous_point
        next_date, next_value = next_point
        if previous_date <= day <= next_date:
            span_days = (next_date - previous_date).days
            elapsed_days = (day - previous_date).days
            fraction = elapsed_days / span_days
            return previous_value + (next_value - previous_value) * fraction
        previous_point = next_point

    return points[-1][1]


def _sum_daily_energy(
    start_date: date, end_date: date, points: list[tuple[date, float]]
) -> float:
    """Sum interpolated daily energy over an inclusive date range."""
    if start_date > end_date:
        return 0
    return sum(
        _interpolated_daily_energy(day, points)
        for day in _date_range(start_date, end_date)
    )


def _time_frame_energy_kwh(
    client,
    site_id: int,
    start_date: date,
    end_date: date,
    time_unit: str,
) -> float:
    """Return SolarEdge time frame energy in kWh."""
    payload = client.get_time_frame_energy(
        site_id=site_id,
        start_date=start_date,
        end_date=end_date,
        time_unit=time_unit,
    )
    energy = payload.get("timeFrameEnergy", {}).get("energy") or 0
    return energy / WH_PER_KWH
