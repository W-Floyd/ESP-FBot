"""Device profile lookup from the BrightEMS product catalog."""

from __future__ import annotations

from dataclasses import dataclass

from .product_catalog import CATEGORIES, PRODUCTS

# Map page_path fragments to a simple device type identifier.
# Longer/more-specific strings must come first so they match before their prefix.
_PAGE_PATH_TYPES: list[tuple[str, str]] = [
    ("portable-power-station-v1", "pps_v1"),
    ("portable-power-station", "pps"),
    ("switch-box", "switch_box"),
    ("balcony-pv", "balcony_pv"),
    ("dc-dc", "dc_dc"),
]

# Pre-build {uuid_upper: {local_name: product_info}} for O(1) lookup.
_INDEX: dict[str, dict[str, dict]] = {}
for _key, _prod in PRODUCTS.items():
    _uuid, _name = _key.split("_", 1)
    _INDEX.setdefault(_uuid, {})[_name] = {**_prod, "_product_key": _key}


@dataclass(frozen=True)
class DeviceProfile:
    """Resolved per-device capabilities from the product catalog."""

    product_key: str
    product_id: str
    category_id: str
    protocol_version: int
    modbus_address: int  # Modbus slave address byte used in every frame
    modbus_count: int  # Number of registers to request per read
    device_type: str  # One of: pps, pps_v1, switch_box, balcony_pv, dc_dc, unknown


def lookup_profile(service_uuids: list[str], local_name: str) -> DeviceProfile | None:
    """Return the DeviceProfile for a BLE device, or None if not in catalog.

    service_uuids: all UUIDs from the BLE advertisement (any format/case)
    local_name:    BLE local name exactly as advertised (e.g. "POWER-06C1")
    """
    for raw_uuid in service_uuids:
        uuid_upper = raw_uuid.upper()
        names = _INDEX.get(uuid_upper)
        if names is None:
            continue
        prod = names.get(local_name)
        if prod is None:
            continue
        cat = CATEGORIES.get(prod["category_id"], {})
        page_path = cat.get("page_path", "")
        device_type = "unknown"
        for fragment, dtype in _PAGE_PATH_TYPES:
            if fragment in page_path:
                device_type = dtype
                break
        return DeviceProfile(
            product_key=prod["_product_key"],
            product_id=prod["product_id"],
            category_id=prod["category_id"],
            protocol_version=prod["protocol_version"],
            modbus_address=cat.get("modbus_address", 0x11),
            modbus_count=cat.get("modbus_count", 80),
            device_type=device_type,
        )
    return None
