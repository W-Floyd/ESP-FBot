# BrightEMS APK Protocol Findings

Source: `BrightEMS_1.6.1_APKPure.xapk` (com.sydpower.app)
App framework: DCloud uni-app (business logic in `app-service.js`)

---

## BLE Connection

**Service UUID:** `0000A002-0000-1000-8000-00805F9B34FB`  
**Write characteristic:** `0000C304-0000-1000-8000-00805F9B34FB`  
**Notify characteristic:** `0000C305-0000-1000-8000-00805F9B34FB`

These **exactly match** the UUIDs already in `fbot.h`.

**Device name scan filter** (advertisement local name prefix):
- `POWER-` — portable power stations
- `Socket-` / `socket-`
- `Meter-` / `meter-`
- `DC_DC-`

---

## Modbus Protocol

### CRC
CRC-16/Modbus: poly=0xA001 (reflected), init=0xFFFF, **appended little-endian** (low byte first).

### Frame formats

**Read holding registers (func 0x03):**
```
[addr, 0x03, reg_hi, reg_lo, count_hi, count_lo, crc_lo, crc_hi]
```

**Read input registers (func 0x04):**
```
[addr, 0x04, reg_hi, reg_lo, count_hi, count_lo, crc_lo, crc_hi]
```

**Write single register (func 0x06) — protocol v0:**
```
[addr, 0x06, reg_hi, reg_lo, val_hi, val_lo, crc_lo, crc_hi]
```

**Write multiple registers (func 0x10 / 16) — protocol v1+:**
Constructed by `getWriteModbusCRCLowFront_new(addr, 6, start_reg, count, [val_hi,val_lo,...], false)`
```
[addr, 0x06, start_hi, start_lo, val_hi, val_lo, ..., crc_lo, crc_hi]
```

### Polling
- **Holding registers** (settings): `getReadModbusCRCLowFront(modbus_address, 0, modbus_count, false)`
- **Input registers** (live status): `getModbusDataCRCLowFront(modbus_address, 0x04, [0,0,count_hi,count_lo], false)`

`modbus_address` and `modbus_count` come from product config (cloud or cached). The known address is `0x11`.

---

## Register Map (`Wu` constants object)

### State / Status (read)
| Register | Name |
|----------|------|
| 53 | deviceState1 |
| 54 | deviceState2 |
| 75 | systemState |
| 76 | systemState2 |
| 83 | grid_charge_custom_enable_flag |
| 84 | grid_charge_custom_current_status |
| 37 | main_BMS_user_status |
| 39–45 | slave1–4_BMS_user_status |

### Control ON/OFF (write, func 0x06)
| Register | Name |
|----------|------|
| 1 | grid_function_pause |
| 2 | system_idle_set |
| 3 | AI_energy_control |
| 4 | AC_backup_output_onoff / AC_BackUp_Output_KEY_onoff |
| 6 | AC_charge_onoff |
| 7 | grid_discharge_onoff / Buzzer_enable |
| 8 | grid_auto_enable |
| 9 | Low_PV_charge_onoff / grid_immediate_enable |
| 10 | Car_charge_onoff / grid_custom_enable |
| 11 | DC_usb_pd_led_wirelesscharge_Port_Out_onoff / charge_immediate_enable |
| 12 | charge_custom_enable |
| 13 | eco |

### Power / Energy
| Register | Name |
|----------|------|
| 0 | DC_charge_power |
| 2 | AC_charge_power / Grid_charge_power |
| 3 | PV1_charge_power |
| 4 | PV2_charge_power |
| 5 | PV3_charge_power |
| 12 | AC_output_power |
| 26 | discharge_SOC_min_limit |
| 33 | grid_immediate_power |
| 59 | PV_charge_energy_total_H |
| 60 | PV_charge_energy_total_L |
| 61 | PV_charge_energy_today |
| 78 | total_DC_discharge_power |
| 88 | charge_priority |

### Battery / BMS
| Register | Name |
|----------|------|
| 31 | main_BAT (SOC) |
| 32–35 | slave1–4_BAT |
| 48 | BMS_Version |

### Time / Sleep settings
| Register | Name |
|----------|------|
| 4 | timeZone |
| 5 | DST_start_time |
| 6 | DST_end_time |
| 24 | Offline_AC_output_sleep_time |
| 25 | LCD_dim_time |
| 28 | shutdown_wait_time |
| 29 | USB_QC_PD_sleep_time |
| 30 | DC_12V_output_sleep_time |
| 97 | device_time_year_month |
| 98 | device_time_day_hour |
| 99 | device_time_min_sec |

### Versions
| Register | Name |
|----------|------|
| 47 | AC_Version |
| 49 | PV_Version |
| 50 | Panel_Version |

### Schedule arrays (multi-register writes)
| Registers | Name |
|-----------|------|
| [38,41,44] | charge_custom_startEnd_time_arr |
| [39,42,45] | charge_custom_energySOC_arr |
| [40,43,46] | charge_custom_period_arr |
| [52,54,56,58,60,62] | grid_custom_startEnd_time_arr |
| [53,55,57,59,61,63] | grid_custom_powerPeriod_arr |
| [68,69,70,71] | grid_discharge_end_soc_arr |
| [80,81,82,83] | socket_meter_bind_arr |

---

## Protocol Version Differences

The app checks `protocol_version >= 1` on the product info:
- **v0**: single-register writes only (`func 0x06`, 1 register at a time)
- **v1+**: multi-register writes supported (`getWriteModbusCRCLowFront_new`)

---

## Additional UUIDs

`6c382a98-49b8-40ba-b761-645d83e8ee74` — appears in the JS but purpose unclear; may be a secondary device type or OTA service.

---

## Extracted Files

- `extracted/register_map.json` — full Wu constants as JSON
- `extracted/modbus_core_pretty.js` — prettified CRC + frame builder functions
- `extracted/ble_handler_pretty.js` — prettified BLE notification handler
- `extracted/ble_vuex_actions_pretty.js` — prettified full BLE Vuex store actions
- `extracted/register_constants_pretty.js` — prettified Wu register constants
