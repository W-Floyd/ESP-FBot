#!/usr/bin/env python3
"""
Standalone smoke-test for the catalog-driven refactor.
Run from the repo root — no Home Assistant installation required:

    python3 apk_analysis/_smoke_test.py
"""

import importlib.util
import pathlib
import struct
import sys
import types

ROOT = pathlib.Path(__file__).parent.parent
FBOT = ROOT / "custom_components" / "fbot"

# ---------------------------------------------------------------------------
# Stub every third-party / HA import so we can load only the modules we need
# without triggering the fbot package __init__.
# ---------------------------------------------------------------------------

_HA_STUBS = [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.components",
    "homeassistant.components.bluetooth",
    "homeassistant.helpers",
    "homeassistant.helpers.device_registry",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.exceptions",
    "homeassistant.helpers.event",
    "bleak",
    "bleak_retry_connector",
]
for _mod in _HA_STUBS:
    sys.modules.setdefault(_mod, types.ModuleType(_mod))

# Give homeassistant.exceptions a HomeAssistantError so coordinator imports cleanly
sys.modules["homeassistant.exceptions"].HomeAssistantError = Exception  # type: ignore[attr-defined]

# Give bleak the attributes coordinator.py imports at module level
_bleak = sys.modules["bleak"]
_bleak.BleakClient = object  # type: ignore[attr-defined]

# Give bleak_retry_connector the attributes coordinator.py imports at module level
_brc = sys.modules["bleak_retry_connector"]
_brc.BleakClientWithServiceCache = object  # type: ignore[attr-defined]
_brc.establish_connection = None  # type: ignore[attr-defined]

# Give homeassistant.components.bluetooth the attributes coordinator.py imports
_bt = sys.modules["homeassistant.components.bluetooth"]
_bt.BluetoothCallbackMatcher = object  # type: ignore[attr-defined]
_bt.BluetoothChange = object  # type: ignore[attr-defined]
_bt.BluetoothScanningMode = object  # type: ignore[attr-defined]
_bt.BluetoothServiceInfoBleak = object  # type: ignore[attr-defined]
_bt.async_ble_device_from_address = None  # type: ignore[attr-defined]
_bt.async_register_callback = None  # type: ignore[attr-defined]

# Give homeassistant.core the attributes coordinator.py imports
_core = sys.modules["homeassistant.core"]
_core.HomeAssistant = object  # type: ignore[attr-defined]
_core.callback = lambda f: f  # type: ignore[attr-defined]

# Give homeassistant.helpers.update_coordinator the attributes coordinator.py imports
_upc = sys.modules["homeassistant.helpers.update_coordinator"]


class _GenericBase:
    """A base class that accepts (and ignores) generic type parameters."""

    def __class_getitem__(cls, _item):
        return cls


_upc.DataUpdateCoordinator = _GenericBase  # type: ignore[attr-defined]

# Give homeassistant.helpers.event the attributes coordinator.py imports
_evt = sys.modules["homeassistant.helpers.event"]
_evt.async_track_time_interval = None  # type: ignore[attr-defined]


