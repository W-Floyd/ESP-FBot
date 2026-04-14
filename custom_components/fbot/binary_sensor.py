"""Binary sensor platform for the fbot Bluetooth integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import BrightEMSDataUpdateCoordinator, BrightEMSBluetoothEntity
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensors from a config entry."""
    coordinator: BrightEMSDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    entities = []

    # Get device features from catalog
    device_uuid = coordinator.device_info.get("product_key", "")
    product_key = f"{device_uuid.upper()}_SYDPOWER"

    if product_key in FEATURES:
        features = FEATURES[product_key]
        for state in features.get("states", []):
            # Create binary sensor entities for status states
            if state.get("input_index") is not None:
                entities.append(
                    BrightEMSBinarySensor(
                        coordinator=coordinator,
                        state_id=state["id"],
                        name=state.get("function_name", "Unknown"),
                        input_index=state["input_index"],
                        device_class=BinarySensorDeviceClass.CONNECTIVITY,
                        enabled_default=True,
                    )
                )

    if entities:
        async_add_entities(entities)


class BrightEMSBinarySensor(BrightEMSBluetoothEntity, BinarySensorEntity):
    """Representation of a BrightEMS binary sensor."""

    def __init__(
        self,
        coordinator: BrightEMSDataUpdateCoordinator,
        state_id: str,
        name: str,
        input_index: int,
        device_class: BinarySensorDeviceClass,
        enabled_default: bool,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator.device_info)
        self._coordinator = coordinator
        self._state_id = state_id
        self._input_index = input_index
        self._attr_name = f"{name} Status"
        self._attr_unique_id = f"{coordinator.device_address}_{state_id}"