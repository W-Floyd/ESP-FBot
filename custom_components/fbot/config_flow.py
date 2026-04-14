"""Config flow for the Fbot integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ADDRESS, CONF_NAME

from .const import CONF_SERVICE_UUIDS, DOMAIN
from .product_catalog import PRODUCTS

# All product UUIDs known to the catalog (upper-case for case-insensitive matching).
_PRODUCT_UUIDS: frozenset[str] = frozenset(
    key.split("_", 1)[0].upper() for key in PRODUCTS
)


def _is_fbot_device(service_uuids: list[str]) -> bool:
    """Return True if any advertised UUID belongs to a known catalog product."""
    return any(uuid.upper() in _PRODUCT_UUIDS for uuid in service_uuids)


class FbotConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Fbot."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery_info: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Handle a Bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery_info = discovery_info
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Confirm Bluetooth discovery."""
        assert self._discovery_info is not None
        if user_input is not None:
            title = self._discovery_info.name or self._discovery_info.address
            return self.async_create_entry(
                title=title,
                data={
                    CONF_ADDRESS: self._discovery_info.address,
                    CONF_NAME: self._discovery_info.name or "",
                    CONF_SERVICE_UUIDS: list(self._discovery_info.service_uuids or []),
                },
            )
        self._set_confirm_only()
        name = self._discovery_info.name or self._discovery_info.address
        self.context["title_placeholders"] = {"name": name}
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": name},
        )

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle a user-initiated flow."""
        discovered_map = {
            info.address: info
            for info in async_discovered_service_info(self.hass, connectable=True)
            if _is_fbot_device(list(info.service_uuids or []))
        }

        if user_input is not None:
            address = user_input[CONF_ADDRESS].upper()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            info = discovered_map.get(address)
            return self.async_create_entry(
                title=info.name if info else address,
                data={
                    CONF_ADDRESS: address,
                    CONF_NAME: info.name or "" if info else "",
                    CONF_SERVICE_UUIDS: list(info.service_uuids or []) if info else [],
                },
            )

        # Offer discovered devices as a dropdown, fall back to free-text entry
        discovered = {
            info.address: f"{info.name or info.address} ({info.address})"
            for info in discovered_map.values()
        }

        if discovered:
            schema = vol.Schema({vol.Required(CONF_ADDRESS): vol.In(discovered)})
        else:
            schema = vol.Schema({vol.Required(CONF_ADDRESS): str})

        return self.async_show_form(step_id="user", data_schema=schema)
