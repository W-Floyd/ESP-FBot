"""BLE coordinator for the Fbot integration."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta

from bleak import BleakClient
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .catalog import DeviceProfile
from .const import (
    DOMAIN,
    KEY_AC_IN_FREQUENCY,
    KEY_AC_INPUT_POWER,
    KEY_AC_OUT_FREQUENCY,
    KEY_AC_OUT_VOLTAGE,
    KEY_AC_VERSION,
    KEY_BATTERY_PERCENT,
    KEY_BATTERY_S1_CONNECTED,
    KEY_BATTERY_S1_PERCENT,
    KEY_BATTERY_S2_CONNECTED,
    KEY_BATTERY_S2_PERCENT,
    KEY_BMS_VERSION,
    KEY_CHARGE_LEVEL,
    KEY_DC_INPUT_POWER,
    KEY_INPUT_POWER,
    KEY_OUTPUT_POWER,
    KEY_PANEL_VERSION,
    KEY_PV_VERSION,
    KEY_REMAINING_TIME,
    KEY_SYSTEM_POWER,
    KEY_TIME_TO_FULL,
    KEY_TOTAL_POWER,
    KEY_USB_A1_POWER,
    KEY_USB_A2_POWER,
    KEY_USB_C1_POWER,
    KEY_USB_C2_POWER,
    KEY_USB_C3_POWER,
    KEY_USB_C4_POWER,
    NOTIFY_CHAR_UUID,
    REG_USB_A1_OUT,
    REG_USB_A2_OUT,
    REG_USB_C1_OUT,
    REG_USB_C2_OUT,
    REG_USB_C3_OUT,
    REG_USB_C4_OUT,
    WRITE_CHAR_UUID,
)

_LOGGER = logging.getLogger(__name__)

_POLLING_INTERVAL = timedelta(seconds=2)
_SETTINGS_INTERVAL = timedelta(seconds=60)


# ---------------------------------------------------------------------------
# Protocol helpers
# ---------------------------------------------------------------------------


def _crc16_modbus(data: bytes) -> int:
    """CRC-16 Modbus variant (polynomial 0xA001, initial value 0xFFFF)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


def _frame(payload: bytes) -> bytes:
    crc = _crc16_modbus(payload)
    return payload + bytes([(crc >> 8) & 0xFF, crc & 0xFF])


def _build_read_status(address: int, count: int) -> bytes:
    """Request input registers (function code 0x04): *count* registers from address 0."""
    return _frame(bytes([address, 0x04, 0x00, 0x00, (count >> 8) & 0xFF, count & 0xFF]))


def _build_read_settings(address: int, count: int) -> bytes:
    """Request holding registers (function code 0x03): *count* registers from address 0."""
    return _frame(bytes([address, 0x03, 0x00, 0x00, (count >> 8) & 0xFF, count & 0xFF]))


def _build_write_command(address: int, reg: int, value: int) -> bytes:
    """Write single holding register (function code 0x06)."""
    return _frame(
        bytes(
            [
                address,
                0x06,
                (reg >> 8) & 0xFF,
                reg & 0xFF,
                (value >> 8) & 0xFF,
                value & 0xFF,
            ]
        )
    )


def _get_reg(data: bytes, idx: int) -> int:
    """Extract a 16-bit big-endian register value. Registers start at byte offset 6."""
    offset = 6 + idx * 2
    if offset + 1 >= len(data):
        return 0
    return (data[offset] << 8) | data[offset + 1]


