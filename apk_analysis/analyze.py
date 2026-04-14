#!/usr/bin/env python3
"""
BrightEMS APK Protocol Analyzer
Extracts BLE/Modbus protocol details from the decompiled app-service.js
"""

import re
import json
import os

APP_JS = os.path.join(os.path.dirname(__file__),
    "decompiled/resources/assets/apps/__UNI__55F5E7F/www/app-service.js")
OUT_DIR = os.path.join(os.path.dirname(__file__), "extracted")
os.makedirs(OUT_DIR, exist_ok=True)

with open(APP_JS) as f:
    content = f.read()

print(f"Loaded app-service.js ({len(content):,} bytes)\n")

# ─────────────────────────────────────────────
# 1. BLE UUIDs
# ─────────────────────────────────────────────
print("=" * 60)
print("BLE SERVICE / CHARACTERISTIC UUIDs")
print("=" * 60)
uuid_re = re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}')
uuids = sorted(set(uuid_re.findall(content)))
for u in uuids:
    if u.startswith("0000A002"):
        label = "  ← SERVICE"
    elif u.startswith("0000C304"):
        label = "  ← WRITE characteristic"
    elif u.startswith("0000C305"):
        label = "  ← NOTIFY characteristic"
    else:
        label = ""
    print(f"  {u}{label}")

# ─────────────────────────────────────────────
# 2. Device name prefixes (for BLE scan filter)
# ─────────────────────────────────────────────
print()
print("=" * 60)
print("BLE ADVERTISEMENT NAME PREFIXES (scan filter)")
print("=" * 60)
# startsWith calls in the scan loop
name_prefixes = re.findall(r'startsWith\("([^"]+)"\)', content)
unique_prefixes = sorted(set(name_prefixes))
for p in unique_prefixes:
    print(f"  {p}")

# ─────────────────────────────────────────────
# 3. CRC / Frame functions (decoded from minified JS)
# ─────────────────────────────────────────────
print()
print("=" * 60)
print("MODBUS FRAME STRUCTURE")
print("=" * 60)
print("""
  CRC algorithm: CRC-16/Modbus
    poly=0xA001 (reflected), init=0xFFFF
    Matches: function Mn(e) in app-service.js

  Frame builder (Gn): [addr, func, ...data, crc_low, crc_high]
    - CRC appended low-byte first (little-endian)

  READ request (jn / getReadModbus):
    [addr, 0x03, reg_high, reg_low, count_high, count_low, crc_low, crc_high]

  WRITE single register (qn / getWriteModbus):
    [addr, func_code, reg_high, reg_low, ...value_bytes, crc_low, crc_high]
""")

# ─────────────────────────────────────────────
# 4. Register map from Wu constants object
# ─────────────────────────────────────────────
print("=" * 60)
print("REGISTER MAP (Wu constants object)")
print("=" * 60)

# Extract the Wu object
wu_match = re.search(r'const Wu=\{([^;]+?)\};', content)
if wu_match:
    wu_raw = "{" + wu_match.group(1) + "}"
    # Parse key:value pairs (simple numeric values and arrays)
    entries = re.findall(r'(\w+):([\d\[\],\s]+?)(?=[,}])', wu_raw)
    registers = {}
    for name, val in entries:
        val = val.strip()
        if val.startswith('['):
            try:
                registers[name] = json.loads(val)
            except Exception:
                registers[name] = val
        else:
            try:
                registers[name] = int(val)
            except Exception:
                registers[name] = val

    # Group into categories
    categories = {
        "State/Status registers": [],
        "Control ON/OFF registers": [],
        "Power/Energy registers": [],
        "Time/Schedule registers": [],
        "BMS/Battery registers": [],
        "Firmware/System registers": [],
        "Chart data registers": [],
        "Array registers (multi-slot)": [],
        "Other": [],
    }

    for name, val in sorted(registers.items(), key=lambda x: (x[1] if isinstance(x[1], int) else 9999, x[0])):
        if isinstance(val, list):
            categories["Array registers (multi-slot)"].append((name, val))
        elif any(k in name for k in ['State', 'Status', 'status', 'state', 'flag']):
            categories["State/Status registers"].append((name, val))
        elif any(k in name for k in ['onoff', '_onoff', 'enable', 'pause', 'idle']):
            categories["Control ON/OFF registers"].append((name, val))
        elif any(k in name for k in ['power', 'Power', 'energy', 'Energy', 'SOC', 'soc', 'BAT', 'charge', 'discharge']):
            categories["Power/Energy registers"].append((name, val))
        elif any(k in name for k in ['time', 'Time', 'DST', 'timezone', 'Zone', 'start', 'end', 'min_sec', 'day_hour', 'year_month']):
            categories["Time/Schedule registers"].append((name, val))
        elif any(k in name for k in ['BMS', 'bms', 'slave', 'main_B']):
            categories["BMS/Battery registers"].append((name, val))
        elif any(k in name for k in ['firmware', 'Firmware', 'reset', 'debug', 'factory', 'upgrade']):
            categories["Firmware/System registers"].append((name, val))
        elif any(k in name for k in ['chart', 'Chart']):
            categories["Chart data registers"].append((name, val))
        else:
            categories["Other"].append((name, val))

    for cat, items in categories.items():
        if not items:
            continue
        print(f"\n  [{cat}]")
        for name, val in items:
            print(f"    reg {str(val):>6}  {name}")

    # Save full register map as JSON
    out_path = os.path.join(OUT_DIR, "register_map.json")
    with open(out_path, "w") as f:
        json.dump(registers, f, indent=2)
    print(f"\n  → Saved to {out_path}")
