"""
BLE Handler for BrightEMS devices.

This module handles all BLE communication with BrightEMS devices including
service discovery, reading/writing registers, and implementing the Modbus
protocol over BLE.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from bleak import BleakClient, BLEDevice
from bleak.backends.device import BLEDevice as BleakDevice
from bleak.exc import BleakError
from homeassistant.components.bluetooth import (
    BluetoothServiceData,
    async_get_bluetooth_manager,
)
from homeassistant.components.bluetooth.manager import BluetoothManager
from homeassistant.components.bluetooth.util import mac_bytes_to_address
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import BLE_SERVICE_UUIDS, CRC16_MODBUS_INIT, CRC16_MODBUS_POLY

_LOGGER = logging.getLogger(__name__)

# Service UUIDs for BrightEMS devices
MAIN_SERVICE_UUID = "0000A002-0000-1000-8000-00805F9B34FB"
WRITE_CHAR_UUID = "0000C304-0000-1000-8000-00805F9B34FB"
NOTIFY_CHAR_UUID = "0000C305-0000-1000-8000-00805F9B34FB"


def calculate_crc16_modbus(data: bytes) -> tuple[int, int]:
    """Calculate CRC-16/Modbus checksum.

    Args:
        data: Raw byte data to calculate CRC for

    Returns:
        Tuple of (low_byte, high_byte) for the checksum
    """
    crc = CRC16_MODBUS_INIT

    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ CRC16_MODBUS_POLY
            else:
                crc >>= 1

    return crc & 0xFF, (crc >> 8) & 0xFF


class BrightEMSConfigEntry:
    """Configuration entry for BrightEMS device."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the config entry.

        Args:
            hass: HomeAssistant instance
            entry: ConfigEntry from Home Assistant
        """
        self.hass = hass
        self.entry = entry
        self.address = entry.data.get("address", "")
        self.uuid = entry.data.get("uuid", "")
        self.product_id = entry.data.get("product_id", "")
        self.protocol_version = entry.data.get("protocol_version", 0)


class BleHandler:
    """Handler for BrightEMS BLE communication."""

    def __init__(self, hass: HomeAssistant):
        """Initialize the BLE handler.

        Args:
            hass: HomeAssistant instance
        """
        self.hass = hass
        self._client: Optional[BleakClient] = None
        self._connection: Optional[Any] = None
        self._notification_handler: Optional[Callable] = None
        self._is_connected: bool = False
        self._setup_done: bool = False

    async def async_setup(self) -> bool:
        """Set up the BLE handler.

        Returns:
            True if setup succeeded
        """
        _LOGGER.info("Setting up BrightEMS BLE handler")

        try:
            self._manager = await async_get_bluetooth_manager(self.hass)
            _LOGGER.debug(f"Bluetooth manager: {self._manager}")

            self._manager.async_register_callback(self._handle_ble_advertisement)

            await self._manager.async_start_scanning()
            self._setup_done = True

            _LOGGER.info("BLE handler setup complete")
            return True

        except Exception as e:
            _LOGGER.error(f"BLE setup failed: {e}")
            return False

    def _handle_ble_advertisement(
        self, service_data: dict[str, list[BluetoothServiceData]], connectable: bool
    ) -> None:
        """Handle incoming BLE advertisement.

        Args:
            service_data: Service data dictionary
            connectable: Whether device is connectable
        """
        for service_uuid, services in service_data.items():
            if service_uuid.lower() in [u.lower() for u in BLE_SERVICE_UUIDS]:
                for service in services:
                    self._process_advertisement(service_uuid, service, connectable)

    def _process_advertisement(
        self, service_uuid: str, data: BluetoothServiceData, connectable: bool
    ) -> None:
        """Process advertisement data.

        Args:
            service_uuid: Service UUID
            data: Service data
            connectable: Whether connectable
        """
        address = data.address
        _LOGGER.info(f"Found BrightEMS device at {address}: {service_uuid}")

    async def connect(self, address: str, service_uuid: str) -> Optional[BleakClient]:
        """Connect to a BrightEMS device.

        Args:
            address: Device MAC address
            service_uuid: Service UUID to connect to

        Returns:
            BleakClient if successful
        """
        _LOGGER.info(f"Connecting to {address} on {service_uuid}")

        try:
            self._client = BleakClient(address)
            await self._client.connect()
            self._is_connected = True

            _LOGGER.info(f"Connected to {address}")
            return self._client

        except BleakError as e:
            _LOGGER.error(f"BLE connection failed: {e}")
            return None

    async def disconnect(self) -> None:
        """Disconnect from the device."""
        if self._client and self._is_connected:
            await self._client.disconnect()
            self._is_connected = False
            self._client = None
            _LOGGER.info("Disconnected from device")

    async def read_register(self, address: int, count: int = 1) -> Optional[bytes]:
        """Read a register value from the device.

        Args:
            address: Register address
            count: Number of registers to read

        Returns:
            Register data or None if failed
        """
        if not self._is_connected:
            _LOGGER.warning("Not connected to device")
            return None

        # Build Modbus READ request
        request = await self._build_modbus_request(
            address=address, function_code=0x03, count=count
        )

        if not request:
            return None

        try:
            # Write request to BLE characteristic
            await self._client.write_char(WRITE_CHAR_UUID, request, response=True)

            # Read response from BLE characteristic
            # Note: This is simplified - in reality you'd use notifications
            response = bytearray()
            # ... implement proper response handling
            return bytes(response) if response else None

        except Exception as e:
            _LOGGER.error(f"Read register failed: {e}")
            return None

    async def write_register(self, address: int, value: int) -> bool:
        """Write a value to a register.

        Args:
            address: Register address
            value: Value to write

        Returns:
            True if successful
        """
        if not self._is_connected:
            _LOGGER.warning("Not connected to device")
            return False

        # Build Modbus WRITE request
        request = await self._build_modbus_request(
            address=address, function_code=0x06, value=value
        )

        if not request:
            return False

        try:
            await self._client.write_char(WRITE_CHAR_UUID, request, response=True)

            _LOGGER.debug(f"Written {value} to register 0x{address:02X}")
            return True

        except Exception as e:
            _LOGGER.error(f"Write register failed: {e}")
            return False

    async def _build_modbus_request(
        self,
        address: int = 0,
        function_code: int = 0x03,
        value: int = 0,
        count: int = 1,
    ) -> Optional[bytes]:
        """Build a Modbus request frame.

        Args:
            address: Device address
            function_code: Modbus function code
            value: Value for write operations
            count: Number of registers

        Returns:
            Modbus request frame or None
        """
        try:
            # Build frame
            frame = bytearray()

            if function_code in (0x03, 0x04):
                # Read request
                frame.extend([address])
                frame.extend([0x00, function_code])
                frame.extend([(address >> 8) & 0xFF, address & 0xFF])
                frame.extend([(count >> 8) & 0xFF, count & 0xFF])
            elif function_code in (0x06, 0x10):
                # Write single
                frame.extend([address])
                frame.extend([function_code])
                frame.extend([(address >> 8) & 0xFF, address & 0xFF])
                frame.extend([(value >> 8) & 0xFF, value & 0xFF])

            if frame:
                # Add CRC
                crc_low, crc_high = calculate_crc16_modbus(bytes(frame))
                frame.extend([crc_low, crc_high])

                return bytes(frame)

            return None

        except Exception as e:
            _LOGGER.error(f"Build modbus request failed: {e}")
            return None

    async def setup_notification_callback(
        self, handler: Callable[[bytes], None]
    ) -> None:
        """Setup notification callback for characteristic value changes.

        Args:
            handler: Callback function to handle notifications
        """
        self._notification_handler = handler

        try:
            await self._client.start_notify(NOTIFY_CHAR_UUID, handler)
        except Exception as e:
            _LOGGER.error(f"Failed to setup notification: {e}")
