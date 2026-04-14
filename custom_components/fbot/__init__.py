"""
The fbot integration - BrightEMS Bluetooth device support for Home Assistant.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceData,
    async_get_bluetooth_manager,
    async_scheduled_instances,
)
from homeassistant.components.bluetooth.const import DOMAIN as BLUETOOTH_DOMAIN
from homeassistant.components.bluetooth.manager import BluetoothManager
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import slugify

from .ble_handler import BLEHandler
from .const import (
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
)
from .coordinator import BrightEMSDataUpdateCoordinator
from .product_catalog import (
    CATEGORIES,
    FEATURES,
    PRODUCTS,
    SPACE_ID,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VALVE,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the fbot component from YAML."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up an entry for the fbot integration."""
    _LOGGER.debug("Setting up fbot entry: %s", entry.title)

    # Initialize the BLE handler
    ble_handler = BLEHandler(hass)
    hass.data.setdefault(DOMAIN, {})

    # Create the coordinator
    coordinator = BrightEMSDataUpdateCoordinator(
        hass,
        entry,
        ble_handler,
    )
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "ble_handler": ble_handler,
    }

    # Register the device
    await _async_setup_device(hass, entry)

    # Setup platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Refresh data on startup
    await coordinator.async_config_entry_first_refresh()

    # Schedule periodic updates
    entry.async_on_unload(
        hass.helpers.event.async_track_time_interval(
            coordinator.async_refresh, timedelta(seconds=30)
        )
    )

    return True


async def _async_setup_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up the device in the device registry."""
    device_registry = dr.async_get(hass)

    device_info = dr.DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"{entry.title} Device",
        manufacturer=MANUFACTURER,
        model=entry.title,
        sw_version=entry.options.get(CONF_REGISTER_MAP, {}).get(
            "firmware_version", "unknown"
        ),
    )

    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        **device_info,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entries."""
    if entry.version == 1:
        # Migrate from version 1 to 2
        _LOGGER.debug("Migrating entry from version %s", entry.version)

        new_data = entry.data.copy()

        if "ble_address" in new_data:
            new_data["ble_address"] = entry.data["ble_address"].upper()

        hass.config_entries.async_update_entry(entry, data=new_data, version=2)

    return True
