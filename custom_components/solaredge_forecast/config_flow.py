"""Config flow for solaredge forecast integration."""
import datetime
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_ACCOUNT_KEY,
    CONF_SITE_ID,
    CONF_STARTDAY,
    CONF_STARTMONTH,
    CONF_ENDDAY,
    CONF_ENDMONTH,
    CONF_STARTDATE_PRODUCTION,
    DEFAULT_ACCOUNT_KEY,
    DEFAULT_SITE_ID,
    DEFAULT_STARTDAY,
    DEFAULT_STARTMONTH,
    DEFAULT_ENDDAY,
    DEFAULT_ENDMONTH,
    DEFAULT_STARTDATE_PRODUCTION,
    DOMAIN,
    MONTHS,
)

_LOGGER = logging.getLogger(__name__)


@callback
def solaredge_forecast_entries(hass: HomeAssistant):
    """Return the installation ID already configured."""
    return {
        entry.data[CONF_SITE_ID] for entry in hass.config_entries.async_entries(DOMAIN)
    }


class SolaredgeForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for solaredge forecast integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._errors: dict = {}

    async def async_step_user(self, user_input=None):
        """Step when user initializes a integration."""
        self._errors = {}

        if user_input is not None:
            if not await self._date_validation(user_input[CONF_STARTDAY], user_input[CONF_STARTMONTH]):
                self._errors[CONF_STARTDAY] = "invalid_startday"
            elif not await self._date_validation(user_input[CONF_ENDDAY], user_input[CONF_ENDMONTH]):
                self._errors[CONF_ENDDAY] = "invalid_endday"
            elif not await self._startdate_validation(user_input[CONF_STARTDATE_PRODUCTION]):
                self._errors[CONF_STARTDATE_PRODUCTION] = "invalid_startdate_production"
            elif not await self._period_validation(user_input[CONF_STARTDAY], user_input[CONF_STARTMONTH],
                                                   user_input[CONF_ENDDAY],user_input[CONF_ENDMONTH]):
                self._errors[CONF_ENDMONTH] = "invalid_period"
            elif await self._installation_id_in_configuration_exists(self.hass, user_input[CONF_SITE_ID]):
                self._errors[CONF_SITE_ID] = "already_configured"
            elif await self._account_key_in_configuration_exists(self.hass, user_input[CONF_ACCOUNT_KEY]):
                self._errors[CONF_ACCOUNT_KEY] = "already_configured"
            else:
                return self.async_create_entry(
                    title="Solaredge Forecast", data=user_input
                )

        user_input = {}
        # Provide defaults for form
        user_input[CONF_SITE_ID] = DEFAULT_SITE_ID
        user_input[CONF_ACCOUNT_KEY] = DEFAULT_ACCOUNT_KEY
        user_input[CONF_STARTDAY] = DEFAULT_STARTDAY
        user_input[CONF_STARTMONTH] = DEFAULT_STARTMONTH
        user_input[CONF_ENDDAY] = DEFAULT_ENDDAY
        user_input[CONF_ENDMONTH] = DEFAULT_ENDMONTH
        user_input[CONF_STARTDATE_PRODUCTION] = DEFAULT_STARTDATE_PRODUCTION

        return await self._show_config_form(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return SolaredgeForecastOptionsFlowHandler(config_entry)

    async def _show_config_form(self, user_input):  # pylint: disable=unused-argument
        """Show the configuration form to edit config data."""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SITE_ID, default=user_input.get(CONF_SITE_ID, DEFAULT_SITE_ID)
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_ACCOUNT_KEY, default=user_input.get(CONF_ACCOUNT_KEY, DEFAULT_ACCOUNT_KEY)
                    ): cv.string,
                    vol.Optional(
                        CONF_STARTDAY, default=user_input.get(CONF_STARTDAY, DEFAULT_STARTDAY)
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_STARTMONTH, default=user_input.get(CONF_STARTMONTH, DEFAULT_STARTMONTH)
                    ):  vol.In(MONTHS),
                    vol.Optional(
                        CONF_ENDDAY, default=user_input.get(CONF_ENDDAY, DEFAULT_ENDDAY)
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_ENDMONTH, default=user_input.get(CONF_ENDMONTH, DEFAULT_ENDMONTH)
                    ): vol.In(MONTHS),
                    vol.Optional(
                        CONF_STARTDATE_PRODUCTION, default=user_input.get(CONF_STARTDATE_PRODUCTION, DEFAULT_STARTDATE_PRODUCTION)
                    ): cv.string,
                }
            ),
            errors=self._errors,
        )

    async def _date_validation(self, day, month) -> bool:
        """Return True if day and month is a correct date."""
        try:
            datetime.datetime.strptime(
                str(datetime.datetime.now().year) + month + str(day), "%Y%B%d"
            )
            return True
        except ValueError:
            return False

    async def _startdate_validation(self, date) -> bool:
        """Return True if date is a correct date."""
        if date == "":
            return True
        try:
            if (datetime.datetime.today() - datetime.datetime.strptime(date.replace("/","").replace("-", "")
                                                           .replace(" ", ""), "%d%m%Y")).days < 365:
                return False
            return True
        except ValueError:
            return False

    async def _period_validation(self, startday, startmonth, endday, endmonth) -> bool:
        """Return True if today is within time period."""
        startdate = datetime.datetime.strptime(str(datetime.datetime.now().year) + startmonth + str(startday), "%Y%B%d")
        enddate = datetime.datetime.strptime(str(datetime.datetime.now().year) + endmonth + str(endday), "%Y%B%d")
        today = datetime.datetime.today()
        if startdate < enddate:
            if startdate < today < enddate:
                return True
        else:
            if startdate > today > enddate:
                return True
        return False

    async def _installation_id_in_configuration_exists(self, hass, installation_id_entry) -> bool:
        """Return True if installation id exists in configuration."""
        if installation_id_entry in solaredge_forecast_entries(hass):
            return True
        return False

    async def _account_key_in_configuration_exists(self, hass, account_key__entry) -> bool:
        """Return True if account key exists in configuration."""
        if account_key__entry in solaredge_forecast_entries(hass):
            return True
        return False

