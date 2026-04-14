#!/usr/bin/env python3
"""
Unminify app-service.js
Uses jsbeautifier to prettify the minified JavaScript into a readable format.
"""

import os
import sys

# Try to import jsbeautifier
try:
    import jsbeautifier
except ImportError:
    print("ERROR: jsbeautifier not installed.")
    print("Install with: pip install js-beautifier")
    sys.exit(1)

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_SERVICE_PATH = os.path.join(
    SCRIPT_DIR, "decompiled/resources/assets/apps/__UNI__55F5E7F/www/app-service.js"
)
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "extracted")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "app-service-beautified.js")

os.makedirs(OUTPUT_DIR, exist_ok=True)

if not os.path.exists(APP_SERVICE_PATH):
    print(f"ERROR: {APP_SERVICE_PATH} not found!")
    sys.exit(1)

print(f"Loading: {APP_SERVICE_PATH}")
print(f"File size: {os.path.getsize(APP_SERVICE_PATH):,} bytes")

with open(APP_SERVICE_PATH, "r", encoding="utf-8") as f:
    minified_content = f.read()

print(f"\nUnminifying with jsbeautifier...")

# Configure beautifier options
opts = jsbeautifier.default_options()
opts.indent_size = 2
opts.preserve_newlines = True
opts.max_preserve_newlines = 2

try:
    beautified_content = jsbeautifier.beautify(minified_content, opts)
except Exception as e:
    print(f"ERROR during beautification: {e}")
    sys.exit(1)

with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    f.write(beautified_content)

print(f"✓ Successfully wrote beautified output to: {OUTPUT_PATH}")
print(f"  Original size: {len(minified_content):,} bytes")
print(f"  Beautified size: {len(beautified_content):,} bytes")
print(f"\nDone!")