def _parse_status(data: bytes, address: int = 0x11, count: int = 80) -> dict | None:
    """Parse a 0x04 (Read Input Registers) response.

    Stores raw input registers as 'i_{idx}' keys for catalog-driven entities,
    plus computed passive-telemetry keys for hardcoded sensor entities.
    """
    if len(data) < 6 or data[0] != address or data[1] != 0x04:
        return None

    # Raw register values — consumed by catalog-driven switch/sensor entities.
    result: dict = {f"i_{idx}": _get_reg(data, idx) for idx in range(count)}

    # Hardcoded passive telemetry ─────────────────────────────────────────────
    battery_s1_raw = result.get("i_53", 0)
    battery_s2_raw = result.get("i_55", 0)

    battery_s1_pct: float | None = (
        battery_s1_raw / 10.0 - 1.0 if battery_s1_raw > 0 else None
    )
    battery_s2_pct: float | None = (
        battery_s2_raw / 10.0 - 1.0 if battery_s2_raw > 0 else None
    )
    if battery_s1_pct is not None and not 0.0 <= battery_s1_pct <= 100.0:
        battery_s1_pct = None
    if battery_s2_pct is not None and not 0.0 <= battery_s2_pct <= 100.0:
        battery_s2_pct = None

    charge_level_raw = result.get("i_2", 0)
    charge_level_watts = (
        (300 + (charge_level_raw - 1) * 200) if 1 <= charge_level_raw <= 5 else 0
    )

    result.update(
        {
            KEY_BATTERY_PERCENT: result.get("i_56", 0) / 10.0,
            KEY_BATTERY_S1_PERCENT: battery_s1_pct,
            KEY_BATTERY_S2_PERCENT: battery_s2_pct,
            KEY_BATTERY_S1_CONNECTED: battery_s1_raw > 0,
            KEY_BATTERY_S2_CONNECTED: battery_s2_raw > 0,
            KEY_AC_INPUT_POWER: result.get("i_3", 0),
            KEY_DC_INPUT_POWER: result.get("i_4", 0),
            KEY_INPUT_POWER: result.get("i_6", 0),
            KEY_TOTAL_POWER: result.get("i_20", 0),
            KEY_SYSTEM_POWER: result.get("i_21", 0),
            KEY_OUTPUT_POWER: result.get("i_39", 0),
            KEY_AC_OUT_VOLTAGE: result.get("i_18", 0) * 0.1,
            KEY_AC_OUT_FREQUENCY: result.get("i_19", 0) * 0.1,
            KEY_AC_IN_FREQUENCY: result.get("i_22", 0) * 0.01,
            KEY_TIME_TO_FULL: result.get("i_58", 0),
            KEY_REMAINING_TIME: result.get("i_59", 0),
            KEY_CHARGE_LEVEL: charge_level_watts,
            KEY_USB_A1_POWER: _get_reg(data, REG_USB_A1_OUT) * 0.1,
            KEY_USB_A2_POWER: _get_reg(data, REG_USB_A2_OUT) * 0.1,
            KEY_USB_C1_POWER: _get_reg(data, REG_USB_C1_OUT) * 0.1,
            KEY_USB_C2_POWER: _get_reg(data, REG_USB_C2_OUT) * 0.1,
            KEY_USB_C3_POWER: _get_reg(data, REG_USB_C3_OUT) * 0.1,
            KEY_USB_C4_POWER: _get_reg(data, REG_USB_C4_OUT) * 0.1,
        }
    )
    return result


