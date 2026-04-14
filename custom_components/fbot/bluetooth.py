"""
Home Assistant BrightEMS Bluetooth Integration Handler.

This module handles device discovery and connection for BrightEMS devices
using the product catalog from fetch_catalog.py.
"""

import asyncio
import logging
from typing import Any, Callable, Optional

from homeassistant.components.bluetooth import (
    BluetoothMatcher,
    BluetoothMatcherData,
    BluetoothServiceData,
)
from homeassistant.components.bluetooth.manager import (
    BluetoothManager,
    get_manager,
)
from homeassistant.components.bluetooth.util import mac_bytes_to_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntry, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import dt as dt_util

from .product_catalog import CATEGORIES, PRODUCTS

_LOGGER = logging.getLogger(__name__)


class BluetoothHandler:
    """Handle BrightEMS Bluetooth device discovery and connections."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the Bluetooth handler."""
        self.hass = hass
        self.manager: Optional[BluetoothManager] = None
        self._device_handlers: dict[str, Callable] = {}
        self._ble_services: dict[str, dict] = {}
        self._device_info: dict[str, DeviceInfo] = {}

    async def async_setup(self) -> None:
        """Set up the Bluetooth handler."""
        _LOGGER.info("Setting up BrightEMS Bluetooth handler")

        # Get the Bluetooth manager
        self.manager = await get_manager(self.hass)
        _LOGGER.debug(f"Bluetooth manager: {self.manager}")

        # Set up callback for BLE advertisement data
        self.manager.async_register_callback(
            self._handle_ble_advertisement,
        )

        # Start scanning for devices
        await self.manager.async_start_scanning()
        _LOGGER.info("Started scanning for BrightEMS devices")

    @callback
    def _handle_ble_advertisement(
        self,
        service_data: dict[str, list[BluetoothServiceData]],
        connectable: bool,
    ) -> None:
        """Handle incoming BLE advertisement data.

        Args:
            service_data: Dictionary of service UUIDs to service data lists
            connectable: Whether the device is connectable
        """
        _LOGGER.debug(f"BLE advertisement: {service_data}")

        # Process each service UUID
        for service_uuid, services in service_data.items():
            # Check if this is a BrightEMS service
            if service_uuid.lower() in [
                "0000a002-0000-1000-8000-00805f9b34fb",
                "6c382a98-49b8-40ba-b761-645d83e8ee74",
            ]:
                for service in services:
                    self._process_ble_data(service_uuid, service, connectable)

    def _process_ble_data(
        self,
        service_uuid: str,
        data: BluetoothServiceData,
        connectable: bool,
    ) -> None:
        """Process BLE advertisement data from a device.

        Args:
            service_uuid: The service UUID
            data: The service data
            connectable: Whether the device is connectable
        """
        address = data.address
        _LOGGER.info(f"Found BrightEMS device at {address}: {service_uuid}")

        # Store device info
        product_key = self._get_product_key_from_uuid(service_uuid)
        if product_key:
            product_info = PRODUCTS.get(product_key, {})
            product_id = product_info.get("product_id", "unknown")
            category_id = product_info.get("category_id", "unknown")

            device_info = DeviceInfo(
                identifiers={(const.BRIGHTEMS, f"{product_id}_{address}")},
                name=f"BrightEMS {product_id}",
                manufacturer="BrightEMS / Sydpower",
                model=product_id,
                sw_version=self._get_firmware_version(product_info),
            )

            self._device_info[address] = device_info

            # Notify handlers
            if address in self._device_handlers:
                self._device_handlers[address](device_info)

    def _get_product_key_from_uuid(self, service_uuid: str) -> Optional[str]:
        """Get product key from service UUID.

        Args:
            service_uuid: The service UUID to look up

        Returns:
            Product key if found, None otherwise
        """
        uuid_lower = service_uuid.lower()

        # Check against known BrightEMS UUIDs
        for product_key in PRODUCTS:
            product_uuid = product_key.split("_", 1)[0].lower()
            if product_uuid == uuid_lower:
                return product_key

        return None

    def _get_firmware_version(self, product_info: dict) -> str:
        """Get firmware version from product info.

        Args:
            product_info: Product information dictionary

        Returns:
            Firmware version string
        """
        return product_info.get("protocol_version", 0)

    def register_device_handler(
        self,
        address: str,
        handler: Callable[[DeviceInfo], None],
    ) -> None:
        """Register a device handler.

        Args:
            address: Device MAC address
            handler: Handler function to call when device is found
        """
        self._device_handlers[address] = handler

    async def connect_to_device(
        self,
        address: str,
        service_uuid: str,
    ) -> Optional[Any]:
        """Connect to a BrightEMS device.

        Args:
            address: Device MAC address
            service_uuid: Service UUID to connect to

        Returns:
            Connection object if successful, None otherwise
        """
        _LOGGER.info(f"Connecting to {address} on {service_uuid}")

        try:
            # TODO: Implement actual BLE connection
            # This would use the Bluetooth integration's connection methods
            connection = await self._perform_ble_connect(address, service_uuid)
            return connection
        except Exception as e:
            _LOGGER.error(f"Failed to connect to {address}: {e}")
            return None

    async def _perform_ble_connect(
        self,
        address: str,
        service_uuid: str,
    ) -> Any:
        """Perform the actual BLE connection.

        Args:
            address: Device MAC address
            service_uuid: Service UUID to connect to

        Returns:
            Connection object
        """
        # Placeholder for actual BLE connection
        # In a real implementation, this would use:
        # - self.manager.async_connect()
        # - Home Assistant's BLE client
        pass

    async def disconnect(self) -> None:
        """Disconnect from all devices."""
        _LOGGER.info("Disconnecting from all devices")
        self._device_handlers.clear()
        self._ble_services.clear()


class BrightEMSBluetoothTracker:
    """Track BrightEMS Bluetooth devices for Home Assistant."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the tracker."""
        self.hass = hass
        self.handler: Optional[BluetoothHandler] = None
        self._devices: dict[str, DeviceInfo] = {}

    async def async_setup(self) -> None:
        """Set up the Bluetooth tracker."""
        self.handler = BluetoothHandler(self.hass)
        await self.handler.async_setup()

        # Set up callbacks for device discovery
        self.hass.bus.async_listen(
            EVENT_HOMEASSISTANT_STARTED,
            self._on_home_assistant_started,
        )

    async def _on_home_assistant_started(self, event: Any) -> None:
        """Handle Home Assistant startup."""
        _LOGGER.info("Home Assistant started, starting BrightEMS device discovery")
        await self._discover_devices()

    async def _discover_devices(self) -> None:
        """Discover available BrightEMS devices."""
        _LOGGER.info("Discovering BrightEMS devices")

        # Use the product catalog to build discovery matchers
        for product_key in PRODUCTS:
            product_info = PRODUCTS[product_key]
            protocol_version = product_info.get("protocol_version", 0)

            # Build discovery matchers for each product
            if product_info.get("service_uuid"):
                matcher = BluetoothMatcher(
                    address=[product_key.split("_", 1)[0].lower()],
                    service_uuid=[product_info["service_uuid"]],
                )

                # Register for discovery
                self.hass.components.bluetooth.async_register_callback(
                    self._on_device_discovered,
                    callback=True,
                    rules=[matcher],
                )

    @callback
    def _on_device_discovered(self, service_data: dict) -> None:
        """Handle device discovery callback."""
        _LOGGER.info(f"Device discovered: {service_data}")

    async def async_stop(self) -> None:
        """Stop the Bluetooth tracker."""
        if self.handler:
            await self.handler.disconnect()
