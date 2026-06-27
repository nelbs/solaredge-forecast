"""SolarEdge Forecast integration."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ACCOUNT_KEY,
    CONF_ENDDAY,
    CONF_ENDMONTH,
    CONF_SITE_ID,
    CONF_STARTDATE_PRODUCTION,
    CONF_STARTDAY,
    CONF_STARTMONTH,
    DEFAULT_ACCOUNT_KEY,
    DEFAULT_ENDDAY,
    DEFAULT_ENDMONTH,
    DEFAULT_SITE_ID,
    DEFAULT_STARTDATE_PRODUCTION,
    DEFAULT_STARTDAY,
    DEFAULT_STARTMONTH,
    DOMAIN,
    MONTHS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]
UPDATE_INTERVAL = timedelta(minutes=15)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry for SolarEdge Forecast."""
    try:
        coordinator = SolaredgeForecastData(hass, entry)
    except ValueError as err:
        raise ConfigEntryError(str(err)) from err

    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration after options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


def _entry_settings(entry: ConfigEntry) -> dict[str, Any]:
    """Return settings for an entry, supporting legacy option-only entries."""
    return {
        CONF_SITE_ID: entry.options.get(
            CONF_SITE_ID, entry.data.get(CONF_SITE_ID, DEFAULT_SITE_ID)
        ),
        CONF_ACCOUNT_KEY: entry.options.get(
            CONF_ACCOUNT_KEY, entry.data.get(CONF_ACCOUNT_KEY, DEFAULT_ACCOUNT_KEY)
        ),
        CONF_STARTDAY: entry.options.get(
            CONF_STARTDAY, entry.data.get(CONF_STARTDAY, DEFAULT_STARTDAY)
        ),
        CONF_STARTMONTH: entry.options.get(
            CONF_STARTMONTH, entry.data.get(CONF_STARTMONTH, DEFAULT_STARTMONTH)
        ),
        CONF_ENDDAY: entry.options.get(
            CONF_ENDDAY, entry.data.get(CONF_ENDDAY, DEFAULT_ENDDAY)
        ),
        CONF_ENDMONTH: entry.options.get(
            CONF_ENDMONTH, entry.data.get(CONF_ENDMONTH, DEFAULT_ENDMONTH)
        ),
        CONF_STARTDATE_PRODUCTION: entry.options.get(
            CONF_STARTDATE_PRODUCTION,
            entry.data.get(CONF_STARTDATE_PRODUCTION, DEFAULT_STARTDATE_PRODUCTION),
        ),
    }


def _month_number(month: str) -> int:
    """Return the month number for an English month name."""
    return MONTHS.index(month) + 1


def _build_date(year: int, month: str, day: int) -> date:
    """Build a date from a year, English month name, and day."""
    month_number = _month_number(month)
    return date(year, month_number, min(int(day), monthrange(year, month_number)[1]))


def _active_forecast_period(
    start_day: int,
    start_month: str,
    end_day: int,
    end_month: str,
    today: date,
) -> tuple[date, date]:
    """Return the active forecast period around today."""
    start_this_year = _build_date(today.year, start_month, start_day)
    end_this_year = _build_date(today.year, end_month, end_day)

    start_year = today.year if start_this_year <= today else today.year - 1
    end_year = today.year if end_this_year >= today else today.year + 1

    return (
        _build_date(start_year, start_month, start_day),
        _build_date(end_year, end_month, end_day),
    )


class SolaredgeForecastData(DataUpdateCoordinator):
    """Get and update SolarEdge forecast data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="SolarEdge Forecast",
            update_interval=UPDATE_INTERVAL,
        )

        settings = _entry_settings(entry)
        account_key = str(settings[CONF_ACCOUNT_KEY]).strip()
        try:
            site_id = int(settings[CONF_SITE_ID])
            start_day = int(settings[CONF_STARTDAY])
            end_day = int(settings[CONF_ENDDAY])
        except (TypeError, ValueError) as err:
            raise ValueError("SolarEdge Forecast configuration is invalid") from err

        if not account_key:
            raise ValueError("SolarEdge account key is required")
        if site_id <= 0:
            raise ValueError("SolarEdge site ID must be a positive integer")

        self.account_key = account_key
        self.site_id = site_id
        self.start_day = start_day
        self.start_month = settings[CONF_STARTMONTH]
        self.end_day = end_day
        self.end_month = settings[CONF_ENDMONTH]
        start_date_production = settings[CONF_STARTDATE_PRODUCTION] or ""
        self.start_date_production = (
            str(start_date_production)
            .replace("/", "")
            .replace("-", "")
            .replace(" ", "")
        )
        self.unique_id = entry.entry_id
        self.name = entry.title

        startdate, enddate = _active_forecast_period(
            self.start_day,
            self.start_month,
            self.end_day,
            self.end_month,
            dt_util.now().date(),
        )
        self.startdate = startdate.strftime("%Y%m%d")
        self.enddate = enddate.strftime("%Y%m%d")

    async def _async_update_data(self):
        """Update data from SolarEdge."""
        try:
            data = await self.hass.async_add_executor_job(
                _fetch_forecast,
                self.startdate,
                self.enddate,
                self.start_date_production,
                self.site_id,
                self.account_key,
            )
        except Exception as err:
            raise UpdateFailed(f"Error updating SolarEdge forecast: {err}") from err

        self.logger.debug("SolarEdge forecast update succeeded: %s", data)
        return data


def _fetch_forecast(
    startdate: str,
    enddate: str,
    start_date_production: str,
    site_id: int,
    account_key: str,
):
    """Create the forecast object inside the executor."""
    from .solaredgeforecast import SolaredgeForecast

    return SolaredgeForecast(
        startdate,
        enddate,
        start_date_production,
        site_id,
        account_key,
    )
