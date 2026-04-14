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
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
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
    WRITE_CHAR_UUID,
)

_LOGGER = logging.getLogger(__name__)

_POLLING_INTERVAL = timedelta(seconds=2)
_SETTINGS_INTERVAL = timedelta(seconds=60)

# Hardcoded input-register indices for per-port USB/DC power readings.
_REG_USB_A1_OUT = 30
_REG_USB_A2_OUT = 31
_REG_USB_C1_OUT = 34
_REG_USB_C2_OUT = 35
_REG_USB_C3_OUT = 36
_REG_USB_C4_OUT = 37


# ---------------------------------------------------------------------------
# Protocol helpers
# ---------------------------------------------------------------------------


def _crc16_modbus(data: bytes) -> int:
    """CRC-16/Modbus — polynomial 0xA001, initial value 0xFFFF."""
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
    """Append CRC little-endian (low byte first) as the APK does."""
    crc = _crc16_modbus(payload)
    return payload + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def _build_read_input(address: int, count: int) -> bytes:
    """Function 0x04 — read *count* input registers starting at 0."""
    return _frame(bytes([address, 0x04, 0x00, 0x00, (count >> 8) & 0xFF, count & 0xFF]))


def _build_read_holding(address: int, count: int) -> bytes:
    """Function 0x03 — read *count* holding registers starting at 0."""
    return _frame(bytes([address, 0x03, 0x00, 0x00, (count >> 8) & 0xFF, count & 0xFF]))


def _build_write_single(address: int, reg: int, value: int) -> bytes:
    """Function 0x06 — write one holding register (protocol v0)."""
    return _frame(
        bytes([
            address, 0x06,
            (reg >> 8) & 0xFF, reg & 0xFF,
            (value >> 8) & 0xFF, value & 0xFF,
        ])
    )


def _build_write_multi(address: int, start_reg: int, values: list[int]) -> bytes:
    """Write one or more holding registers (protocol v1+).

    Matches the APK's getWriteModbusCRCLowFront_new():
      byte 0: address
      byte 1: 0x06 (reused function code for this vendor extension)
      byte 2: start register (single byte)
      bytes 3-4: count of registers (big-endian)
      bytes 5+: register values (each big-endian 16-bit)
    """
    count = len(values)
    payload = bytearray([address, 0x06, start_reg & 0xFF, (count >> 8) & 0xFF, count & 0xFF])
    for v in values:
        payload.append((v >> 8) & 0xFF)
        payload.append(v & 0xFF)
    return _frame(bytes(payload))


def _reg(data: bytes, idx: int) -> int:
    """Extract register *idx* (0-based) from a device response.

    The BrightEMS/Sydpower devices echo the full request header (address,
    function, start_hi, start_lo, count_hi, count_lo) before the register
    data, so register values start at byte offset 6.
    """
    offset = 6 + idx * 2
    if offset + 1 >= len(data):
        return 0
    return (data[offset] << 8) | data[offset + 1]


def _parse_input(data: bytes, address: int, count: int) -> dict | None:
    """Parse a 0x04 (Read Input Registers) response.

    Produces raw 'i_{n}' keys for every register plus pre-computed
    human-readable telemetry keys for the hardcoded sensor platform.
    """
    if len(data) < 8 or data[0] != address or data[1] != 0x04:
        return None

    result: dict = {f"i_{n}": _reg(data, n) for n in range(count)}

    # Battery pack presence and SOC for optional satellite packs.
    bat_s1_raw = result.get("i_53", 0)
    bat_s2_raw = result.get("i_55", 0)
    bat_s1_pct: float | None = (bat_s1_raw / 10.0 - 1.0) if bat_s1_raw > 0 else None
    bat_s2_pct: float | None = (bat_s2_raw / 10.0 - 1.0) if bat_s2_raw > 0 else None
    if bat_s1_pct is not None and not 0.0 <= bat_s1_pct <= 100.0:
        bat_s1_pct = None
    if bat_s2_pct is not None and not 0.0 <= bat_s2_pct <= 100.0:
        bat_s2_pct = None

    # Charge-level register encodes a discrete step (1–5) → watt value.
    charge_raw = result.get("i_2", 0)
    charge_watts = (300 + (charge_raw - 1) * 200) if 1 <= charge_raw <= 5 else 0

    result.update({
        KEY_BATTERY_PERCENT:    result.get("i_56", 0) / 10.0,
        KEY_BATTERY_S1_PERCENT: bat_s1_pct,
        KEY_BATTERY_S2_PERCENT: bat_s2_pct,
        KEY_BATTERY_S1_CONNECTED: bat_s1_raw > 0,
        KEY_BATTERY_S2_CONNECTED: bat_s2_raw > 0,
        KEY_AC_INPUT_POWER:  result.get("i_3", 0),
        KEY_DC_INPUT_POWER:  result.get("i_4", 0),
        KEY_INPUT_POWER:     result.get("i_6", 0),
        KEY_TOTAL_POWER:     result.get("i_20", 0),
        KEY_SYSTEM_POWER:    result.get("i_21", 0),
        KEY_OUTPUT_POWER:    result.get("i_39", 0),
        KEY_AC_OUT_VOLTAGE:  result.get("i_18", 0) * 0.1,
        KEY_AC_OUT_FREQUENCY: result.get("i_19", 0) * 0.1,
        KEY_AC_IN_FREQUENCY: result.get("i_22", 0) * 0.01,
        KEY_TIME_TO_FULL:    result.get("i_58", 0),
        KEY_REMAINING_TIME:  result.get("i_59", 0),
        KEY_CHARGE_LEVEL:    charge_watts,
        KEY_USB_A1_POWER:    _reg(data, _REG_USB_A1_OUT) * 0.1,
        KEY_USB_A2_POWER:    _reg(data, _REG_USB_A2_OUT) * 0.1,
        KEY_USB_C1_POWER:    _reg(data, _REG_USB_C1_OUT) * 0.1,
        KEY_USB_C2_POWER:    _reg(data, _REG_USB_C2_OUT) * 0.1,
        KEY_USB_C3_POWER:    _reg(data, _REG_USB_C3_OUT) * 0.1,
        KEY_USB_C4_POWER:    _reg(data, _REG_USB_C4_OUT) * 0.1,
    })
    return result


