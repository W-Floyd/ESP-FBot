"""Config flow for the fbot Bluetooth integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothServiceData,
    async_discovered_entries,
    async_uuid_service_data,
)
from homeassistant.components.bluetooth.manager import BluetoothManager
from homeassistant.components.bluetooth.util import mac_bytes_to_address
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import BLE_SERVICE_UUIDS, DOMAIN
from .product_catalog import CATEGORIES, PRODUCTS

_LOGGER = logging.getLogger(__name__)

# Configuration schema for manual entry
CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required("ble_address"): str,
        vol.Required("ble_name", default=""): str,
    }
)

# Options schema for runtime configuration
OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional("poll_interval", default=30): vol.All(
            vol.Coerce(int), vol.Range(min=5, max=300)
        ),
        vol.Optional("enable_updates", default=True): bool,
    }
)


class FbotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BrightEMS fbot."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._ble_service_data: dict[str, dict] = {}
        self._discovered_devices: list[dict] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle the initial config flow step."""
        errors = {}

        if user_input is not None:
            address = user_input.get(CONF_ADDRESS, "")

            # Verify the address is valid
            if not address or ":" not in address:
                errors["base"] = "invalid_address"
            else:
                # Check if device is already configured
                await self.async_set_unique_id(address)
                self._abort_if_unique_id_configured()

                # Create entry
                return self.async_create_entry(
                    title=f"BrightEMS Device {address}",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=CONFIG_SCHEMA,
            errors=errors,
        )

    async def async_step_bluetooth(self, discovery_info: dict) -> Any:
        """Handle Bluetooth discovery."""
        _LOGGER.info("Discovered BrightEMS device via Bluetooth: %s", discovery_info)

        service_uuids = discovery_info.get("service_uuids", [])

        # Check if this is a BrightEMS device
        if not any(
            uuid.lower() in [uuid.lower() for uuid in BLE_SERVICE_UUIDS]
            for uuid in service_uuids
        ):
            return self.async_abort(reason="not_brightems_device")

        address = discovery_info.get("address", "")

        if not address:
            return self.async_abort(reason="no_address")

        # Check if device is already configured
        await self.async_set_unique_id(address)
        self._abort_if_unique_id_configured()

        # Store discovery info
        self._ble_service_data[address] = discovery_info

        # Show form for user confirmation
        return self.async_show_form(
            step_id="bluetooth",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "ble_name", default=discovery_info.get("name", "")
                    ): str,
                }
            ),
        )

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> Any:
        """Confirm Bluetooth discovery."""
        errors = {}

        if user_input is not None:
            address = self._ble_service_data.get("address", "")

            return self.async_create_entry(
                title=f"BrightEMS Device {address}",
                data={
                    CONF_ADDRESS: address,
                    "ble_name": user_input.get("ble_name", ""),
                },
            )

        # Show confirmation form
        address = self._ble_service_data.get("address", "")
        ble_name = self._ble_service_data.get("name", "")

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("ble_name", default=ble_name): str,
                }
            ),
            description_placeholders={
                "address": address,
                "ble_name": ble_name,
            },
        )


class FbotOptionsFlowHandler(OptionsFlow):
    """Handle options for BrightEMS fbot."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> Any:
        """Handle the initial options flow step."""
        errors = {}

        if user_input is not None:
            # Save updated options
            return self.async_create_entry(
                title="",
                data=user_input,
            )

        # Use existing options or defaults
        options = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=OPTIONS_SCHEMA.extend(
                {
                    vol.Optional(
                        "ble_address", default=options.get("ble_address", "")
                    ): str,
                    vol.Optional("ble_name", default=options.get("ble_name", "")): str,
                }
            ),
            errors=errors,
        )
