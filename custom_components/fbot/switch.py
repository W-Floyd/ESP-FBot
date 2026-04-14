"""Switch platform for the BrightEMS fbot integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FbotCoordinator, FbotEntity
from .const import DOMAIN
from .product_catalog import CATEGORIES, FEATURES

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    coordinator: FbotCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities = []

    # Get device features from catalog
    device_uuid = coordinator.device_info.get("uuid", "")
    product_key = f"{device_uuid.upper()}_SYDPOWER"

    if product_key in FEATURES:
        features = FEATURES[product_key]
        for setting in features.get("settings", []):
            # Create switch entities for writable settings
            if setting.get("holding_index") is not None:
                entities.append(
                    FbotSwitch(
                        coordinator=coordinator,
                        setting_id=setting["id"],
                        name=setting.get("function_name", "Unknown"),
                        holding_index=setting["holding_index"],
                        unit=setting.get("unit", ""),
                    )
                )

    if entities:
        async_add_entities(entities)
