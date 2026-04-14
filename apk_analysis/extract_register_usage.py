#!/usr/bin/env python3
"""
Extract register usage from app-service-beautified.js
Analyzes the prettified JavaScript to extract:
- Register addresses used
- Operations (read/write)
- Variable names/identifiers
- Usage context (commands, callbacks, etc.)
"""

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_PATH = os.path.join(SCRIPT_DIR, "extracted/app-service-beautified.js")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "register_usage")
os.makedirs(OUTPUT_DIR, exist_ok=True)


@dataclass
class RegisterUsage:
    """Represents a register usage instance"""

    address: int
    name: str
    operation: str  # 'read' or 'write'
    context: str  # function/command context
    line_number: int
    snippet: str


def find_lines_with_context(
    content: str, start_pos: int, context_length: int = 100
) -> Tuple[str, int]:
    """Get the line number for a position in the file"""
    line_num = content[:start_pos].count("\n") + 1
    # Get surrounding context
    start = max(0, start_pos - context_length)
    end = min(len(content), start_pos + context_length)
    return content[start:end], line_num


def extract_register_usages(content: str) -> List[RegisterUsage]:
    """Extract all register usages from the beautified JavaScript"""
    usages = []

    # Pattern 1: Direct register address references in Modbus calls
    # Look for patterns like: getReadModbus(addr, 0x03, ...)
    modbus_call_pattern = re.compile(
        r"(getReadModbus|getWriteModbus|getReadModbusCRCLowFront|getWriteModbusCRCLowFront|getReadModbusCRCLowFront_new|getWriteModbusCRCLowFront_new)\s*\([^)]*0x[0-9a-fA-F]{2,4}[^)]*\)",
        re.MULTILINE | re.DOTALL,
    )

    # Pattern 2: Array-based register definitions (Wu constants)
    wu_array_pattern = re.compile(r"(\w+)\s*:\s*\[([^\]]{1,50})\]", re.MULTILINE)

    # Pattern 3: Object-based register definitions (numeric keys)
    wu_object_pattern = re.compile(r"(\w+)\s*:\s*(\d+)", re.MULTILINE)

    # Pattern 4: Register polling commands
    poll_pattern = re.compile(
        r"pol\s*=\s*(\d+)|poll\s*:\s*(\d+)|Poll\s*=\s*(\d+)", re.MULTILINE
    )

    # Pattern 5: BLE command register handlers
    ble_handler_pattern = re.compile(
        r"(GET_BLE_(?:SERVICES|CMD|READ|WRITE|POL|BLE_|INPUT|NETWORK|HOLDING|CONNECT)_\w*)\s*:",
        re.MULTILINE,
    )

    # Pattern 6: Register value assignments
    assign_pattern = re.compile(
        r"(?:reg|data|val|result|value|data\[?[\d\w]+?\]?)\s*=\s*(?:0x[0-9a-fA-F]+|\d+)",
        re.MULTILINE,
    )

    # Extract Wu register constants
    wu_match = re.search(
        r"const\s+Wu\s*=\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}", content, re.DOTALL
    )
    if wu_match:
        wu_content = wu_match.group(1)

        # Find register name -> address mappings
        reg_mappings = re.findall(
            r"(\w+)\s*:\s*0x([0-9a-fA-F]+)|(\w+)\s*:\s*(\d+)", wu_content
        )

        for match in reg_mappings:
            name = match[0] or match[2]
            addr_str = match[1] or match[3]
            try:
                if addr_str.startswith("0x"):
                    address = int(addr_str, 16)
                else:
                    address = int(addr_str)
                usages.append(
                    RegisterUsage(
                        address=address,
                        name=name,
                        operation="defined",
                        context="Wu constants",
                        line_number=content[: wu_match.start()].count("\n") + 1,
                        snippet=f"const Wu = {{ {name}: 0x{address:x} }}",
                    )
                )
            except ValueError:
                pass

        # Find array definitions
        array_matches = re.findall(r"(\w+)\s*:\s*\[([^\]]{1,100})\]", wu_content)
        for name, arr_str in array_matches:
            # Extract first element as address hint
            elem_match = re.search(r"(0x[0-9a-fA-F]+|\d+)", arr_str)
            if elem_match:
                try:
                    if elem_match.group(1).startswith("0x"):
                        address = int(elem_match.group(1), 16)
                    else:
                        address = int(elem_match.group(1))
                    usages.append(
                        RegisterUsage(
                            address=address,
                            name=name,
                            operation="array",
                            context="Wu constants array",
                            line_number=content[: wu_match.start()].count("\n") + 1,
                            snippet=f"Wu.{name} = [{elem_match.group(1)}]",
                        )
                    )
                except ValueError:
                    pass

    # Find BLE commands that reference registers
    ble_commands = re.findall(r'(GET_BLE_\w+)\s*:\s*"([^"]+)"', content)

    for cmd_name, cmd_value in ble_commands:
        # Check if this command references a register
        if any(
            keyword in cmd_value.lower()
            for keyword in ["reg", "addr", "read", "write", "poll"]
        ):
            usages.append(
                RegisterUsage(
                    address=-1,
                    name=cmd_name,
                    operation="command",
                    context="BLE command",
                    line_number=content.find(cmd_name),
                    snippet=f'{cmd_name}: "{cmd_value}"',
                )
            )

    # Find register polling operations
    polling_matches = re.findall(
        r"(?:getRead|poll)\s*\(.*?(\d+)\s*,\s*0x03", content, re.MULTILINE
    )

    for addr in polling_matches:
        try:
            address = int(addr)
            usages.append(
                RegisterUsage(
                    address=address,
                    name="poll",
                    operation="read_poll",
                    context="polling",
                    line_number=content.find(addr),
                    snippet=f"getReadModbus(..., {addr}, 0x03)",
                )
            )
        except ValueError:
            pass

    # Find register write operations
    write_matches = re.findall(
        r"(?:getWriteModbus)\s*\(.*?(\d+)\s*,\s*0x(?:03|06|07|10)\s*,",
        content,
        re.MULTILINE,
    )

    for addr in write_matches:
        try:
            address = int(addr)
            usages.append(
                RegisterUsage(
                    address=address,
                    name="write",
                    operation="write_poll",
                    context="write operation",
                    line_number=content.find(addr),
                    snippet=f"getWriteModbus(..., {addr}, 0x...)",
                )
            )
        except ValueError:
            pass

    # Extract specific register definitions from Wu object
    wu_defs = re.findall(
        r"(\w+)\s*:\s*(\d+|0x[0-9a-fA-F]+)(?:,\s*(?:\[\s*(\d{1,4})(?:\s*,\s*\d{1,4})*\s*\])?)?",
        wu_content if wu_match else "",
    )

    for defn in wu_defs:
        name, addr_str, array_info = defn
        try:
            if addr_str.startswith("0x"):
                address = int(addr_str, 16)
            else:
                address = int(addr_str)

            if array_info:
                op_type = "array_def"
                snippet = f"Wu.{name} = [{array_info}]"
            else:
                op_type = "single_def"
                snippet = f"Wu.{name} = 0x{address:x}"

            # Avoid duplicates
            if not any(u.address == address and u.name == name for u in usages):
                usages.append(
                    RegisterUsage(
                        address=address,
                        name=name,
                        operation=op_type,
                        context="Wu constant definition",
                        line_number=content.find(name),
                        snippet=snippet,
                    )
                )
        except ValueError:
            pass

    return usages


