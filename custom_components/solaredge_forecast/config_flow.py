"""Config flow for the SolarEdge Forecast integration."""

from __future__ import annotations

import secrets
from contextlib import nullcontext
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util
from solaredge import (
    OAuthToken,
    SolarEdgeError,
    SolarEdgeOAuthError,
    SolarEdgeValidationError,
)
from solaredge.oauth import async_exchange_code, authorization_url, parse_callback

from .api import DurableTokenStore
from .const import (
    CONF_ACCOUNT_KEY,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_ENDDAY,
    CONF_ENDMONTH,
    CONF_REDIRECT_URI,
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
        CONF_UPDATE_INTERVAL: _entry_value(
            entry, CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        ),
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
    except TypeError, ValueError:
        return False

    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id == ignore_entry_id:
            continue
        configured_site_id = _entry_value(entry, CONF_SITE_ID)
        try:
            configured_site_id = int(configured_site_id)
        except TypeError, ValueError:
            continue
        if configured_site_id == normalized_site_id:
            return True
    return False


def _validate_user_input(user_input: dict[str, Any]) -> dict[str, str]:
    """Validate config or options flow input."""
    errors: dict[str, str] = {}
    today = dt_util.now().date()

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
    return vol.Schema(
        {
            site_id: cv.positive_int,
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=defaults.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=60, max=1440)),
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

    VERSION = 2

    def __init__(self) -> None:
        """Keep authorization state in the active flow, never in options."""
        self.settings: dict[str, Any] = {}
        self.credentials: dict[str, str] = {}
        self.state = secrets.token_urlsafe(32)
        self.reauth_entry = None
        self.authorized_token: OAuthToken | None = None

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
                self.settings = user_input
                return await self.async_step_auth()

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data):
        """Upgrade an existing V1 entry or renew an expired V2 grant."""
        self.reauth_entry = self._get_reauth_entry()
        self.settings = _entry_settings(self.reauth_entry)
        return await self.async_step_auth()

    async def async_step_reconfigure(self, user_input=None):
        """Allow replacement of app credentials without replacing sensors."""
        self.reauth_entry = self._get_reconfigure_entry()
        self.settings = _entry_settings(self.reauth_entry)
        return await self.async_step_auth(user_input)

    async def async_step_auth(self, user_input=None):
        """Collect locally registered Site Access application credentials."""
        errors = {}
        if user_input is not None:
            redirect = urlsplit(user_input[CONF_REDIRECT_URI])
            if (
                redirect.scheme not in ("https", "http")
                or not redirect.netloc
                or redirect.query
                or redirect.fragment
                or redirect.username
                or redirect.password
                or (
                    redirect.scheme == "http"
                    and redirect.hostname not in ("localhost", "127.0.0.1", "::1")
                )
            ):
                errors["base"] = "invalid_redirect"
            elif not all(value.strip() for value in user_input.values()):
                errors["base"] = "invalid_auth"
            else:
                self.credentials = {
                    key: value.strip() for key, value in user_input.items()
                }
                self.state = secrets.token_urlsafe(32)
                self.authorized_token = None
                return await self.async_step_authorize()
        defaults = self.reauth_entry.data if self.reauth_entry else {}
        return self.async_show_form(
            step_id="auth",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CLIENT_ID, default=defaults.get(CONF_CLIENT_ID, "")
                    ): cv.string,
                    vol.Required(CONF_CLIENT_SECRET): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Required(
                        CONF_REDIRECT_URI, default=defaults.get(CONF_REDIRECT_URI, "")
                    ): cv.string,
                }
            ),
            errors=errors,
        )

    async def async_step_authorize(self, user_input=None):
        """Exchange the manually returned SolarEdge callback for a rotating grant."""
        errors = {}
        if user_input is not None:
            try:
                callback_url = user_input["callback_url"]
                actual = urlsplit(callback_url)
                expected = urlsplit(self.credentials[CONF_REDIRECT_URI])
                if (actual.scheme, actual.netloc, actual.path) != (
                    expected.scheme,
                    expected.netloc,
                    expected.path,
                ):
                    raise SolarEdgeValidationError("Incorrect redirect URI")
                callback = parse_callback(callback_url, expected_state=self.state)
                if callback.site_id != int(self.settings[CONF_SITE_ID]):
                    raise SolarEdgeValidationError("Incorrect authorized site")
                if (
                    callback.external_id is not None
                    and callback.external_id != self.state
                ):
                    raise SolarEdgeValidationError("Incorrect authorization identifier")
                if self.authorized_token is None:
                    self.authorized_token = await async_exchange_code(
                        self.credentials[CONF_CLIENT_ID],
                        self.credentials[CONF_CLIENT_SECRET],
                        callback.code,
                        redirect_uri=self.credentials[CONF_REDIRECT_URI],
                        site_id=callback.site_id,
                    )
                token = self.authorized_token
                if not token.refresh_token:
                    self.authorized_token = None
                    raise SolarEdgeValidationError("Missing rotating refresh token")
            except SolarEdgeValidationError, SolarEdgeOAuthError:
                errors["base"] = "invalid_auth"
            except SolarEdgeError, httpx.TransportError:
                errors["base"] = "cannot_connect"
            else:
                data = {**self.settings, **self.credentials}
                if self.reauth_entry is not None:
                    try:
                        coordinator = self.hass.data.get(DOMAIN, {}).get(
                            self.reauth_entry.entry_id
                        )
                        async with (
                            coordinator.authorization_lock
                            if coordinator
                            else nullcontext()
                        ):
                            if coordinator:
                                await coordinator.async_shutdown()
                            await DurableTokenStore(
                                self.hass,
                                1,
                                f"{DOMAIN}.{self.reauth_entry.entry_id}.oauth",
                                private=True,
                                atomic_writes=True,
                            ).async_save(token.to_dict())
                    except OSError:
                        errors["base"] = "cannot_store"
                    else:
                        options = {
                            key: value
                            for key, value in self.reauth_entry.options.items()
                            if key != CONF_ACCOUNT_KEY
                        }
                        self.hass.config_entries.async_update_entry(
                            self.reauth_entry, data=data, options=options, version=2
                        )
                        await self.hass.config_entries.async_reload(
                            self.reauth_entry.entry_id
                        )
                        return self.async_abort(reason="reauth_successful")
                else:
                    return self.async_create_entry(
                        title=f"SolarEdge Forecast {self.settings[CONF_SITE_ID]}",
                        data={**data, CONF_TOKEN: token.to_dict()},
                    )
        url = authorization_url(
            self.credentials[CONF_CLIENT_ID],
            redirect_uri=self.credentials[CONF_REDIRECT_URI],
            scopes=("SITE_DATA",),
            state=self.state,
            external_id=self.state,
            access_duration=24,
        )
        return self.async_show_form(
            step_id="authorize",
            data_schema=vol.Schema(
                {
                    vol.Required("callback_url"): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={"authorization_url": url},
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
            if int(user_input[CONF_SITE_ID]) != int(
                _entry_value(self.config_entry, CONF_SITE_ID)
            ):
                errors[CONF_SITE_ID] = "site_change"
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
