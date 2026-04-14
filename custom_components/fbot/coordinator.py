"""Coordinator for BrightEMS device data handling."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .ble_handler import BLEHandler
from .product_catalog import CATEGORIES, FEATURES

_LOGGER = logging.getLogger(__name__)


class BrightEMSDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinate data updates from BrightEMS devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        ble_handler: BLEHandler,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="fbot_device",
            update_interval=timedelta(seconds=30),
        )

        self.entry = entry
        self.ble_handler = ble_handler
        self.device_address = entry.data.get("address", "")
        self.product_key = entry.data.get("product_key", "")

        # Get device info
        self.device_info = {
            "address": self.device_address,
            "product_key": self.product_key,
            "name": entry.title,
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch the latest data from the device."""
        _LOGGER.debug(
            "Updating data for device %s (product: %s)",
            self.device_address,
            self.product_key,
        )

        # Get device features from catalog
        features = FEATURES.get(self.product_key, {"states": [], "settings": []})

        # Read registers from device
        try:
            device_data = await self._read_device_registers()
            return {
                "features": features,
                "registers": device_data,
                "device_info": self.device_info,
            }
        except Exception as err:
            _LOGGER.error("Failed to fetch data for %s: %s", self.device_address, err)
            raise UpdateFailed(f"Update failed: {err}") from err

    async def _read_device_registers(self) -> dict[str, Any]:
        """Read registers from the connected device."""
        # This would use the BLE handler to communicate with the device
        # For now, return empty data that will be populated when device connects

        service_uuid = self.entry.data.get("service_uuid", "")
        if not service_uuid:
            return {}

        try:
            # TODO: Implement actual BLE communication
            # This would use the BLE handler to send read commands
            # and parse the responses according to the Modbus protocol

            # Simulate reading from device (replace with actual implementation)
            device_data = {
                "status": "connected",
                "signal_strength": -65,
                "last_update": "2024-01-01T00:00:00Z",
            }

            return device_data

        except Exception as err:
            _LOGGER.error("Error reading device registers: %s", err)
            return {}

    async def send_command(
        self,
        register_address: int,
        value: int,
    ) -> bool:
        """Send a command to the device.

        Args:
            register_address: The Modbus register address to write
            value: The value to write

        Returns:
            True if the command was successful, False otherwise
        """
        _LOGGER.debug(
            "Sending command to device %s: reg=0x%04X val=%d",
            self.device_address,
            register_address,
            value,
        )

        # TODO: Implement actual BLE command sending
        # This would use the BLE handler to send the Modbus command
        # to the device and wait for confirmation

        try:
            # Simulate command sending
            await asyncio.sleep(0.1)
            return True

        except Exception as err:
            _LOGGER.error("Failed to send command: %s", err)
            return False

    async def read_register(self, register_address: int) -> Optional[int]:
        """Read a register value from the device.

        Args:
            register_address: The Modbus register address to read

        Returns:
            The register value if successful, None otherwise
        """
        _LOGGER.debug(
            "Reading register 0x%04X from device %s",
            register_address,
            self.device_address,
        )

        # TODO: Implement actual BLE read operation
        # This would use the BLE handler to send a read command
        # and parse the response

        try:
            # Simulate reading (replace with actual implementation)
            await asyncio.sleep(0.1)
            return 0  # Placeholder value

        except Exception as err:
            _LOGGER.error("Failed to read register: %s", err)
            return None

    def get_device_features(self) -> dict[str, Any]:
        """Get the device features from the product catalog."""
        features = FEATURES.get(self.product_key, {"states": [], "settings": []})
        return features

    def get_product_info(self) -> Optional[dict[str, Any]]:
        """Get product information from the catalog."""
        product_key = self.product_key
        if product_key:
            for key in FEATURES:
                if product_key in key:
                    return FEATURES[key]
        return None

    async def async_stop(self) -> None:
        """Stop the coordinator."""
        _LOGGER.info("Stopping coordinator for device %s", self.device_address)
        await super().async_stop()
        await self.ble_handler.disconnect()


class FbotCoordinator:
    """Legacy coordinator for backward compatibility."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        name: str,
        profile: dict,
    ) -> None:
        """Initialize the coordinator."""
        self.hass = hass
        self.address = address
        self._device_name = name
        self.profile = profile
        self._data: dict[str, Any] = {}
        self._unsub_refresh: Optional[asyncio.Task] = None

    @property
    def data(self) -> dict[str, Any]:
        """Return the latest data."""
        return self._data

    @property
    def device_name(self) -> str:
        """Return the device name."""
        return self._device_name

    async def async_refresh(self) -> None:
        """Refresh data from the device."""
        _LOGGER.debug("Refreshing data for device %s", self.address)
        self._data = {}
        await self.async_start()

    async def async_start(self) -> None:
        """Start data collection."""
        _LOGGER.debug("Starting data collection for device %s", self.address)

    async def async_stop(self) -> None:
        """Stop data collection."""
        _LOGGER.debug("Stopping data collection for device %s", self.address)
        if self._unsub_refresh:
            self._unsub_refresh.cancel()
            self._unsub_refresh = None

    async def async_send_command(self, register_address: int, value: int) -> bool:
        """Send a command to the device."""
        return await self._send_modbus_command(register_address, value)

    async def _send_modbus_command(
        self,
        register_address: int,
        value: int,
    ) -> bool:
        """Send a Modbus command to the device.

        Args:
            register_address: The register address to write
            value: The value to write

        Returns:
            True if the command was successful
        """
        _LOGGER.debug(
            "Sending Modbus command: reg=0x%04X val=%d to %s",
            register_address,
            value,
            self.address,
        )

        # TODO: Implement actual BLE communication
        try:
            await asyncio.sleep(0.1)
            return True
        except Exception as err:
            _LOGGER.error("Failed to send command: %s", err)
            return False
