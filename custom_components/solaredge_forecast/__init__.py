"""SolarEdge Forecast integration."""

from __future__ import annotations

import asyncio
import logging
import time
from calendar import monthrange
from datetime import date, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from solaredge import (
    AsyncMonitoringClient,
    SolarEdgeAuthError,
    SolarEdgeError,
    SolarEdgeOAuthError,
    SolarEdgeRateLimitError,
    SolarEdgeResponseError,
)

from .api import (
    TokenStorage,
    first_history_month,
    midnight,
    monthly_history,
    retry_delay,
    total_kwh,
)
from .const import (
    CONF_ENDDAY,
    CONF_ENDMONTH,
    CONF_SITE_ID,
    CONF_STARTDATE_PRODUCTION,
    CONF_STARTDAY,
    CONF_STARTMONTH,
    CONF_TOKEN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_ENDDAY,
    DEFAULT_ENDMONTH,
    DEFAULT_SITE_ID,
    DEFAULT_STARTDATE_PRODUCTION,
    DEFAULT_STARTDAY,
    DEFAULT_STARTMONTH,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MONTHS,
)
from .solaredgeforecast import SolaredgeForecast, _production_start_date

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Keep legacy settings and entity identities; V1 grants require reauth."""
    if entry.version > 2:
        return False
    if entry.version == 1:
        hass.config_entries.async_update_entry(entry, version=2)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry for SolarEdge Forecast."""
    try:
        coordinator = SolaredgeForecastData(hass, entry)
    except (TypeError, ValueError) as err:
        raise ConfigEntryError("Invalid SolarEdge Forecast configuration") from err
    try:
        await coordinator.async_initialize()
    except (ValueError, KeyError) as err:
        raise ConfigEntryAuthFailed("Authorize SolarEdge V2 Site Access") from err
    except OSError as err:
        raise ConfigEntryNotReady("Cannot persist SolarEdge Site Access token") from err
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Storage is authoritative after the initial grant has been persisted.
    if CONF_TOKEN in entry.data:
        hass.config_entries.async_update_entry(
            entry,
            data={key: value for key, value in entry.data.items() if key != CONF_TOKEN},
        )
    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the integration after options change."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None and coordinator._shutdown_requested:
        return
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
        CONF_UPDATE_INTERVAL: entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
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
        settings = _entry_settings(entry)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name="SolarEdge Forecast",
            update_interval=timedelta(minutes=int(settings[CONF_UPDATE_INTERVAL])),
        )
        try:
            site_id = int(settings[CONF_SITE_ID])
            start_day = int(settings[CONF_STARTDAY])
            end_day = int(settings[CONF_ENDDAY])
        except (TypeError, ValueError) as err:
            raise ValueError("SolarEdge Forecast configuration is invalid") from err

        if site_id <= 0:
            raise ValueError("SolarEdge site ID must be a positive integer")

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
        self.tokens = TokenStorage(hass, entry)
        self.history_store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.history")
        self.cache: dict[str, Any] = {}
        self.retry_at = 0.0
        self.next_request_at = 0.0
        self.authorization_lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Load tokens and cached complete months."""
        self.auth = await self.tokens.async_auth()
        cache = await self.history_store.async_load()
        if cache is not None and not isinstance(cache, dict):
            raise ConfigEntryError("Invalid SolarEdge history cache")
        self.cache = cache or {}

    async def _async_pace_request(self, request: httpx.Request) -> None:
        """Respect the Free tier's 10 calls/minute, including token requests."""
        await asyncio.sleep(max(0, self.next_request_at - time.monotonic()))
        self.next_request_at = time.monotonic() + 6.1

    async def _async_update_data(self):
        """Update data from SolarEdge."""
        async with self.authorization_lock:
            if self._shutdown_requested:
                raise UpdateFailed("SolarEdge coordinator is shutting down")
            return await self._async_fetch_data()

    async def _async_fetch_data(self):
        """Fetch production while holding the authorization lifecycle lock."""
        if time.time() < self.retry_at:
            raise UpdateFailed("SolarEdge rate limit backoff is active")
        try:
            await self.tokens.async_flush()
            async with AsyncMonitoringClient(oauth=self.auth) as client:
                client.client.event_hooks["request"].append(self._async_pace_request)
                if self.cache.get("site_id") != self.site_id:
                    self.cache = {"site_id": self.site_id}
                if "details" not in self.cache:
                    self.cache["details"] = await client.get_site_details(self.site_id)
                details = self.cache["details"]
                if not isinstance(details, dict) or not isinstance(
                    details.get("location"), dict
                ):
                    raise SolarEdgeResponseError("Invalid V2 site metadata")
                timezone = ZoneInfo(details["location"]["timezone"])
                now = dt_util.now().astimezone(timezone)
                today = now.date()
                startdate, enddate = _active_forecast_period(
                    self.start_day,
                    self.start_month,
                    self.end_day,
                    self.end_month,
                    today,
                )
                production_start = _production_start_date(
                    self.start_date_production
                ) or first_history_month(details)
                month_end = today.replace(day=1)
                history_key = f"{production_start}:{month_end}:{timezone.key}"
                if (
                    self.cache.get("history_key") != history_key
                    or time.time() - self.cache.get("saved_at", 0) >= 7 * 86400
                ):
                    history = await monthly_history(
                        client, self.site_id, production_start, month_end, timezone
                    )
                    self.cache.update(
                        history_key=history_key, history=history, saved_at=time.time()
                    )
                    await self.history_store.async_save(self.cache)
                produced = total_kwh(
                    await client.get_energy(
                        self.site_id,
                        start=midnight(startdate, timezone),
                        end=now,
                        resolution="TOTAL",
                        unit="KWH",
                    )
                )
                produced_today = total_kwh(
                    await client.get_energy(
                        self.site_id,
                        start=midnight(today, timezone),
                        end=now,
                        resolution="TOTAL",
                        unit="KWH",
                    )
                )
            return SolaredgeForecast(
                startdate.strftime("%Y%m%d"),
                enddate.strftime("%Y%m%d"),
                production_start.strftime("%d%m%Y"),
                self.site_id,
                self.cache["history"],
                produced,
                produced_today,
                today,
            )
        except (SolarEdgeAuthError, SolarEdgeOAuthError) as err:
            raise ConfigEntryAuthFailed(
                "SolarEdge Site Access authorization expired or was denied"
            ) from err
        except SolarEdgeRateLimitError as err:
            self.retry_at = time.time() + retry_delay(err.retry_after)
            raise UpdateFailed("SolarEdge API credit or rate limit reached") from err
        except (SolarEdgeError, httpx.TransportError) as err:
            raise UpdateFailed(
                f"SolarEdge V2 request failed ({type(err).__name__})"
            ) from err
        except (ValueError, KeyError, TypeError, ZoneInfoNotFoundError) as err:
            raise UpdateFailed(
                "Invalid forecast history or site timezone; "
                "check production dates and V2 site metadata"
            ) from err
        except OSError as err:
            raise UpdateFailed("Could not persist SolarEdge tokens or history") from err