def _parse_holding(data: bytes, address: int, count: int) -> dict | None:
    """Parse a 0x03 (Read Holding Registers) response.

    Produces raw 'h_{n}' keys for every register plus firmware-version keys.
    """
    if len(data) < 8 or data[0] != address or data[1] != 0x03:
        return None

    result: dict = {f"h_{n}": _reg(data, n) for n in range(count)}

    result.update({
        KEY_AC_VERSION:    result.get("h_47", 0),
        KEY_BMS_VERSION:   result.get("h_48", 0),
        KEY_PV_VERSION:    result.get("h_49", 0),
        KEY_PANEL_VERSION: result.get("h_50", 0),
    })
    return result


# Aliases used by apk_analysis/_smoke_test.py and any external callers.
_parse_status = _parse_input
_parse_settings = _parse_holding
_build_read_status = _build_read_input
_build_read_settings = _build_read_holding


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
        self._cancel_bt_cb: CALLBACK_TYPE | None = None
        self._cancel_unavailable_cb: CALLBACK_TYPE | None = None
        self._cancel_input_poll: CALLBACK_TYPE | None = None
        self._cancel_holding_poll: CALLBACK_TYPE | None = None
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
        """Register BLE callbacks and attempt initial connection.

        Both the advertisement callback and the unavailability tracker are
        registered once here and stay active for the lifetime of the entry.
        The advertisement callback triggers reconnection whenever the device
        is seen in range; the unavailability tracker clears state when the
        BLE scanner has not seen the device for an extended period.
        """
        self._cancel_bt_cb = bluetooth.async_register_callback(
            self.hass,
            self._on_ble_advertisement,
            BluetoothCallbackMatcher(address=self._address, connectable=True),
            BluetoothScanningMode.ACTIVE,
        )
        self._cancel_unavailable_cb = bluetooth.async_track_unavailable(
            self.hass,
            self._on_bt_unavailable,
            self._address,
            connectable=True,
        )
        await self._async_connect_if_available()

    async def async_stop(self) -> None:
        """Unregister callbacks, stop polls, and disconnect."""
        if self._cancel_bt_cb:
            self._cancel_bt_cb()
            self._cancel_bt_cb = None
        if self._cancel_unavailable_cb:
            self._cancel_unavailable_cb()
            self._cancel_unavailable_cb = None
        self._stop_polls()
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    async def _async_update_data(self) -> dict:
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
            _LOGGER.debug("Fbot %s not in range, waiting for advertisement", self._address)

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
                disconnected_callback=self._on_disconnect,
                ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                    self.hass, self._address, connectable=True
                ),
            )
            self._client = client
            await client.start_notify(NOTIFY_CHAR_UUID, self._on_notification)
            _LOGGER.info("Connected to Fbot %s", self._address)

            await self._send_input_request()
            await asyncio.sleep(0.5)
            await self._send_holding_request()

            if self.is_connected:
                self._start_polls()
        except Exception as ex:
            _LOGGER.warning("Failed to connect to Fbot %s: %s", self._address, ex)
        finally:
            self._connecting = False

    @callback
    def _on_disconnect(self, _client: BleakClient) -> None:
        """Handle an unexpected BLE disconnection.

        Polls are stopped and data is cleared so entities show as unavailable.
        The always-active advertisement callback will trigger a reconnect the
        next time the device is seen in range.
        """
        _LOGGER.warning("Fbot %s disconnected", self._address)
        self._client = None
        self._stop_polls()
        self._parsed_data = {}
        self.async_set_updated_data(self._parsed_data)

    @callback
    def _on_ble_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        """Handle a BLE advertisement — reconnect if currently disconnected."""
        if self.is_connected or self._connecting:
            return
        self.hass.async_create_task(self._async_connect(service_info.device))

    @callback
    def _on_bt_unavailable(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Handle the device going out of BLE scanner range.

        The scanner has not seen this address for an extended period; clear all
        state so entities report unavailable, and forcefully close any stale
        connection.
        """
        _LOGGER.debug("Fbot %s is unavailable (out of range)", self._address)
        self._stop_polls()
        self._parsed_data = {}
        self.async_set_updated_data(self._parsed_data)
        if self._client:
            # Fire-and-forget: if it fails the connection was already dead.
            self.hass.async_create_task(self._async_force_disconnect())

    async def _async_force_disconnect(self) -> None:
        if self._client:
            try:
                await self._client.disconnect()
            except Exception:
                pass
            self._client = None

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _start_polls(self) -> None:
        self._cancel_input_poll = async_track_time_interval(
            self.hass, self._schedule_input_poll, _POLLING_INTERVAL,
        )
        self._cancel_holding_poll = async_track_time_interval(
            self.hass, self._schedule_holding_poll, _SETTINGS_INTERVAL,
        )

    @callback
    def _schedule_input_poll(self, _now=None) -> None:
        self.hass.async_create_task(self._send_input_request())

    @callback
    def _schedule_holding_poll(self, _now=None) -> None:
        self.hass.async_create_task(self._send_holding_request())

    def _stop_polls(self) -> None:
        if self._cancel_input_poll:
            self._cancel_input_poll()
            self._cancel_input_poll = None
        if self._cancel_holding_poll:
            self._cancel_holding_poll()
            self._cancel_holding_poll = None

    # ------------------------------------------------------------------
    # Raw BLE I/O
    # ------------------------------------------------------------------

    async def _send_input_request(self) -> None:
        if not self.is_connected:
            return
        try:
            await self._client.write_gatt_char(  # type: ignore[union-attr]
                WRITE_CHAR_UUID,
                _build_read_input(self._profile.modbus_address, self._profile.modbus_count),
                response=False,
            )
        except Exception as ex:
            _LOGGER.debug("Error sending input-register request: %s", ex)

    async def _send_holding_request(self) -> None:
        if not self.is_connected:
            return
        try:
            await self._client.write_gatt_char(  # type: ignore[union-attr]
                WRITE_CHAR_UUID,
                _build_read_holding(self._profile.modbus_address, self._profile.modbus_count),
                response=False,
            )
        except Exception as ex:
            _LOGGER.debug("Error sending holding-register request: %s", ex)

    # ------------------------------------------------------------------
    # Notification parsing
    # ------------------------------------------------------------------

    @callback
    def _on_notification(self, _sender, data: bytearray) -> None:
        raw = bytes(data)
        addr = self._profile.modbus_address
        count = self._profile.modbus_count
        if len(raw) < 5 or raw[0] != addr:
            return
        if raw[1] == 0x04:
            parsed = _parse_input(raw, addr, count)
        elif raw[1] == 0x03:
            parsed = _parse_holding(raw, addr, count)
        else:
            return
        if parsed:
            self._parsed_data = {**self._parsed_data, **parsed}
            self.async_set_updated_data(self._parsed_data)

    # ------------------------------------------------------------------
    # Control commands (public API for entity platforms)
    # ------------------------------------------------------------------

    async def async_send_command(self, reg: int, value: int) -> None:
        """Write a single holding register.

        v1+ devices use the multi-register frame even for a single register;
        v0 devices use the standard Modbus write-single-register frame.
        """
        if not self.is_connected:
            raise HomeAssistantError("Fbot is not connected")
        addr = self._profile.modbus_address
        frame = (
            _build_write_multi(addr, reg, [value])
            if self._profile.protocol_version >= 1
            else _build_write_single(addr, reg, value)
        )
        try:
            await self._client.write_gatt_char(  # type: ignore[union-attr]
                WRITE_CHAR_UUID, frame, response=False
            )
        except Exception as ex:
            raise HomeAssistantError(f"Failed to send command: {ex}") from ex
        # Restart polls so we get a fresh read promptly.
        self._stop_polls()
        self._start_polls()

    async def async_send_multi_command(self, start_reg: int, values: list[int]) -> None:
        """Write multiple consecutive holding registers.

        v1+ uses a single multi-register frame; v0 falls back to sequential
        single-register writes.
        """
        if not self.is_connected:
            raise HomeAssistantError("Fbot is not connected")
        addr = self._profile.modbus_address
        try:
            if self._profile.protocol_version >= 1:
                await self._client.write_gatt_char(  # type: ignore[union-attr]
                    WRITE_CHAR_UUID,
                    _build_write_multi(addr, start_reg, values),
                    response=False,
                )
            else:
                for offset, value in enumerate(values):
                    await self._client.write_gatt_char(  # type: ignore[union-attr]
                        WRITE_CHAR_UUID,
                        _build_write_single(addr, start_reg + offset, value),
                        response=False,
                    )
        except Exception as ex:
            raise HomeAssistantError(f"Failed to send multi-register command: {ex}") from ex
        self._stop_polls()
        self._start_polls()

    async def async_refresh_holding(self) -> None:
        """Request a fresh holding-register read from the device."""
        await self._send_holding_request()
