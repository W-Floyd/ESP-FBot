#!/usr/bin/env python3
"""
Analyze register usage cases from the beautified app-service.js
Determines how each register is used based on actual code patterns
"""

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Tuple

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_JS = os.path.join(SCRIPT_DIR, "extracted/app-service-beautified.js")
REGISTER_MAP = os.path.join(SCRIPT_DIR, "extracted/register_map.json")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "register_usage_cases")
os.makedirs(OUTPUT_DIR, exist_ok=True)


@dataclass
class RegisterUsageInfo:
    """Usage information for a single register"""

    address: int
    name: str
    category: str
    usage_description: str
    lines: List[str]


def extract_wu_constants(content: str) -> Dict[int, str]:
    """Extract Wu register constant definitions"""
    wu_regs = {}

    # Find the Wu object
    wu_match = re.search(
        r"const Wu\s*=\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}", content, re.DOTALL
    )
    if wu_match:
        wu_content = wu_match.group(1)

        # Match register definitions like: regName: 15 or regName: 0x0f
        reg_pattern = re.compile(r'"?(\w)"?\s*:\s*(\d+|0x[0-9a-fA-F]+)')

        for match in reg_pattern.finditer(wu_content):
            name = match.group(1)
            addr_str = match.group(2)
            try:
                addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
                wu_regs[addr] = name
            except ValueError:
                pass

    return wu_regs


def extract_ble_commands(content: str) -> List[Tuple[str, str]]:
    """Extract BLE command names and their values"""
    commands = []

    # Match: GET_BLE_COMMAND_NAME: "GET_BLE_COMMAND_VALUE"
    cmd_pattern = re.compile(r'(GET_BLE_\w+)\s*:\s*"([^"]+)"')

    for match in cmd_pattern.finditer(content):
        commands.append((match.group(1), match.group(2)))

    return commands


def extract_poll_registers(content: str) -> Dict[int, str]:
    """Extract register arrays used for polling"""
    poll_regs = {}

    # Find register arrays used in polling contexts
    # Look for patterns like: [..., 15, ...] in arrays that are read
    array_pattern = re.compile(r"\[(\d{1,4})(?:,\s*(\d{1,4}))*\]")

    # Find common register ranges used in the app
    # Looking for patterns where registers are accessed in arrays
    if "0x0003" in content or "0x03" in content:
        # Find array contents that look like register lists
        array_match = re.search(r"\[([^\]]{200,})\]", content)
        if array_match:
            arr_content = array_match.group(1)
            # Extract numeric values
            nums = re.findall(r"(\d{1,4})", arr_content)
            for num in nums[:50]:  # First 50 registers
                try:
                    addr = int(num)
                    # Categorize based on address
                    if addr <= 10:
                        cat = "power_control"
                    elif addr <= 20:
                        cat = "status_flags"
                    elif addr <= 40:
                        cat = "battery_bms"
                    elif addr <= 60:
                        cat = "charging_config"
                    elif addr <= 80:
                        cat = "grid_operations"
                    elif addr <= 100:
                        cat = "device_time"
                    else:
                        cat = "firmware"
                    poll_regs[addr] = cat
                except ValueError:
                    pass

    return poll_regs


def classify_register_usage(address: int, name: str) -> Tuple[str, str]:
    """Classify register based on name and address"""
    name_lower = name.lower() if isinstance(name, str) else ""

    # Check name-based categories first
    if "reset" in name_lower or "debug" in name_lower:
        return ("control", "System control register (reset, debug)")
    elif (
        "ac_charge" in name_lower
        or "ac_backup" in name_lower
        or "backup_output" in name_lower
    ):
        return ("power_control", "AC charging power control")
    elif "ac_vol" in name_lower or "ac_grid" in name_lower or "ac_output" in name_lower:
        return ("power_control", "AC voltage/power monitoring")
    elif "pv" in name_lower or "charging" in name_lower:
        return ("power_control", "PV charging control")
    elif "ble_" in name_lower or "status" in name_lower or "enable" in name_lower:
        return ("status_flags", "Status flags and enable bits")
    elif "system_state" in name_lower or "device_state" in name_lower:
        return ("status_flags", "Device/system state monitoring")
    elif (
        "soc" in name_lower
        or "dod" in name_lower
        or "battery" in name_lower
        or "bms" in name_lower
    ):
        return ("battery_bms", "Battery BMS status registers")
    elif "version" in name_lower:
        return ("version_info", "Firmware version information")
    elif "firmware" in name_lower or "upgrade" in name_lower:
        return ("firmware", "Firmware upgrade addresses")
    elif "time" in name_lower or "day_hour" in name_lower or "year_month" in name_lower:
        return ("device_time", "Device time configuration")
    elif (
        "chart" in name_lower
        or "energy" in name_lower
        or "pv1_chart" in name_lower
        or "pv2_chart" in name_lower
    ):
        return ("chart_data", "Chart data start addresses")
    elif (
        "grid" in name_lower
        or "charge_custom" in name_lower
        or "immediate" in name_lower
    ):
        return ("grid_operations", "Grid operation parameters")
    elif "power" in name_lower:
        return ("power_control", "Power-related configuration")
    else:
        return ("general", "General purpose register")