def _parse_settings(data: bytes, address: int = 0x11, count: int = 80) -> dict | None:
    """Parse a 0x03 (Read Holding Registers) response.

    Stores raw holding registers as 'h_{idx}' keys for catalog-driven select
    entities, plus hardcoded firmware version keys.
    """
    if len(data) < 6 or data[0] != address or data[1] != 0x03:
        return None

    # Raw register values — consumed by catalog-driven select entities.
    result: dict = {f"h_{idx}": _get_reg(data, idx) for idx in range(count)}

    # Hardcoded firmware version telemetry ────────────────────────────────────
    result.update(
        {
            KEY_AC_VERSION: result.get("h_47", 0),
            KEY_BMS_VERSION: result.get("h_48", 0),
            KEY_PV_VERSION: result.get("h_49", 0),
            KEY_PANEL_VERSION: result.get("h_50", 0),
        }
    )
    return result


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class FbotCoordinator(DataUpdateCoordinator[dict]):
    """Manages the BLE connection and data for a single Fbot device."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        name: str,
        profile: DeviceProfile,
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self._address = address
        self._device_name = name
        self._profile = profile
        self._client: BleakClient | None = None
        self._parsed_data: dict = {}
        self._cancel_bluetooth_callback: Callable[[], None] | None = None
        self._cancel_status_poll: Callable[[], None] | None = None
        self._cancel_settings_poll: Callable[[], None] | None = None
        self._connecting = False

    @property
    def address(self) -> str:
        return self._address

    @property
    def profile(self) -> DeviceProfile:
        return self._profile

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_start(self) -> None:
        """Attempt initial connection. Called after coordinator setup."""
        await self._async_connect_if_available()

    async def async_stop(self) -> None:
        """Disconnect and cancel all callbacks."""
        self._cancel_all_callbacks()
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    async def _async_update_data(self) -> dict:
        """Called by DataUpdateCoordinator on first refresh. Returns current data."""
        return self._parsed_data

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def _async_connect_if_available(self) -> None:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self._address, connectable=True
        )
        if ble_device is not None:
            await self._async_connect(ble_device)
        else:
            _LOGGER.debug(
                "Fbot %s not in range, waiting for advertisement", self._address
            )
            self._register_advertisement_listener()

    async def _async_connect(self, ble_device) -> None:
        if self._connecting or self.is_connected:
            return
        self._connecting = True
        try:
            _LOGGER.debug("Connecting to Fbot %s", self._address)
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self._device_name,
                disconnected_callback=self._async_on_disconnect,
                ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                    self.hass, self._address, connectable=True
                ),
            )
            self._client = client
            await client.start_notify(NOTIFY_CHAR_UUID, self._async_on_notification)
            _LOGGER.info("Connected to Fbot %s", self._address)

            if self._cancel_bluetooth_callback is not None:
                self._cancel_bluetooth_callback()
                self._cancel_bluetooth_callback = None

            await self._async_send_status_request()
            await asyncio.sleep(0.5)
            await self._async_send_settings_request()
            self._start_polls()
        except Exception as ex:
            _LOGGER.warning("Failed to connect to Fbot %s: %s", self._address, ex)
            self._register_advertisement_listener()
        finally:
            self._connecting = False

    @callback
    def _async_on_disconnect(self, _client: BleakClient) -> None:
        """Called by bleak when the connection drops."""
        _LOGGER.warning("Fbot %s disconnected", self._address)
        self._client = None
        self._stop_polls()
        self._parsed_data = {}
        self.async_set_updated_data(self._parsed_data)
        self._register_advertisement_listener()

    def _register_advertisement_listener(self) -> None:
        if self._cancel_bluetooth_callback is not None:
            return
        self._cancel_bluetooth_callback = bluetooth.async_register_callback(
            self.hass,
            self._async_on_ble_advertisement,
            BluetoothCallbackMatcher(address=self._address),
            BluetoothScanningMode.ACTIVE,
        )
        _LOGGER.debug("Registered BLE advertisement listener for %s", self._address)

    @callback
    def _async_on_ble_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        if self.is_connected or self._connecting:
            return
        _LOGGER.debug("Fbot %s advertisement seen, attempting reconnect", self._address)
        self.hass.async_create_task(self._async_connect(service_info.device))

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _start_polls(self) -> None:
        self._cancel_status_poll = async_track_time_interval(
            self.hass, self._schedule_status_poll, _POLLING_INTERVAL
        )
        self._cancel_settings_poll = async_track_time_interval(
            self.hass, self._schedule_settings_poll, _SETTINGS_INTERVAL
        )

    def _stop_polls(self) -> None:
        if self._cancel_status_poll is not None:
            self._cancel_status_poll()
            self._cancel_status_poll = None
        if self._cancel_settings_poll is not None:
            self._cancel_settings_poll()
            self._cancel_settings_poll = None

    def _cancel_all_callbacks(self) -> None:
        self._stop_polls()
        if self._cancel_bluetooth_callback is not None:
            self._cancel_bluetooth_callback()
            self._cancel_bluetooth_callback = None

    @callback
    def _schedule_status_poll(self, _now=None) -> None:
        self.hass.async_create_task(self._async_send_status_request())

    @callback
    def _schedule_settings_poll(self, _now=None) -> None:
        self.hass.async_create_task(self._async_send_settings_request())

    async def _async_send_status_request(self) -> None:
        if not self.is_connected:
            return
        try:
            await self._client.write_gatt_char(  # type: ignore[union-attr]
                WRITE_CHAR_UUID,
                _build_read_status(
                    self._profile.modbus_address, self._profile.modbus_count
                ),
                response=False,
            )
        except Exception as ex:
            _LOGGER.debug("Error sending status request: %s", ex)

    async def _async_send_settings_request(self) -> None:
        if not self.is_connected:
            return
        try:
            await self._client.write_gatt_char(  # type: ignore[union-attr]
                WRITE_CHAR_UUID,
                _build_read_settings(
                    self._profile.modbus_address, self._profile.modbus_count
                ),
                response=False,
            )
        except Exception as ex:
            _LOGGER.debug("Error sending settings request: %s", ex)

    # ------------------------------------------------------------------
    # Notification parsing
    # ------------------------------------------------------------------

    @callback
    def _async_on_notification(self, _sender, data: bytearray) -> None:
        raw = bytes(data)
        addr = self._profile.modbus_address
        count = self._profile.modbus_count
        if len(raw) < 6 or raw[0] != addr:
            return
        if raw[1] == 0x04:
            parsed = _parse_status(raw, addr, count)
        elif raw[1] == 0x03:
            parsed = _parse_settings(raw, addr, count)
        else:
            return
        if parsed:
            self._parsed_data = {**self._parsed_data, **parsed}
            self.async_set_updated_data(self._parsed_data)

    # ------------------------------------------------------------------
    # Control commands
    # ------------------------------------------------------------------

    async def async_send_command(self, reg: int, value: int) -> None:
        """Send a write-single-register command to the device."""
        if not self.is_connected:
            raise HomeAssistantError("Fbot is not connected")
        try:
            await self._client.write_gatt_char(  # type: ignore[union-attr]
                WRITE_CHAR_UUID,
                _build_write_command(self._profile.modbus_address, reg, value),
                response=False,
            )
        except Exception as ex:
            raise HomeAssistantError(f"Failed to send command: {ex}") from ex

        self._stop_polls()
        self._start_polls()

    async def async_send_settings_refresh(self) -> None:
        """Request a fresh settings read from the device."""
        await self._async_send_settings_request()