def group_by_address(usages: List[RegisterUsage]) -> Dict[int, List[RegisterUsage]]:
    """Group usages by register address"""
    groups = defaultdict(list)
    for usage in usages:
        groups[usage.address].append(usage)
    return dict(groups)


def group_by_operation(usages: List[RegisterUsage]) -> Dict[str, List[RegisterUsage]]:
    """Group usages by operation type"""
    groups = defaultdict(list)
    for usage in usages:
        groups[usage.operation].append(usage)
    return dict(groups)


def analyze_register_usage(usages: List[RegisterUsage]) -> Dict:
    """Analyze usage patterns"""
    analysis = {
        "total_usages": len(usages),
        "unique_registers": len(set(u.address for u in usages if u.address > 0)),
        "operations": group_by_operation(usages),
        "by_address": group_by_address(usages),
        "details": [],
    }

    # Find registers with both read and write operations
    reg_ops = defaultdict(set)
    for u in usages:
        if u.address > 0:
            reg_ops[u.address].add(u.operation)

    analysis["bidirectional_registers"] = [
        {"address": addr, "operations": list(ops)}
        for addr, ops in reg_ops.items()
        if len(ops) > 1
    ]

    return analysis


def write_report(usages: List[RegisterUsage], analysis: Dict):
    """Write the register usage report to files"""

    # Write JSON report
    report_json = os.path.join(OUTPUT_DIR, "register_usage_report.json")
    report_data = {
        "total_usages": analysis["total_usages"],
        "unique_registers": analysis["unique_registers"],
        "bidirectional_registers": analysis["bidirectional_registers"],
        "usages": [
            {
                "address": u.address,
                "name": u.name,
                "operation": u.operation,
                "context": u.context,
                "line": u.line_number,
                "snippet": u.snippet,
            }
            for u in usages
        ],
    }

    with open(report_json, "w") as f:
        json.dump(report_data, f, indent=2)

    # Write human-readable summary
    summary_txt = os.path.join(OUTPUT_DIR, "register_usage_summary.txt")
    with open(summary_txt, "w") as f:
        f.write("=" * 70 + "\n")
        f.write("REGISTER USAGE REPORT\n")
        f.write("=" * 70 + "\n\n")

        f.write(f"Total usages found: {analysis['total_usages']}\n")
        f.write(f"Unique registers: {analysis['unique_registers']}\n\n")

        f.write("=" * 70 + "\n")
        f.write("OPERATIONS BREAKDOWN\n")
        f.write("=" * 70 + "\n\n")

        for op_type, op_usages in analysis["operations"].items():
            f.write(f"\n{op_type.upper()} ({len(op_usages)} usages):\n")
            f.write("-" * 40 + "\n")
            for usage in sorted(op_usages, key=lambda x: x.address):
                f.write(
                    f"  Address 0x{usage.address:04X} ({usage.address:>4}) - {usage.name}\n"
                )
                f.write(f"    Context: {usage.context}\n")
                f.write(f"    Line {usage.line_number}: {usage.snippet[:80]}\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("REGISTER DETAILS\n")
        f.write("=" * 70 + "\n\n")

        # Group by address
        by_addr = group_by_address(usages)
        for addr in sorted(by_addr.keys()):
            if addr <= 0:
                continue

            usages_at_addr = by_addr[addr]
            f.write(f"\nRegister 0x{addr:04X} ({addr:>4}):")
            for usage in usages_at_addr:
                f.write(f"\n  - {usage.name}: {usage.context}")
                f.write(f"\n    {usage.snippet[:100]}")

        f.write("\n" + "=" * 70 + "\n")
        f.write("BIDIRECTIONAL REGISTERS (read + write)\n")
        f.write("=" * 70 + "\n\n")

        for bidir in analysis["bidirectional_registers"]:
            f.write(f"Address 0x{bidir['address']:04X}: {bidir['operations']}\n")

    # Write categorized output files
    by_op = group_by_operation(usages)

    for op_type, op_usages in by_op.items():
        if op_type in ["defined", "array", "single_def"]:
            filename = f"{op_type}s.json"
        else:
            filename = f"{op_type}.json"

        filepath = os.path.join(OUTPUT_DIR, filename)
        with open(filepath, "w") as f:
            json.dump(
                [
                    {
                        "address": u.address,
                        "name": u.name,
                        "context": u.context,
                        "line": u.line_number,
                        "snippet": u.snippet,
                    }
                    for u in op_usages
                ],
                f,
                indent=2,
            )

    return report_json, summary_txt


def main():
    """Main entry point"""
    print(f"Reading: {INPUT_PATH}")

    if not os.path.exists(INPUT_PATH):
        print(f"ERROR: {INPUT_PATH} not found!")
        return

    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    print(f"File size: {len(content):,} bytes")
    print("\nExtracting register usages...")

    usages = extract_register_usages(content)
    print(f"Found {len(usages)} register usages")

    analysis = analyze_register_usage(usages)
    print(f"Unique registers: {analysis['unique_registers']}")

    report_json, summary_txt = write_report(usages, analysis)
    print(f"\nReports written to:")
    print(f"  - {report_json}")
    print(f"  - {summary_txt}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total usages: {analysis['total_usages']}")
    print(f"Unique registers: {analysis['unique_registers']}")

    if analysis["bidirectional_registers"]:
        print(
            f"\nBidirectional registers (read+write): {len(analysis['bidirectional_registers'])}"
        )
        for bidir in analysis["bidirectional_registers"][:10]:
            print(f"  0x{bidir['address']:04X}: {bidir['operations']}")


if __name__ == "__main__":
    main()