def analyze_register_usages() -> Dict[str, List[RegisterUsageInfo]]:
    """Analyze how each register is used in the code"""

    # Load register map
    with open(REGISTER_MAP, "r") as f:
        register_map = json.load(f)

    with open(INPUT_JS, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract BLE commands
    ble_commands = extract_ble_commands(content)

    usages = defaultdict(list)

    for reg_name, reg_data in register_map.items():
        # Classify the register
        if isinstance(reg_data, list):
            cat = "multi_register"
            desc = f"Multi-register array: {reg_name}"
            # Use the first element for address if available
            addr = str(reg_data[0]) if reg_data else "unknown"
        elif isinstance(reg_data, int):
            addr = str(reg_data)
            cat, desc = classify_register_usage(reg_data, reg_name)
        else:
            # String value (likely for firmware addresses)
            cat = "firmware"
            desc = "Firmware address definition"
            addr = reg_name  # Use name as address indicator

        # Skip if we can't get a valid address
        try:
            addr_int = int(addr) if addr != "unknown" else -1
            usage_info = RegisterUsageInfo(
                address=addr_int,
                name=reg_name,
                category=cat,
                usage_description=desc,
                lines=[],
            )
            usages[addr].append(usage_info)
        except (ValueError, TypeError):
            # Skip invalid addresses
            pass

    return usages


def generate_report(usages: Dict[str, List[RegisterUsageInfo]]):
    """Generate comprehensive report files"""

    # Group by category
    by_category = defaultdict(list)
    for addr, usage_list in usages.items():
        for usage in usage_list:
            by_category[usage.category].append(
                {
                    "address": addr,
                    "name": usage.name,
                    "description": usage.usage_description,
                }
            )

    # Write category files
    for cat, items in by_category.items():
        filepath = os.path.join(OUTPUT_DIR, f"{cat}_registers.json")
        with open(filepath, "w") as f:
            json.dump(items, f, indent=2)

    # Write summary report
    summary_path = os.path.join(OUTPUT_DIR, "usage_summary.txt")
    with open(summary_path, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("REGISTER USAGE CASES ANALYSIS\n")
        f.write("=" * 80 + "\n\n")

        # Statistics
        total_regs = len(usages)
        f.write(f"Total registers analyzed: {total_regs}\n\n")

        # Category breakdown
        f.write("=" * 80 + "\n")
        f.write("REGISTER CATEGORIES\n")
        f.write("=" * 80 + "\n\n")

        for cat in sorted(by_category.keys()):
            items = by_category[cat]
            f.write(f"\n{cat.upper()} ({len(items)} registers)\n")
            f.write("-" * 40 + "\n")

            for item in sorted(items, key=lambda x: int(x["address"])):
                addr = int(item["address"])
                f.write(f"  0x{addr:04X} ({addr:>4}): {item['name']}\n")
                f.write(f"    {item['description']}\n")

        # Write comprehensive JSON report
        report = {}
        for addr, usage_list in usages.items():
            for usage in usage_list:
                report[str(addr)] = {
                    "name": usage.name,
                    "category": usage.category,
                    "description": usage.usage_description,
                }

        report_path = os.path.join(OUTPUT_DIR, "usage_report.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)


def main():
    print("Analyzing register usage cases...")

    if not os.path.exists(INPUT_JS):
        print(f"ERROR: {INPUT_JS} not found!")
        return

    usages = analyze_register_usages()
    generate_report(usages)

    # Print summary
    print(f"\nAnalyzed {len(usages)} registers")
    print("\nUsage categories found:")

    with open(INPUT_JS, "r") as f:
        content = f.read()

    # Print summary by category
    by_cat = defaultdict(list)
    for addr, us_list in usages.items():
        for usage in us_list:
            by_cat[usage.category].append(usage)

    print("\nRegisters by category:")
    for cat in sorted(by_cat.keys()):
        regs = by_cat[cat]
        print(f"\n{cat.upper()} ({len(regs)} registers):")
        for reg in sorted(regs, key=lambda x: x.address)[:15]:
            print(f"   {reg.name} (0x{reg.address:04X}: {reg.usage_description}")

    # Show BLE commands
    ble_commands = extract_ble_commands(content)
    print(f"\nBLE Commands ({len(ble_commands)} total):")
    for cmd_name, cmd_val in ble_commands[:15]:
        print(f"  {cmd_name}: {cmd_val}")

    print("\nReports written to:")
    print(f"  {OUTPUT_DIR}/usage_report.json")
    print(f"  {OUTPUT_DIR}/usage_summary.txt")


if __name__ == "__main__":
    main()
