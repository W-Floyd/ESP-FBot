"""The Fbot Battery Station integration."""

from __future__ import annotations

import logging

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, CONF_NAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .catalog import lookup_profile
from .const import CONF_SERVICE_UUIDS, DOMAIN
from .coordinator import FbotCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fbot from a config entry."""
    service_uuids: list[str] = entry.data.get(CONF_SERVICE_UUIDS, [])
    local_name: str = entry.data.get(CONF_NAME, "")

    # Legacy entries (created before catalog support) only stored CONF_ADDRESS.
    # Try to recover the service UUIDs and local name from the BLE scanner so
    # we can look the device up in the catalog without forcing a re-pair.
    if not service_uuids:
        service_info = bluetooth.async_last_service_info(
            hass, entry.data[CONF_ADDRESS], connectable=True
        )
        if service_info is not None:
            service_uuids = list(service_info.service_uuids or [])
            local_name = service_info.name or local_name
            # Persist so the migration only runs once.
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    CONF_NAME: local_name,
                    CONF_SERVICE_UUIDS: service_uuids,
                },
            )
            _LOGGER.debug(
                "Migrated legacy entry for %s: name=%r UUIDs=%s",
                entry.data[CONF_ADDRESS],
                local_name,
                service_uuids,
            )
        else:
            raise ConfigEntryNotReady(
                f"Device {entry.data[CONF_ADDRESS]} not yet seen by BLE scanner; "
                "will retry when an advertisement is received"
            )

    profile = lookup_profile(service_uuids, local_name)

    if profile is None:
        _LOGGER.error(
            "Fbot device '%s' (UUIDs: %s) not found in product catalog — "
            "re-pair the device or update the catalog.",
            local_name,
            service_uuids,
        )
        return False

    coordinator = FbotCoordinator(
        hass,
        address=entry.data[CONF_ADDRESS],
        name=entry.title,
        profile=profile,
    )

    await coordinator.async_refresh()
    await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: FbotCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_stop()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
