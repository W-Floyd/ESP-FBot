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

from .const import (
    AC_CHARGE_LIMITS,
    DOMAIN,
    KEY_AC_ACTIVE,
    KEY_AC_CHARGE_LIMIT,
    KEY_AC_IN_FREQUENCY,
    KEY_AC_INPUT_POWER,
    KEY_AC_OUT_FREQUENCY,
    KEY_AC_OUT_VOLTAGE,
    KEY_AC_SILENT,
    KEY_BATTERY_PERCENT,
    KEY_BATTERY_S1_CONNECTED,
    KEY_BATTERY_S1_PERCENT,
    KEY_BATTERY_S2_CONNECTED,
    KEY_BATTERY_S2_PERCENT,
    KEY_CHARGE_LEVEL,
    KEY_DC_ACTIVE,
    KEY_DC_INPUT_POWER,
    KEY_INPUT_POWER,
    KEY_KEY_SOUND,
    KEY_LIGHT_ACTIVE,
    KEY_LIGHT_MODE,
    KEY_OUTPUT_POWER,
    KEY_REMAINING_TIME,
    KEY_SYSTEM_POWER,
    KEY_THRESHOLD_CHARGE,
    KEY_THRESHOLD_DISCHARGE,
    KEY_TIME_TO_FULL,
    KEY_TOTAL_POWER,
    KEY_USB_A1_POWER,
    KEY_USB_A2_POWER,
    KEY_USB_ACTIVE,
    KEY_USB_C1_POWER,
    KEY_USB_C2_POWER,
    KEY_USB_C3_POWER,
    KEY_USB_C4_POWER,
    LIGHT_MODES,
    NOTIFY_CHAR_UUID,
    REG_AC_CHARGE_LIMIT,
    REG_AC_SILENT_CONTROL,
    REG_KEY_SOUND,
    REG_LIGHT_CONTROL,
    REG_THRESHOLD_CHARGE,
    REG_THRESHOLD_DISCHARGE,
    REG_USB_A1_OUT,
    REG_USB_A2_OUT,
    REG_USB_C1_OUT,
    REG_USB_C2_OUT,
    REG_USB_C3_OUT,
    REG_USB_C4_OUT,
    STATE_AC_BIT,
    STATE_DC_BIT,
    STATE_LIGHT_BIT,
    STATE_USB_BIT,
    WRITE_CHAR_UUID,
)

_LOGGER = logging.getLogger(__name__)

_POLLING_INTERVAL = timedelta(seconds=5)
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


def _build_read_status() -> bytes:
    """Request input registers (function code 0x04): 80 registers from address 0."""
    return _frame(bytes([0x11, 0x04, 0x00, 0x00, 0x00, 0x50]))


def _build_read_settings() -> bytes:
    """Request holding registers (function code 0x03): 80 registers from address 0."""
    return _frame(bytes([0x11, 0x03, 0x00, 0x00, 0x00, 0x50]))