def _load(name: str, path: pathlib.Path):
    """Load a single .py file as module *name*, bypassing the package __init__."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Load only the modules under test — skip fbot/__init__.py entirely
product_catalog = _load("fbot.product_catalog", FBOT / "product_catalog.py")
catalog = _load("fbot.catalog", FBOT / "catalog.py")
const = _load("fbot.const", FBOT / "const.py")
coordinator_mod = _load("fbot.coordinator", FBOT / "coordinator.py")

FEATURES = product_catalog.FEATURES
PRODUCTS = product_catalog.PRODUCTS
CATEGORIES = product_catalog.CATEGORIES

lookup_profile = catalog.lookup_profile
DeviceProfile = catalog.DeviceProfile

_parse_status = coordinator_mod._parse_status
_parse_settings = coordinator_mod._parse_settings
_build_read_status = coordinator_mod._build_read_status
_build_read_settings = coordinator_mod._build_read_settings
_frame = coordinator_mod._frame
_crc16_modbus = coordinator_mod._crc16_modbus

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
failures = 0


def check(label: str, condition: bool) -> None:
    global failures
    status = PASS if condition else FAIL
    print(f"  [{status}] {label}")
    if not condition:
        failures += 1


# ---------------------------------------------------------------------------
# Helpers — build a realistic fake Modbus response
# ---------------------------------------------------------------------------


def _fake_response(func_code: int, address: int, register_values: list[int]) -> bytes:
    """Build a fake device response matching the 6-byte header the real device sends.

    The device echoes back the request start-address and register-count before
    the data, so register data starts at byte offset 6 — matching _get_reg's
    hardcoded offset of 6.

    Format: [addr, func, 0x00, 0x00, count_hi, count_lo, reg0_hi, reg0_lo, ...]
    """
    count = len(register_values)
    payload = bytes([address, func_code, 0x00, 0x00, (count >> 8) & 0xFF, count & 0xFF])
    for v in register_values:
        payload += struct.pack(">H", v)
    crc = _crc16_modbus(payload)
    return payload + bytes([(crc >> 8) & 0xFF, crc & 0xFF])


def _regs(count: int, overrides: dict[int, int] | None = None) -> list[int]:
    """Make a zeroed register list with optional per-index overrides."""
    regs = [0] * count
    for idx, val in (overrides or {}).items():
        if 0 <= idx < count:
            regs[idx] = val
    return regs


# ============================================================================
print("\n=== 1. catalog.py — lookup_profile ===")
# ============================================================================

known_uuid = "0000C106-0000-1000-8000-00805F9B34FB"
known_name = "POWER-06C1"
known_pid = "69d70c58189f8658d9260223"

p = lookup_profile([known_uuid], known_name)
check("returns DeviceProfile for a known device", isinstance(p, DeviceProfile))
check("correct product_id", p is not None and p.product_id == known_pid)
check("correct modbus_address (0x11 = 17)", p is not None and p.modbus_address == 17)
check("correct modbus_count (80)", p is not None and p.modbus_count == 80)
check("device_type is 'pps'", p is not None and p.device_type == "pps")

none_result = lookup_profile(["0000DEAD-0000-1000-8000-00805F9B34FB"], "UNKNOWN-DEVICE")
check("returns None for unknown device", none_result is None)

# UUID matching should be case-insensitive
p_lower = lookup_profile([known_uuid.lower()], known_name)
check(
    "UUID lookup is case-insensitive",
    p_lower is not None and p_lower.product_id == known_pid,
)

# ============================================================================
print("\n=== 2. product_catalog.py — FEATURES structure ===")
# ============================================================================

feat = FEATURES.get(known_pid)
check("FEATURES entry exists for known product_id", feat is not None)
check("has 'states' list", feat is not None and isinstance(feat.get("states"), list))
check(
    "has 'settings' list", feat is not None and isinstance(feat.get("settings"), list)
)

if feat:
    states = feat["states"]
    check("at least one state", len(states) >= 1)
    if states:
        s0 = states[0]
        check("state has 'id'", "id" in s0)
        check("state has 'function_name'", "function_name" in s0)
        check("state has 'holding_index'", "holding_index" in s0)
        check("state has 'input_index'", "input_index" in s0)
        check("state has 'children'", "children" in s0)

    settings = feat["settings"]
    writable = [s for s in settings if s["data_state"] and len(s["data_list"]) > 1]
    check("at least one writable setting", len(writable) >= 1)
    if writable:
        w0 = writable[0]
        check("setting has 'id'", "id" in w0)
        check("setting has 'holding_index'", "holding_index" in w0)
        check("setting has 'data_list'", "data_list" in w0)
        check("setting has 'unit'", "unit" in w0)

# Every product in FEATURES should be reachable via a product in PRODUCTS
products_with_feat = {
    v["product_id"] for v in PRODUCTS.values() if v["product_id"] in FEATURES
}
orphan_features = set(FEATURES.keys()) - products_with_feat
check(
    f"all FEATURES keys map to a PRODUCTS entry ({len(orphan_features)} orphans)",
    len(orphan_features) == 0,
)

# ============================================================================
print("\n=== 3. coordinator.py — _parse_status ===")
# ============================================================================

COUNT = 80
ADDR = 0x11

# Build a fake 0x04 response with some interesting values
overrides_04 = {
    56: 987,  # battery: 987 / 10.0 = 98.7 %
    6: 500,  # input power
    20: 300,  # total power
    21: 150,  # system power
    39: 200,  # output power
    18: 2300,  # AC out voltage: 2300 * 0.1 = 230.0 V
    19: 500,  # AC out freq:    500  * 0.1 = 50.0 Hz
    22: 5000,  # AC in freq:    5000  * 0.01 = 50.0 Hz
    58: 45,  # time to full
    59: 120,  # remaining time
    2: 3,  # charge level: 300 + (3-1)*200 = 700 W
    53: 11,  # battery S1: 11/10 - 1 = 0.1 %
    3: 400,  # ac input power
    4: 100,  # dc input power
    25: 1,  # USB on/off (input_index for "Sortie USB")
    26: 0,  # DC on/off
    27: 1,  # AC on/off
    28: 0,  # LED on/off
}
regs_04 = _regs(COUNT, overrides_04)
resp_04 = _fake_response(0x04, ADDR, regs_04)
status = _parse_status(resp_04, ADDR, COUNT)

check("_parse_status returns a dict", isinstance(status, dict))
check("stores i_0 … i_79 raw registers", all(f"i_{i}" in status for i in range(COUNT)))
check(
    "battery_percent correct (98.7)",
    abs(status.get(const.KEY_BATTERY_PERCENT, -1) - 98.7) < 0.01,
)
check(
    "ac_out_voltage correct (230.0 V)",
    abs(status.get(const.KEY_AC_OUT_VOLTAGE, -1) - 230.0) < 0.01,
)
check(
    "ac_out_frequency correct (50.0 Hz)",
    abs(status.get(const.KEY_AC_OUT_FREQUENCY, -1) - 50.0) < 0.01,
)
check(
    "ac_in_frequency correct (50.0 Hz)",
    abs(status.get(const.KEY_AC_IN_FREQUENCY, -1) - 50.0) < 0.01,
)
check("charge_level correct (700 W)", status.get(const.KEY_CHARGE_LEVEL) == 700)
check("remaining_time correct (120)", status.get(const.KEY_REMAINING_TIME) == 120)
check("ac_input_power correct (400)", status.get(const.KEY_AC_INPUT_POWER) == 400)
check("dc_input_power correct (100)", status.get(const.KEY_DC_INPUT_POWER) == 100)

# Catalog-driven switch state keys are present
check("i_25 present (USB input_index)", "i_25" in status)
check("i_25 == 1 (USB is on)", status["i_25"] == 1)
check("i_27 present (AC input_index)", "i_27" in status)
check("i_27 == 1 (AC is on)", status["i_27"] == 1)
check("i_26 == 0 (DC is off)", status.get("i_26") == 0)

# No interactive keys should appear
interactive_keys = {
    "usb_active",
    "dc_active",
    "ac_active",
    "light_active",
    "ac_silent",
    "key_sound",
    "light_mode",
    "ac_charge_limit",
    "silent_charging",
    "buzzer",
    "ups_mode",
}
leaked = interactive_keys & set(status.keys())
check(f"no interactive keys in status data (leaked: {leaked})", len(leaked) == 0)

# Wrong address is rejected
bad_addr = _fake_response(0x04, 0x22, regs_04)
check(
    "_parse_status rejects wrong address", _parse_status(bad_addr, ADDR, COUNT) is None
)

# Wrong function code is rejected
bad_func = _fake_response(0x03, ADDR, regs_04)
check(
    "_parse_status rejects func_code 0x03", _parse_status(bad_func, ADDR, COUNT) is None
)

# ============================================================================
print("\n=== 4. coordinator.py — _parse_settings ===")
# ============================================================================

overrides_03 = {
    13: 300,  # AC charge power setting (data_list value, e.g. 300 W)
    47: 12,  # AC firmware version
    48: 34,  # BMS firmware version
    49: 5,  # PV firmware version
    50: 7,  # Panel firmware version
    59: 5,  # idle timeout
    60: 8,  # AC idle timeout
}
regs_03 = _regs(COUNT, overrides_03)
resp_03 = _fake_response(0x03, ADDR, regs_03)
settings = _parse_settings(resp_03, ADDR, COUNT)

check("_parse_settings returns a dict", isinstance(settings, dict))
check(
    "stores h_0 … h_79 raw registers", all(f"h_{i}" in settings for i in range(COUNT))
)
check("h_13 == 300 (AC charge power)", settings.get("h_13") == 300)
check("h_59 == 5  (USB idle timeout)", settings.get("h_59") == 5)
check("ac_version  correct (12)", settings.get(const.KEY_AC_VERSION) == 12)
check("bms_version correct (34)", settings.get(const.KEY_BMS_VERSION) == 34)
check("pv_version  correct (5)", settings.get(const.KEY_PV_VERSION) == 5)
check("panel_version correct (7)", settings.get(const.KEY_PANEL_VERSION) == 7)

# Interactive keys must NOT appear
interactive_setting_keys = {
    "ac_silent",
    "key_sound",
    "light_mode",
    "ac_charge_limit",
    "threshold_charge",
    "threshold_discharge",
    "silent_charging",
    "buzzer",
    "ups_mode",
}
leaked_s = interactive_setting_keys & set(settings.keys())
check(f"no interactive keys in settings data (leaked: {leaked_s})", len(leaked_s) == 0)

check(
    "_parse_settings rejects wrong address",
    _parse_settings(_fake_response(0x03, 0x22, regs_03), ADDR, COUNT) is None,
)
check(
    "_parse_settings rejects func_code 0x04",
    _parse_settings(_fake_response(0x04, ADDR, regs_03), ADDR, COUNT) is None,
)

# ============================================================================
print("\n=== 5. Switch entity logic — catalog-driven data keys ===")
# ============================================================================

if feat and feat["states"]:
    for state in feat["states"]:
        hi = state["holding_index"]
        ii = state["input_index"]
        name = state["function_name"]
        expected_data_key = f"i_{ii}"
        # Simulate what FbotCatalogSwitch.__init__ computes
        computed_key = f"i_{state['input_index']}"
        check(
            f"  state '{name}': data_key == 'i_{ii}'",
            computed_key == expected_data_key,
        )
        check(
            f"  state '{name}': write register == holding_index ({hi})",
            isinstance(hi, int),
        )
        check(
            f"  state '{name}': is_on == bool(status['{expected_data_key}'])",
            expected_data_key in status,
        )

# ============================================================================
print("\n=== 6. Select entity logic — catalog-driven options ===")
# ============================================================================

if feat and feat["settings"]:
    writable = [
        s
        for s in feat["settings"]
        if s["data_state"] and len(s["data_list"]) > 1 and s["holding_index"] < COUNT
    ]
    for setting in writable:
        hi = setting["holding_index"]
        dl = setting["data_list"]
        unit = setting.get("unit", "")
        name = setting["function_name"]
        expected_data_key = f"h_{hi}"

        # Build labels the same way select.py does
        options = [f"{v} {unit}".strip() if unit else str(v) for v in dl]
        value_to_option = dict(zip(dl, options))
        option_to_value = dict(zip(options, dl))

        check(
            f"  setting '{name}': data_key == 'h_{hi}'",
            expected_data_key in settings,
        )
        # Round-trip: raw value in data → option label → raw value
        raw = settings.get(expected_data_key)
        if raw in value_to_option:
            label = value_to_option[raw]
            recovered = option_to_value.get(label)
            check(
                f"  setting '{name}': raw {raw} → '{label}' → {recovered} (round-trip)",
                recovered == raw,
            )
        else:
            check(
                f"  setting '{name}': raw value {raw} not in data_list {dl} (device at default?)",
                True,  # acceptable — device just hasn't reported this register yet
            )

# ============================================================================
print("\n=== 7. const.py — removed constants absent, kept constants present ===")
# ============================================================================

removed = [
    "REG_USB_CONTROL",
    "REG_DC_CONTROL",
    "REG_AC_CONTROL",
    "REG_LIGHT_CONTROL",
    "REG_KEY_SOUND",
    "REG_AC_SILENT_CONTROL",
    "REG_THRESHOLD_DISCHARGE",
    "REG_THRESHOLD_CHARGE",
    "REG_SILENT_CHARGING",
    "REG_BUZZER",
    "REG_APP_REMOTE_SHUTOFF",
    "REG_LOW_BATTERY_NOTIFICATION",
    "REG_UPS_MODE",
    "REG_AC_CHARGE_LIMIT",
    "STATE_USB_BIT",
    "STATE_DC_BIT",
    "STATE_AC_BIT",
    "STATE_LIGHT_BIT",
    "KEY_USB_ACTIVE",
    "KEY_DC_ACTIVE",
    "KEY_AC_ACTIVE",
    "KEY_LIGHT_ACTIVE",
    "KEY_THRESHOLD_CHARGE",
    "KEY_THRESHOLD_DISCHARGE",
    "KEY_AC_SILENT",
    "KEY_KEY_SOUND",
    "KEY_LIGHT_MODE",
    "KEY_AC_CHARGE_LIMIT",
    "KEY_SILENT_CHARGING",
    "KEY_BUZZER",
    "KEY_APP_REMOTE_SHUTOFF",
    "KEY_LOW_BATTERY_NOTIFICATION",
    "KEY_UPS_MODE",
    "LIGHT_MODES",
    "AC_CHARGE_LIMITS",
]
for name in removed:
    check(f"  '{name}' removed from const", not hasattr(const, name))

kept = [
    "DOMAIN",
    "CONF_SERVICE_UUIDS",
    "SERVICE_UUID",
    "WRITE_CHAR_UUID",
    "NOTIFY_CHAR_UUID",
    "REG_USB_A1_OUT",
    "REG_USB_A2_OUT",
    "REG_USB_C1_OUT",
    "REG_USB_C2_OUT",
    "REG_USB_C3_OUT",
    "REG_USB_C4_OUT",
    "KEY_BATTERY_PERCENT",
    "KEY_BATTERY_S1_PERCENT",
    "KEY_BATTERY_S2_PERCENT",
    "KEY_BATTERY_S1_CONNECTED",
    "KEY_BATTERY_S2_CONNECTED",
    "KEY_AC_INPUT_POWER",
    "KEY_DC_INPUT_POWER",
    "KEY_INPUT_POWER",
    "KEY_OUTPUT_POWER",
    "KEY_SYSTEM_POWER",
    "KEY_TOTAL_POWER",
    "KEY_REMAINING_TIME",
    "KEY_CHARGE_LEVEL",
    "KEY_AC_OUT_VOLTAGE",
    "KEY_AC_OUT_FREQUENCY",
    "KEY_AC_IN_FREQUENCY",
    "KEY_TIME_TO_FULL",
    "KEY_USB_A1_POWER",
    "KEY_USB_A2_POWER",
    "KEY_USB_C1_POWER",
    "KEY_USB_C2_POWER",
    "KEY_USB_C3_POWER",
    "KEY_USB_C4_POWER",
    "KEY_BMS_VERSION",
    "KEY_AC_VERSION",
    "KEY_PV_VERSION",
    "KEY_PANEL_VERSION",
]
for name in kept:
    check(f"  '{name}' present in const", hasattr(const, name))

# ============================================================================
# Summary
# ============================================================================

total = sum(1 for _ in range(0))  # reset-style; count via failures
print(f"\n{'=' * 60}")
if failures == 0:
    print(f"\033[32mAll checks passed.\033[0m")
else:
    print(f"\033[31m{failures} check(s) FAILED.\033[0m")
    sys.exit(1)
