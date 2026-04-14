"""Constants for the fbot Bluetooth integration."""

from homeassistant.const import Platform

DOMAIN = "fbot"
MANUFACTURER = "BrightEMS"
PRODUCT_PREFIX = "BrightEMS"

# Platforms supported by this integration
PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.SWITCH, Platform.CLIMATE]

# Protocol versions
PROTOCOL_V1 = 1
PROTOCOL_V2 = 2

# BLE Service UUIDs (extracted from app-service.js)
BLE_SERVICE_UUIDS = [
    "0000A002-0000-1000-8000-00805F9B34FB",  # Main BLE service
    "0000C304-0000-1000-8000-00805F9B34FB",  # Write characteristic
    "0000C305-0000-1000-8000-00805F9B34FB",  # Notify characteristic
]

# Device name prefixes for BLE scanning
DEVICE_NAME_PREFIXES = [
    "DC_DC-",
    "Meter-",
    "POWER-",
    "Socket-",
    "meter-",
    "socket-",
    "searchConnect",
    "http",
]

# Register map addresses (from app-service.js Wu constants)
REGISTER_MAP = {
    # Control
    "reset_to_factory": 0x00,
    "debug_mode": 0x01,
    # Power control
    "AC_charge_power": 0x02,
    "AC_backup_output_onoff": 0x04,
    "AC_BackUp_Output_KEY_onoff": 0x04,
    "AC_Vol_Exist_status": 0x05,
    "AC_charge_onoff": 0x06,
    "AC_grid_power": 0x07,
    "Low_PV_Vol_Exist_status": 0x08,
    "Low_PV_charge_onoff": 0x09,
    "PV2_charge_onoff": 0x0B,
    # Status flags
    "Buzzer_enable": 0x07,
    "grid_auto_enable": 0x08,
    "Car_charge_Vol_Exist_status": 0x09,
    "BMS_user_status_BatHeat": 0x09,
    "grid_immediate_enable": 0x09,
    "grid_custom_enable": 0x0A,
    "charge_immediate_enable": 0x0B,
    "charge_custom_enable": 0x0C,
    "main_BMS_user_status": 0x25,
    "slave1_BMS_user_status": 0x27,
    "slave2_BMS_user_status": 0x29,
    "slave3_BMS_user_status": 0x2B,
    "slave4_BMS_user_status": 0x2D,
    # Battery/BMS
    "discharge_SOC_min_limit": 0x1A,
    "ups_charge_soc_max_limit": 0x1B,
    "dod_deep_discharge": 0x20,
    "grid_immediate_EndSOC": 0x23,
    "charge_immediate_energySOC": 0x25,
    "BMS_Version": 0x30,
    # Device time
    "timeZone": 0x04,
    "DST_start_time": 0x05,
    "DST_end_time": 0x06,
    "LCD_dim_time": 0x19,
    "shutdown_wait_time": 0x1C,
    "USB_QC_PD_sleep_time": 0x1D,
    "DC_12V_output_sleep_time": 0x1E,
    "grid_immediate_time": 0x22,
    "charge_immediate_time": 0x24,
    "grid_charge_appointment_time": 0x46,
    "remain_charge_time": 0x47,
    "remain_discharge_time": 0x48,
    "device_time_year_month": 0x61,
    "device_time_day_hour": 0x62,
    "device_time_min_sec": 0x63,
    # Firmware
    "firmware_function_code": 0x26,
    "main_board_firmware_address_max": 0x63,
    "meter_firmware_address_min": 0x69,
    "meter_firmware_address_max": 0x6D,
    # Version info
    "AC_Version": 0x2F,
    "Panel_Version": 0x32,
    # Power registers (0x00-0x65, 0x0191, 0x02BD, 0x03E9)
    "DC_charge_power": 0x00,
    "PV1_charge_power": 0x03,
    "PV3_charge_power": 0x05,
    "PV4_charge_power": 0x06,
    "grid_charge_chart_start": 0x65,
    "energy_chart_start": 0x3E9,
}

# BLE command types
BLE_COMMANDS = {
    "GET_BLE_SYNC_STATUS": "GET_BLE_SYNC_STATUS",
    "GET_BLE_SEARCH": "GET_BLE_SEARCH",
    "GET_BLE_SEARCH_STOP": "GET_BLE_SEARCH_STOP",
    "GET_BLE_ADAPTER_INIT": "GET_BLE_ADAPTER_INIT",
    "GET_BLE_ADAPTER_OPEN": "GET_BLE_ADAPTER_OPEN",
    "GET_BLE_ADAPTER_CLOSE": "GET_BLE_ADAPTER_CLOSE",
    "GET_BLE_CONNECT_CREATE": "GET_BLE_CONNECT_CREATE",
    "GET_BLE_CONNECT_CLOSE": "GET_BLE_CONNECT_CLOSE",
    "GET_BLE_SERVICES": "GET_BLE_SERVICES",
    "GET_BLE_WRITE": "GET_BLE_WRITE",
    "GET_BLE_CMD_INFO": "GET_BLE_CMD_INFO",
    "GET_BLE_CONNECT_INFO": "GET_BLE_CONNECT_INFO",
    "GET_BLE_HOLDING_REGISTER": "GET_BLE_HOLDING_REGISTER",
    "GET_BLE_HOLDING_REGISTER_SET": "GET_BLE_HOLDING_REGISTER_SET",
    "GET_BLE_INPUT_REGISTER_SET": "GET_BLE_INPUT_REGISTER_SET",
}

# CRC-16/Modbus configuration
CRC16_MODBUS_POLY = 0xA001
CRC16_MODBUS_INIT = 0xFFFF

# Entity category and device class mappings
ENTITY_CATEGORY_BATTERY = "battery"
ENTITY_CATEGORY_DIAGNOSTIC = "diagnostic"
ENTITY_CATEGORY_NONE = None

DEVICE_CLASS_BATTERY = "battery"
DEVICE_CLASS_CURRENT = "current"
DEVICE_CLASS_ENERGY = "energy"
DEVICE_CLASS_FREQUENCY = "frequency"
DEVICE_CLASS_POWER = "power"
DEVICE_CLASS_SIGNAL_STRENGTH = "signal_strength"
DEVICE_CLASS_TEMPERATURE = "temperature"
DEVICE_CLASS_VOLTAGE = "voltage"

STATE_CLASS_TOTAL_INCREASING = "total_increasing"
STATE_CLASS_MEASUREMENT = "measurement"

# Binary sensor device classes
DEVICE_CLASS_CONNECTIVITY = "connectivity"
DEVICE_CLASS_DOOR = "door"
DEVICE_CLASS_GARAGE_DOOR = "garage_door"
DEVICE_CLASS_MOTION = "motion"
DEVICE_CLASS_OCCUPANCY = "occupancy"
DEVICE_CLASS_POWER = "power"
DEVICE_CLASS_PROBLEM = "problem"
DEVICE_CLASS_SAFETY = "safety"
DEVICE_CLASS_SMOKE = "smoke"
DEVICE_CLASS_UNLOCK = "lock"
DEVICE_CLASS_WINDOW = "window"