def _build_write_command(reg: int, value: int) -> bytes:
    """Write single holding register (function code 0x06)."""
    return _frame(
        bytes(
            [
                0x11,
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


def _parse_status(data: bytes) -> dict | None:
    """Parse a 0x04 (Read Input Registers) response into a data dict."""
    if len(data) < 6 or data[0] != 0x11 or data[1] != 0x04:
        return None

    battery_s1_raw = _get_reg(data, 53)
    battery_s2_raw = _get_reg(data, 55)

    # Extra batteries report 0 when disconnected; subtract 1 to normalise range.
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

    charge_level_raw = _get_reg(data, 2)
    charge_level_watts = (
        (300 + (charge_level_raw - 1) * 200) if 1 <= charge_level_raw <= 5 else 0
    )

    state_flags = _get_reg(data, 41)

    return {
        KEY_BATTERY_PERCENT: _get_reg(data, 56) / 10.0,
        KEY_BATTERY_S1_PERCENT: battery_s1_pct,
        KEY_BATTERY_S2_PERCENT: battery_s2_pct,
        KEY_BATTERY_S1_CONNECTED: battery_s1_raw > 0,
        KEY_BATTERY_S2_CONNECTED: battery_s2_raw > 0,
        KEY_AC_INPUT_POWER: _get_reg(data, 3),
        KEY_DC_INPUT_POWER: _get_reg(data, 4),
        KEY_INPUT_POWER: _get_reg(data, 6),
        KEY_TOTAL_POWER: _get_reg(data, 20),
        KEY_SYSTEM_POWER: _get_reg(data, 21),
        KEY_OUTPUT_POWER: _get_reg(data, 39),
        KEY_AC_OUT_VOLTAGE: _get_reg(data, 18) * 0.1,
        KEY_AC_OUT_FREQUENCY: _get_reg(data, 19) * 0.1,
        KEY_AC_IN_FREQUENCY: _get_reg(data, 22) * 0.01,
        KEY_TIME_TO_FULL: _get_reg(data, 58),
        KEY_REMAINING_TIME: _get_reg(data, 59),
        KEY_USB_A1_POWER: _get_reg(data, REG_USB_A1_OUT) * 0.1,
        KEY_USB_A2_POWER: _get_reg(data, REG_USB_A2_OUT) * 0.1,
        KEY_USB_C1_POWER: _get_reg(data, REG_USB_C1_OUT) * 0.1,
        KEY_USB_C2_POWER: _get_reg(data, REG_USB_C2_OUT) * 0.1,
        KEY_USB_C3_POWER: _get_reg(data, REG_USB_C3_OUT) * 0.1,
        KEY_USB_C4_POWER: _get_reg(data, REG_USB_C4_OUT) * 0.1,
        KEY_CHARGE_LEVEL: charge_level_watts,
        KEY_USB_ACTIVE: bool(state_flags & STATE_USB_BIT),
        KEY_DC_ACTIVE: bool(state_flags & STATE_DC_BIT),
        KEY_AC_ACTIVE: bool(state_flags & STATE_AC_BIT),
        KEY_LIGHT_ACTIVE: bool(state_flags & STATE_LIGHT_BIT),
    }


def _parse_settings(data: bytes) -> dict | None:
    """Parse a 0x03 (Read Holding Registers) response into a data dict."""
    if len(data) < 6 or data[0] != 0x11 or data[1] != 0x03:
        return None

    light_mode_raw = _get_reg(data, REG_LIGHT_CONTROL)
    light_mode = (
        LIGHT_MODES[light_mode_raw]
        if light_mode_raw < len(LIGHT_MODES)
        else LIGHT_MODES[0]
    )

    ac_charge_limit_raw = _get_reg(data, REG_AC_CHARGE_LIMIT)
    ac_charge_limit = (
        AC_CHARGE_LIMITS[ac_charge_limit_raw - 1]
        if 1 <= ac_charge_limit_raw <= len(AC_CHARGE_LIMITS)
        else AC_CHARGE_LIMITS[0]
    )

    return {
        KEY_AC_SILENT: _get_reg(data, REG_AC_SILENT_CONTROL) == 1,
        KEY_KEY_SOUND: _get_reg(data, REG_KEY_SOUND) == 1,
        KEY_LIGHT_MODE: light_mode,
        KEY_AC_CHARGE_LIMIT: ac_charge_limit,
        KEY_THRESHOLD_DISCHARGE: _get_reg(data, REG_THRESHOLD_DISCHARGE) / 10.0,
        KEY_THRESHOLD_CHARGE: _get_reg(data, REG_THRESHOLD_CHARGE) / 10.0,
    }


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class FbotCoordinator(DataUpdateCoordinator[dict]):
    """Manages the BLE connection and data for a single Fbot device."""

    def __init__(self, hass: HomeAssistant, address: str, name: str) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=None)
        self._address = address
        self._device_name = name
        self._client: BleakClient | None = None
        self._parsed_data: dict = {}
        self._cancel_bluetooth_callback: Callable[[], None] | None = None
        self._cancel_status_poll: Callable[[], None] | None = None
        self._cancel_settings_poll: Callable[[], None] | None = None
        self._connecting = False
        self._last_disconnect_time: float = 0.0
        self._backoff_exponent: int = 1
        self._connection_cooldown_seconds: float = 5.0
        self._backoff_multiplier: float = 2.0
        self._max_backoff_seconds: float = 60.0

    @property
    def address(self) -> str:
        return self._address

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_start(self) -> None:
        """Attempt initial connection with retry loop for robust connection."""
        max_retries = 3
        initial_retry_interval = 2.0
        for attempt in range(1, max_retries + 1):
            ble_device = bluetooth.async_ble_device_from_address(
                self.hass, self._address, connectable=True
            )
            if ble_device is not None:
                try:
                    await self._async_connect(ble_device)
                    if self.is_connected:
                        _LOGGER.info(
                            "Successfully connected to Fbot %s on attempt %d",
                            self._address,
                            attempt,
                        )
                        return
                except Exception as ex:
                    _LOGGER.error(
                        "Attempt %d failed to connect to Fbot %s: %s",
                        attempt,
                        self._address,
                        ex,
                    )
            else:
                _LOGGER.warning(
                    "Attempt %d: Fbot %s not in range, waiting for advertisement",
                    attempt,
                    self._address,
                )
            if attempt < max_retries:
                await asyncio.sleep(initial_retry_interval)
        _LOGGER.error(
            "Failed to connect to Fbot %s after %d attempts. "
            "Device may be out of range or busy.",
            self._address,
            max_retries,
        )

    async def async_stop(self) -> None:
        """Disconnect and cancel all callbacks."""
        self._cancel_all_callbacks()
        self._last_disconnect_time = 0.0
        self._backoff_exponent = 1
        self._connection_cooldown_seconds = 5.0
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
        """Connect to the Fbot device with explicit timeout handling."""
        if self._connecting or self.is_connected:
            return

        self._connecting = True
        connect_timeout = 10.0  # Increased from default to give device more time

        try:
            _LOGGER.debug(
                "Connecting to Fbot %s (timeout: %.1fs)", self._address, connect_timeout
            )
            client = await establish_connection(
                BleakClientWithServiceCache,
                ble_device,
                self._device_name,
                disconnected_callback=self._async_on_disconnect,
                ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                    self.hass, self._address, connectable=True
                ),
                timeout=connect_timeout,
            )
            self._client = client
            await client.start_notify(NOTIFY_CHAR_UUID, self._async_on_notification)
            _LOGGER.info("Connected to Fbot %s", self._address)

            # Reset backoff on successful connection
            self._reset_backoff()

            # Cancel any pending advertisement listener now that we're connected
            if self._cancel_bluetooth_callback is not None:
                self._cancel_bluetooth_callback()
                self._cancel_bluetooth_callback = None

            # Fetch initial status and settings, then start periodic polling
            await self._async_send_status_request()
            await self._async_send_settings_request()
            self._start_polls()
            _LOGGER.debug(
                "Fbot %s: initial status/settings requests sent", self._address
            )
        except asyncio.TimeoutError as ex:
            _LOGGER.error(
                "Connection to Fbot %s timed out after %.1fs. Device may be out of range.",
                self._address,
                connect_timeout,
            )
            self._handle_connection_failure(ex, "timeout")
        except Exception as ex:
            # Check for GATT connection failure specifically
            error_str = str(ex).lower()
            if (
                "esp_gatt_conn_fail_establish" in error_str
                or "connection failed to establish" in error_str
            ):
                _LOGGER.error(
                    "GATT connection error for Fbot %s: %s. Device may be busy or out of range.",
                    self._address,
                    ex,
                )
                self._handle_connection_failure(ex, "gatt_fail")
            else:
                _LOGGER.error("Failed to connect to Fbot %s: %s", self._address, ex)
                self._handle_connection_failure(ex, "other")
        finally:
            self._connecting = False

    def _handle_connection_failure(self, error: Exception, error_type: str) -> None:
        """Handle connection failure with appropriate backoff."""
        # Apply exponential backoff before re-registering for connection
        self._backoff_exponent = min(
            self._backoff_exponent + 1,
            int(self._max_backoff_seconds / self._connection_cooldown_seconds) + 1,
        )
        backoff_seconds = min(
            self._connection_cooldown_seconds
            * self._backoff_multiplier ** (self._backoff_exponent - 1),
            self._max_backoff_seconds,
        )
        self._connection_cooldown_seconds = backoff_seconds

        if error_type == "gatt_fail":
            # For GATT failures, use longer backoff and log more details
            self._connection_cooldown_seconds = max(backoff_seconds, 15.0)
            _LOGGER.warning(
                "GATT connection failure for Fbot %s after %d attempts. "
                "Next retry in %.1fs. Original error: %s",
                self._address,
                self._backoff_exponent,
                self._connection_cooldown_seconds,
                error,
            )
        else:
            _LOGGER.warning(
                "Failed to connect to Fbot %s after %d attempts (type: %s). "
                "Next retry in %.1fs. Original error: %s",
                self._address,
                self._backoff_exponent,
                error_type,
                backoff_seconds,
                error,
            )

        self._register_advertisement_listener()

    @callback
    def _async_on_disconnect(self, _client: BleakClient) -> None:
        """Called by bleak when the connection drops."""
        _LOGGER.warning("Fbot %s disconnected", self._address)
        self._client = None
        self._stop_polls()
        # Record disconnect time and apply backoff
        self._last_disconnect_time = asyncio.get_event_loop().time()
        self._parsed_data = {}
        self.async_set_updated_data(self._parsed_data)
        # Only register for reconnection if backoff period has passed
        if self._should_attempt_reconnect():
            self._register_advertisement_listener()

    def _register_advertisement_listener(self) -> None:
        """Register a BLE advertisement listener to reconnect when device is seen."""
        if self._cancel_bluetooth_callback is not None:
            return  # Already registered
        if not self._should_attempt_reconnect():
            _LOGGER.debug(
                "Fbot %s: skipping reconnection (backoff not expired)", self._address
            )
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
        """Device was seen in a BLE scan — attempt reconnection."""
        if self.is_connected or self._connecting:
            return
        # Reset backoff when device is seen
        self._connection_cooldown_seconds = 5.0
        _LOGGER.debug("Fbot %s advertisement seen, attempting reconnect", self._address)
        self.hass.async_create_task(self._async_connect(service_info.device))
        # Reset backoff when device is seen
        self._reset_backoff()

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

    def _should_attempt_reconnect(self) -> bool:
        """Check if backoff period has passed since last disconnect."""
        if self._last_disconnect_time == 0.0:
            return True
        elapsed = asyncio.get_event_loop().time() - self._last_disconnect_time
        return elapsed >= self._connection_cooldown_seconds

    def _reset_backoff(self) -> None:
        """Reset backoff state on successful connection."""
        self._backoff_exponent = 1
        self._connection_cooldown_seconds = 5.0

    async def _async_send_status_request(self) -> None:
        if not self.is_connected:
            return
        try:
            await self._client.write_gatt_char(  # type: ignore[union-attr]
                WRITE_CHAR_UUID, _build_read_status(), response=False
            )
        except Exception as ex:
            _LOGGER.debug("Error sending status request: %s", ex)
            # Reconnect on error
            self._async_on_disconnect(None)

    async def _async_send_settings_request(self) -> None:
        if not self.is_connected:
            return
        try:
            await self._client.write_gatt_char(  # type: ignore[union-attr]
                WRITE_CHAR_UUID, _build_read_settings(), response=False
            )
        except Exception as ex:
            _LOGGER.debug("Error sending settings request: %s", ex)
            # Reconnect on error
            self._async_on_disconnect(None)

    # ------------------------------------------------------------------
    # Notification parsing
    # ------------------------------------------------------------------

    @callback
    def _async_on_notification(self, _sender, data: bytearray) -> None:
        raw = bytes(data)
        if len(raw) < 6 or raw[0] != 0x11:
            return
        if raw[1] == 0x04:
            parsed = _parse_status(raw)
        elif raw[1] == 0x03:
            parsed = _parse_settings(raw)
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
                WRITE_CHAR_UUID, _build_write_command(reg, value), response=False
            )
            # Small delay to let device process the command before next poll
            await asyncio.sleep(0.2)
        except Exception as ex:
            raise HomeAssistantError(f"Failed to send command: {ex}") from ex

    async def _async_send_settings_refresh_internal(self) -> None:
        """Internal method for settings refresh without connection check."""
        if not self.is_connected:
            return
        try:
            await self._client.write_gatt_char(  # type: ignore[union-attr]
                WRITE_CHAR_UUID, _build_read_settings(), response=False
            )
        except Exception:
            # Reconnect on error
            self._async_on_disconnect(None)

    async def async_send_settings_refresh(self) -> None:
        """Request a fresh settings read from the device."""
        if self.is_connected:
            await self._async_send_settings_refresh_internal()
        else:
            _LOGGER.warning(
                "Cannot refresh settings: Fbot %s is not connected", self._address
            )
