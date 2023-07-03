"""Constants for the solaredge forecast integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    ENERGY_KILO_WATT_HOUR
)

DOMAIN = "solaredge_forecast"

# Default config for solaredge forecast integration.
CONF_ACCOUNT_KEY = "account key"
CONF_SITE_ID = "site id"
CONF_STARTDAY = "startday"
CONF_STARTMONTH = "startmonth"
CONF_ENDDAY = "endday"
CONF_ENDMONTH = "endmonth"

DEFAULT_ACCOUNT_KEY = ""
DEFAULT_SITE_ID = ""
DEFAULT_STARTDAY = "01"
DEFAULT_STARTMONTH = "January"
DEFAULT_ENDDAY = "31"
DEFAULT_ENDMONTH = "December"

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December"
]

@dataclass
class SolaredgeForecastSensorEntityDescription(SensorEntityDescription):
    """Describes Solaredge Forecast sensor entity."""


SENSOR_TYPES: tuple[SolaredgeForecastSensorEntityDescription, ...] = (
    SolaredgeForecastSensorEntityDescription(
        key="solaredge_forecast",
        name="Solar energy forecast",
        icon="mdi:solar-power",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SolaredgeForecastSensorEntityDescription(
        key="solaredge_produced",
        name="Solar energy produced",
        icon="mdi:solar-power",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SolaredgeForecastSensorEntityDescription(
        key="solaredge_estimated",
        name="Solar energy expected",
        icon="mdi:solar-power",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SolaredgeForecastSensorEntityDescription(
        key="solaredge_progress",
        name="Solar energy progress",
        icon="mdi:solar-power",
        native_unit_of_measurement=ENERGY_KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    SolaredgeForecastSensorEntityDescription(
        key="startdate",
        name="Start date forecast period",
        icon="mdi:calendar",
        native_unit_of_measurement=None,
        device_class=SensorDeviceClass.DATE,
        state_class=None,
    ),
    SolaredgeForecastSensorEntityDescription(
        key="enddate",
        name="End date forecast period",
        icon="mdi:calendar",
        native_unit_of_measurement=None,
        device_class=SensorDeviceClass.DATE,
        state_class=None,
    ),
)
