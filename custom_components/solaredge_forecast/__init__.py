"""SolarEdge Forecast integration."""
from datetime import timedelta
import datetime
import logging

from .solaredgeforecast import SolaredgeForecast

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import update_coordinator

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
    DOMAIN
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry for solaredge forecast."""
    coordinator = SolaredgeForecastData(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Update listener."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


class SolaredgeForecastData(update_coordinator.DataUpdateCoordinator):
    """Get and update the latest data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the data object."""
        super().__init__(
            hass, _LOGGER, name="Solaredge Forecast", update_interval=timedelta(seconds=900)
        )

        """Populate default options."""
        if not self.config_entry.options:
            data = dict(self.config_entry.data)
            options = {
                CONF_ACCOUNT_KEY: data.pop(CONF_ACCOUNT_KEY, DEFAULT_ACCOUNT_KEY),
                CONF_SITE_ID: data.pop(CONF_SITE_ID, DEFAULT_SITE_ID),
                CONF_STARTDAY: data.pop(CONF_STARTDAY, DEFAULT_STARTDAY),
                CONF_STARTMONTH: data.pop(CONF_STARTMONTH, DEFAULT_STARTMONTH),
                CONF_ENDDAY: data.pop(CONF_ENDDAY, DEFAULT_ENDDAY),
                CONF_ENDMONTH: data.pop(CONF_ENDMONTH, DEFAULT_ENDMONTH),
                CONF_STARTDATE_PRODUCTION: data.pop(CONF_STARTDATE_PRODUCTION, DEFAULT_STARTDATE_PRODUCTION),
            }

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=data,
                options=options
            )

        self.account_key = entry.options[CONF_ACCOUNT_KEY]
        self.site_id = entry.options[CONF_SITE_ID]
        self.start_day = entry.options[CONF_STARTDAY]
        self.start_month = entry.options[CONF_STARTMONTH]
        self.end_day = entry.options[CONF_ENDDAY]
        self.end_month = entry.options[CONF_ENDMONTH]
        self.start_date_production = entry.options[CONF_STARTDATE_PRODUCTION]\
            .replace("/","").replace("-", "").replace(" ", "")
        self.unique_id = entry.entry_id
        self.name = entry.title

        startdate = datetime.datetime.strptime(self.start_month + str(self.start_day), "%B%d")
        enddate = datetime.datetime.strptime(self.end_month + str(self.end_day), "%B%d")
        today = datetime.datetime.today()
        # define year of given start month and start day
        if today.month < startdate.month:
            start_year = today.year - 1
        elif today.month == startdate.month:
            if today.day < startdate.day:
                start_year = today.year - 1
            else:
                start_year = today.year
        else:
            start_year = today.year
        # define year of given end month and end day
        if today.month < enddate.month:
            end_year = today.year
        elif today.month == enddate.month:
            if today.day < enddate.day:
                end_year = today.year
            else:
                end_year = today.year + 1
        else:
            end_year = today.year + 1

        self.startdate = datetime.datetime.strptime(str(start_year) + self.start_month + str(self.start_day),
                                                    "%Y%B%d").strftime("%Y%m%d")
        self.enddate = datetime.datetime.strptime(str(end_year) + self.end_month + str(self.end_day),
                                                    "%Y%B%d").strftime("%Y%m%d")

    async def _async_update_data(self):
        """Update the data from the SolarEdge device."""

        try:
            data = await self.hass.async_add_executor_job(
                SolaredgeForecast,
                self.startdate,
                self.enddate,
                self.start_date_production,
                self.site_id,
                self.account_key
            )

        except OSError as err:
            raise update_coordinator.UpdateFailed(err)

        self.logger.debug(
            "Connection to SolarEdge successfull. Forecast this year %s",
            data,
        )

        return data
