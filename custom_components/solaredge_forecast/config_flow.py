"""Config flow for the SolarEdge Forecast integration."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
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

DAY_SCHEMA = vol.All(vol.Coerce(int), vol.Range(min=1, max=31))


def _month_number(month: str) -> int:
    """Return the month number for an English month name."""
    return MONTHS.index(month) + 1


def _day_month_to_date(day: int | str, month: str, year: int) -> date:
    """Convert a day and month name to a date in the given year."""
    return date(year, _month_number(month), int(day))


def _parse_startdate_production(value: str) -> date | None:
    """Parse the optional production start date from the config flow."""
    cleaned = value.replace("/", "").replace("-", "").replace(" ", "")
    if not cleaned:
        return None
    return datetime.strptime(cleaned, "%d%m%Y").date()


def _entry_value(
    entry: config_entries.ConfigEntry, key: str, default: Any = None
) -> Any:
    """Return an entry setting, preferring options for legacy entries."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


def _entry_settings(entry: config_entries.ConfigEntry) -> dict[str, Any]:
    """Return all settings for a config entry."""
    return {
        CONF_SITE_ID: _entry_value(entry, CONF_SITE_ID, DEFAULT_SITE_ID),
        CONF_ACCOUNT_KEY: _entry_value(entry, CONF_ACCOUNT_KEY, DEFAULT_ACCOUNT_KEY),
        CONF_STARTDAY: _entry_value(entry, CONF_STARTDAY, DEFAULT_STARTDAY),
        CONF_STARTMONTH: _entry_value(entry, CONF_STARTMONTH, DEFAULT_STARTMONTH),
        CONF_ENDDAY: _entry_value(entry, CONF_ENDDAY, DEFAULT_ENDDAY),
        CONF_ENDMONTH: _entry_value(entry, CONF_ENDMONTH, DEFAULT_ENDMONTH),
        CONF_STARTDATE_PRODUCTION: _entry_value(
            entry, CONF_STARTDATE_PRODUCTION, DEFAULT_STARTDATE_PRODUCTION
        ),
    }


def _site_id_exists(
    hass: HomeAssistant, site_id: int | str, ignore_entry_id: str | None = None
) -> bool:
    """Return whether the site ID is already configured."""
    try:
        normalized_site_id = int(site_id)
    except (TypeError, ValueError):
        return False

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == ignore_entry_id:
            continue
        configured_site_id = _entry_value(entry, CONF_SITE_ID)
        try:
            configured_site_id = int(configured_site_id)
        except (TypeError, ValueError):
            continue
        if configured_site_id == normalized_site_id:
            return True
    return False


def _validate_user_input(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate config or options flow input."""
    errors: dict[str, str] = {}
    today = dt_util.now().date()

    if not str(user_input[CONF_ACCOUNT_KEY]).strip():
        errors[CONF_ACCOUNT_KEY] = "invalid_account_key"

    try:
        _day_month_to_date(
            user_input[CONF_STARTDAY], user_input[CONF_STARTMONTH], today.year
        )
    except ValueError:
        errors[CONF_STARTDAY] = "invalid_startday"

    try:
        _day_month_to_date(
            user_input[CONF_ENDDAY], user_input[CONF_ENDMONTH], today.year
        )
    except ValueError:
        errors[CONF_ENDDAY] = "invalid_endday"

    try:
        startdate_production = _parse_startdate_production(
            user_input.get(CONF_STARTDATE_PRODUCTION, DEFAULT_STARTDATE_PRODUCTION)
        )
    except ValueError:
        errors[CONF_STARTDATE_PRODUCTION] = "invalid_startdate_production"
    else:
        if (
            startdate_production is not None
            and today - startdate_production < timedelta(days=365)
        ):
            errors[CONF_STARTDATE_PRODUCTION] = "invalid_startdate_production"

    if not errors and not _period_contains_today(user_input, today):
        errors[CONF_ENDMONTH] = "invalid_period"

    return errors


def _period_contains_today(user_input: dict[str, Any], today: date) -> bool:
    """Return whether the forecast period contains today."""
    startdate = _day_month_to_date(
        user_input[CONF_STARTDAY], user_input[CONF_STARTMONTH], today.year
    )
    enddate = _day_month_to_date(
        user_input[CONF_ENDDAY], user_input[CONF_ENDMONTH], today.year
    )

    if startdate <= enddate:
        return startdate <= today <= enddate
    return today >= startdate or today <= enddate


def _schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Return the config or options form schema."""
    defaults = defaults or {}
    site_id = (
        vol.Required(CONF_SITE_ID, default=defaults[CONF_SITE_ID])
        if CONF_SITE_ID in defaults
        else vol.Required(CONF_SITE_ID)
    )
    account_key = (
        vol.Required(CONF_ACCOUNT_KEY, default=defaults[CONF_ACCOUNT_KEY])
        if CONF_ACCOUNT_KEY in defaults
        else vol.Required(CONF_ACCOUNT_KEY)
    )

    return vol.Schema(
        {
            site_id: cv.positive_int,
            account_key: cv.string,
            vol.Required(
                CONF_STARTDAY,
                default=defaults.get(CONF_STARTDAY, DEFAULT_STARTDAY),
            ): DAY_SCHEMA,
            vol.Required(
                CONF_STARTMONTH,
                default=defaults.get(CONF_STARTMONTH, DEFAULT_STARTMONTH),
            ): vol.In(MONTHS),
            vol.Required(
                CONF_ENDDAY,
                default=defaults.get(CONF_ENDDAY, DEFAULT_ENDDAY),
            ): DAY_SCHEMA,
            vol.Required(
                CONF_ENDMONTH,
                default=defaults.get(CONF_ENDMONTH, DEFAULT_ENDMONTH),
            ): vol.In(MONTHS),
            vol.Optional(
                CONF_STARTDATE_PRODUCTION,
                default=defaults.get(
                    CONF_STARTDATE_PRODUCTION, DEFAULT_STARTDATE_PRODUCTION
                ),
            ): cv.string,
        }
    )


class SolaredgeForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SolarEdge Forecast."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = _validate_user_input(user_input)
            if not errors and _site_id_exists(self.hass, user_input[CONF_SITE_ID]):
                errors[CONF_SITE_ID] = "already_configured"

            if not errors:
                await self.async_set_unique_id(str(user_input[CONF_SITE_ID]))
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"SolarEdge Forecast {user_input[CONF_SITE_ID]}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return SolaredgeForecastOptionsFlowHandler()


class SolaredgeForecastOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle SolarEdge Forecast options."""

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle options submitted by the user."""
        errors: dict[str, str] = {}
        defaults = (
            user_input if user_input is not None else _entry_settings(self.config_entry)
        )

        if user_input is not None:
            errors = _validate_user_input(user_input)
            if not errors and _site_id_exists(
                self.hass,
                user_input[CONF_SITE_ID],
                ignore_entry_id=self.config_entry.entry_id,
            ):
                errors[CONF_SITE_ID] = "already_configured"

            if not errors:
                return self.async_create_entry(
                    title=f"SolarEdge Forecast {user_input[CONF_SITE_ID]}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(defaults),
            errors=errors,
        )
