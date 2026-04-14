"""Support for BrightEMS device sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricPotential,
    UnitOfElectricPower,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import BrightEMSBluetoothEntity
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors from a config entry."""
    bluetooth_devices = hass.data[DOMAIN][entry.entry_id]["devices"]
    entities = []
    for device in bluetooth_devices.values():
        entity = BrightEMSSensor(device)
        entities.append(entity)
    async_add_entities(entities)


class BrightEMSSensor(BrightEMSBluetoothEntity, SensorEntity):
    """Representation of a BrightEMS device sensor."""

    def __init__(self, device: dict) -> None:
        """Initialize the sensor."""
        super().__init__(device)
        self._attr_unique_id = f"{device['mac_address']}_sensor"
        self._attr_name = f"{device['name']} Sensor"
        self._attr_native_value = None
        self._attr_device_class = None
        self._attr_state_class = None
        self._attr_unit_of_measurement = None

    @property
    def device_info(self) -> dict | None:
        """Return the device info."""
        return {
            "identifiers": {(DOMAIN, self._device["mac_address"])},
            "name": self._device["name"],
            "model": self._device.get("model", "BrightEMS Device"),
            "manufacturer": "BrightEMS",
        }

    async def async_update(self) -> None:
        """Fetch the latest data from the device."""
        if self._device.get("service_uuid"):
            service_data = await self._ble_device.read_characteristic(
                self._device["service_uuid"]
            )
            if service_data:
                self._parse_sensor_data(service_data)

    def _parse_sensor_data(self, data: bytes) -> None:
        """Parse sensor data from the device."""
        if not data or len(data) < 2:
            return

        value = int.from_bytes(data[:2], byteorder="big")
        self._attr_native_value = value

        self._set_sensor_properties()

    def _set_sensor_properties(self) -> None:
        """Set sensor properties based on device data."""
        pass