class SolaredgeForecastOptionsFlowHandler(config_entries.OptionsFlow):
    """Blueprint config flow options handler."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self._errors: dict = {}
        self.config_entry = config_entry
        self.options = dict(config_entry.options)

    async def async_step_init(self, user_input=None):  # pylint: disable=unused-argument
        """Manage the options."""
        return await self.async_step_user()

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        if user_input is not None:
            self.options.update(user_input)
            if not await self._date_validation(user_input[CONF_STARTDAY], user_input[CONF_STARTMONTH]):
                self._errors[CONF_STARTDAY] = "invalid_startday"
            elif not await self._date_validation(user_input[CONF_ENDDAY], user_input[CONF_ENDMONTH]):
                self._errors[CONF_ENDDAY] = "invalid_endday"
            elif not await self._startdate_validation(user_input[CONF_STARTDATE_PRODUCTION]):
                self._errors[CONF_STARTDATE_PRODUCTION] = "invalid_startdate_production"
            elif not await self._period_validation(user_input[CONF_STARTDAY], user_input[CONF_STARTMONTH],
                                                   user_input[CONF_ENDDAY],user_input[CONF_ENDMONTH]):
                self._errors[CONF_ENDMONTH] = "invalid_period"
            else:
                return await self._update_options()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SITE_ID, default=self.options.get(CONF_SITE_ID, DEFAULT_SITE_ID)
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_ACCOUNT_KEY, default=self.options.get(CONF_ACCOUNT_KEY, DEFAULT_ACCOUNT_KEY)
                    ): cv.string,
                    vol.Optional(
                        CONF_STARTDAY, default=self.options.get(CONF_STARTDAY, DEFAULT_STARTDAY)
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_STARTMONTH, default=self.options.get(CONF_STARTMONTH, DEFAULT_STARTMONTH)
                    ):  vol.In(MONTHS),
                    vol.Optional(
                        CONF_ENDDAY, default=self.options.get(CONF_ENDDAY, DEFAULT_ENDDAY)
                    ): cv.positive_int,
                    vol.Optional(
                        CONF_ENDMONTH, default=self.options.get(CONF_ENDMONTH, DEFAULT_ENDMONTH)
                    ): vol.In(MONTHS),
                    vol.Optional(
                        CONF_STARTDATE_PRODUCTION, default=self.options.get(CONF_STARTDATE_PRODUCTION,
                                                                            DEFAULT_STARTDATE_PRODUCTION)
                    ): cv.string,
                }
            ),
            errors=self._errors,
        )
    async def async_end(self):
        """Finalization of the ConfigEntry creation"""
        _LOGGER.info(
            "Recreating entry %s due to configuration change",
            self.config_entry.entry_id,
        )
        self.hass.config_entries.async_update_entry(self.config_entry, data=self._infos)
        return self.async_create_entry(title=None, data=None)

    async def _update_options(self):
        """Update config entry options."""
        return self.async_create_entry(
            title="Solaredge Forecast", data=self.options
        )

    async def _date_validation(self, day, month) -> bool:
        """Return True if day and month is a correct date."""
        try:
            datetime.datetime.strptime(
                str(datetime.datetime.now().year) + month + str(day), "%Y%B%d"
            )
            return True
        except ValueError:
            return False

    async def _startdate_validation(self, date) -> bool:
        """Return True if date is a correct date."""
        if date == "":
            return True
        try:
            if (datetime.datetime.today() - datetime.datetime.strptime(date.replace("/","").replace("-", "")
                                                           .replace(" ", ""), "%d%m%Y")).days < 365:
                return False
            return True
        except ValueError:
            return False


    async def _period_validation(self, startday, startmonth, endday, endmonth) -> bool:
        """Return True if today is within time period."""
        startdate = datetime.datetime.strptime(str(datetime.datetime.now().year) + startmonth + str(startday), "%Y%B%d")
        enddate = datetime.datetime.strptime(str(datetime.datetime.now().year) + endmonth + str(endday), "%Y%B%d")
        today = datetime.datetime.today()
        if startdate < enddate:
            if startdate < today < enddate:
                return True
        else:
            if startdate > today > enddate:
                return True
        return False