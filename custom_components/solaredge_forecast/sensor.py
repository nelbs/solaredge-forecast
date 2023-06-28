"""Platform for solaredge forecast sensors."""
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers import update_coordinator
from homeassistant.helpers.entity import StateType

from . import SolaredgeForecastData
from .const import DOMAIN, SENSOR_TYPES, SolaredgeForecastSensorEntityDescription


async def async_setup_entry(hass, entry, async_add_entities):
    """Add solaredge forecast entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        SolaredgeForecastSensor(coordinator, description) for description in SENSOR_TYPES
    )


class SolaredgeForecastSensor(update_coordinator.CoordinatorEntity, SensorEntity):
    """Representation of a Sensor."""

    entity_description: SolaredgeForecastSensorEntityDescription

    def __init__(
        self,
        coordinator: SolaredgeForecastData,
        description: SolaredgeForecastSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_name = f"{description.name}"
        self._attr_unique_id = f"{coordinator.unique_id}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the native sensor value."""
        state = getattr(self.coordinator.data, self.entity_description.key)
        return state
