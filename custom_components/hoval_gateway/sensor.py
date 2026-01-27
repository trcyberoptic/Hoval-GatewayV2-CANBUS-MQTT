"""Sensor platform for Hoval Gateway."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HovalDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Hoval Gateway sensors."""
    coordinator: HovalDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    # Create sensors for all known datapoints
    entities = []
    for dp_info in coordinator.datapoint_map.values():
        entities.append(
            HovalSensor(
                coordinator,
                entry,
                dp_info['name'],
                dp_info['unit'],
            )
        )

    async_add_entities(entities)


class HovalSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Hoval sensor."""

    def __init__(
        self,
        coordinator: HovalDataUpdateCoordinator,
        entry: ConfigEntry,
        name: str,
        unit: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._attr_name = f'Hoval {name}'
        self._original_name = name
        self._unit = unit

        # Normalize name for unique ID
        clean_name = name.lower().replace(' ', '_')
        clean_name = clean_name.replace('ä', 'ae').replace('ö', 'oe')
        clean_name = clean_name.replace('ü', 'ue').replace('ß', 'ss')
        clean_name = clean_name.replace('.', '').replace('/', '')
        self._clean_name = clean_name

        self._attr_unique_id = f'{entry.entry_id}_{clean_name}'

        # Set unit of measurement
        if unit == '°C':
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_icon = 'mdi:thermometer'
        elif unit == '%':
            self._attr_native_unit_of_measurement = PERCENTAGE
            if 'feucht' in name.lower():
                self._attr_device_class = SensorDeviceClass.HUMIDITY
                self._attr_icon = 'mdi:water-percent'
            elif 'lueft' in name.lower() or 'lüft' in name.lower():
                self._attr_icon = 'mdi:fan'
            self._attr_state_class = SensorStateClass.MEASUREMENT
        else:
            self._attr_native_unit_of_measurement = unit

        # Device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name='Hoval HomeVent',
            manufacturer='Hoval',
            model='HomeVent',
            sw_version='2.6.1',
        )

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        return self.coordinator.last_sent.get(self._clean_name)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self._clean_name in self.coordinator.last_sent