else:
    print("  WARNING: Could not find Wu constants object")

# ─────────────────────────────────────────────
# 5. BLE polling / holding register read
# ─────────────────────────────────────────────
print()
print("=" * 60)
print("POLLING LOGIC")
print("=" * 60)

idx = content.find('getReadModbusCRCLowFront')
if idx >= 0:
    snippet = content[max(0,idx-200):idx+400]
    # Extract modbus_address and modbus_count references
    print("  Read poll command construction:")
    print(f"  {snippet[:600]}")

# ─────────────────────────────────────────────
# 6. Setting list items (writable controls)
# ─────────────────────────────────────────────
print()
print("=" * 60)
print("WRITABLE CONTROL ACTIONS (setting_list)")
print("=" * 60)

# Find setting-related write calls
write_patterns = re.findall(
    r'getWriteModbus[^(]*\([^)]{0,200}\)',
    content
)
print(f"  Found {len(write_patterns)} getWriteModbus call sites")
for i, p in enumerate(write_patterns[:10]):
    print(f"  [{i+1}] {p[:120]}")

# ─────────────────────────────────────────────
# 7. Extract & prettify BLE state machine
# ─────────────────────────────────────────────
print()
print("=" * 60)
print("BLE STATE MACHINE (GET_BLE_CMD_INFO handler)")
print("=" * 60)

idx = content.find('GET_BLE_CMD_INFO')
if idx >= 0:
    # Find the handler function body - look for the action handler
    handler_start = content.rfind('\n', 0, idx)
    snippet = content[max(0, idx-300):idx+2000]
    print(snippet[:1500])

# ─────────────────────────────────────────────
# 8. Prettify the relevant section into a file
# ─────────────────────────────────────────────
print()
print("=" * 60)
print("PRETTIFYING KEY SECTIONS")
print("=" * 60)

try:
    import jsbeautifier
    opts = jsbeautifier.default_options()
    opts.indent_size = 2

    # Extract ~50KB around the Modbus/BLE core logic
    start = max(0, content.find('function Mn(') - 500)
    end = min(len(content), content.find('ModbusUtils') + 3000)
    core_section = content[start:end]

    pretty = jsbeautifier.beautify(core_section, opts)
    out_path = os.path.join(OUT_DIR, "modbus_core_pretty.js")
    with open(out_path, "w") as f:
        f.write(pretty)
    print(f"  → Wrote prettified Modbus core to {out_path}")

    # Extract BLE bluetooth store section
    ble_start = max(0, content.find('onBLECharacteristicValueChange') - 1000)
    ble_end = min(len(content), ble_start + 8000)
    ble_section = content[ble_start:ble_end]
    pretty_ble = jsbeautifier.beautify(ble_section, opts)
    out_path2 = os.path.join(OUT_DIR, "ble_handler_pretty.js")
    with open(out_path2, "w") as f:
        f.write(pretty_ble)
    print(f"  → Wrote prettified BLE handler to {out_path2}")

    # Extract Wu constants + surrounding control write logic
    wu_start = max(0, content.find('const Wu={') - 200)
    wu_end = min(len(content), wu_start + 5000)
    wu_section = content[wu_start:wu_end]
    pretty_wu = jsbeautifier.beautify(wu_section, opts)
    out_path3 = os.path.join(OUT_DIR, "register_constants_pretty.js")
    with open(out_path3, "w") as f:
        f.write(pretty_wu)
    print(f"  → Wrote prettified register constants to {out_path3}")

except ImportError:
    print("  jsbeautifier not available, skipping prettification")

print()
print("Done.")
