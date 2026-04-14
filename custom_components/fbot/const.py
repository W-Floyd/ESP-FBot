"""Constants for the Fbot integration."""

DOMAIN = "fbot"

# Config entry data key for the list of BLE service UUIDs seen at pairing time.
CONF_SERVICE_UUIDS = "service_uuids"

# BLE UUIDs
WRITE_CHAR_UUID = "0000c304-0000-1000-8000-00805f9b34fb"
NOTIFY_CHAR_UUID = "0000c305-0000-1000-8000-00805f9b34fb"

# Input-register indices for per-port USB/DC power readings (hardcoded passive telemetry).
# These are used with _get_reg() on the 0x04 (input register) response.
REG_USB_A1_OUT = 30
REG_USB_A2_OUT = 31
REG_USB_C1_OUT = 34
REG_USB_C2_OUT = 35
REG_USB_C3_OUT = 36
REG_USB_C4_OUT = 37

# Data keys used in coordinator.data dict — passive telemetry (input registers, 0x04)
KEY_BATTERY_PERCENT = "battery_percent"
KEY_BATTERY_S1_PERCENT = "battery_s1_percent"
KEY_BATTERY_S2_PERCENT = "battery_s2_percent"
KEY_BATTERY_S1_CONNECTED = "battery_s1_connected"
KEY_BATTERY_S2_CONNECTED = "battery_s2_connected"
KEY_AC_INPUT_POWER = "ac_input_power"
KEY_DC_INPUT_POWER = "dc_input_power"
KEY_INPUT_POWER = "input_power"
KEY_OUTPUT_POWER = "output_power"
KEY_SYSTEM_POWER = "system_power"
KEY_TOTAL_POWER = "total_power"
KEY_REMAINING_TIME = "remaining_time"
KEY_CHARGE_LEVEL = "charge_level"
KEY_AC_OUT_VOLTAGE = "ac_out_voltage"
KEY_AC_OUT_FREQUENCY = "ac_out_frequency"
KEY_AC_IN_FREQUENCY = "ac_in_frequency"
KEY_TIME_TO_FULL = "time_to_full"
KEY_USB_A1_POWER = "usb_a1_power"
KEY_USB_A2_POWER = "usb_a2_power"
KEY_USB_C1_POWER = "usb_c1_power"
KEY_USB_C2_POWER = "usb_c2_power"
KEY_USB_C3_POWER = "usb_c3_power"
KEY_USB_C4_POWER = "usb_c4_power"

# Firmware version keys (passive telemetry, from holding registers 0x03)
KEY_BMS_VERSION = "bms_version"
KEY_AC_VERSION = "ac_version"
KEY_PV_VERSION = "pv_version"
KEY_PANEL_VERSION = "panel_version"
