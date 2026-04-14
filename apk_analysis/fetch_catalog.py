#!/usr/bin/env python3
"""
Fetch the BrightEMS product catalog from uniCloud and write it as a static
Python module at custom_components/fbot/product_catalog.py.

Run once whenever the upstream catalog may have changed:
    python3 apk_analysis/fetch_catalog.py
"""

import hashlib
import hmac
import json
import pathlib
import textwrap
import time
import urllib.request

# ── uniCloud credentials (from app-service.js) ────────────────────────────────
SPACE_ID = "mp-6c382a98-49b8-40ba-b761-645d83e8ee74"
CLIENT_SECRET = "5rCEdl/nx7IgViBe4QYRiQ=="
ENDPOINT = "https://api.next.bspapp.com/client"

OUT_PATH = (
    pathlib.Path(__file__).parent.parent
    / "custom_components"
    / "fbot"
    / "product_catalog.py"
)
MANIFEST_PATH = (
    pathlib.Path(__file__).parent.parent
    / "custom_components"
    / "fbot"
    / "manifest.json"
)


# ── uniCloud transport ─────────────────────────────────────────────────────────


def _sign(data: dict, secret: str) -> str:
    """HmacMD5 over sorted key=value pairs (replicates JS zs() function)."""
    parts = "&".join(f"{k}={data[k]}" for k in sorted(data) if data[k])
    return hmac.new(secret.encode(), parts.encode(), hashlib.md5).hexdigest()


def _post(body: dict, token: str | None = None) -> dict:
    if token:
        body["token"] = token
    sig = _sign(body, CLIENT_SECRET)
    headers = {"Content-Type": "application/json", "x-serverless-sign": sig}
    if token:
        headers["x-basement-token"] = token
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=15)
    return json.loads(resp.read())


def _call(url: str, token: str) -> dict:
    ts = int(time.time() * 1000)
    result = _post(
        {
            "method": "serverless.function.runtime.invoke",
            "params": json.dumps(
                {
                    "functionTarget": "router",
                    "functionArgs": {
                        "$url": url,
                        "clientInfo": {"uniPlatform": "app"},
                    },
                }
            ),
            "spaceId": SPACE_ID,
            "timestamp": ts,
        },
        token,
    )
    # Unwrap nested response layers
    data = result.get("data") or result.get("result") or result
    if isinstance(data, dict) and "data" in data:
        data = data["data"]
    return data


def _get_token() -> str:
    ts = int(time.time() * 1000)
    result = _post(
        {
            "method": "serverless.auth.user.anonymousAuthorize",
            "params": "{}",
            "spaceId": SPACE_ID,
            "timestamp": ts,
        }
    )
    return result["data"]["accessToken"]


# ── fetch ──────────────────────────────────────────────────────────────────────


def fetch() -> dict:
    print("Authenticating...")
    token = _get_token()

    print("Fetching product list (UUID + name)...")
    prod_list_data = _call("client/product/pub/listProductByWhereJson_v2", token)
    products_simple = prod_list_data.get("rows", [])
    print(f"  {len(products_simple)} products")

    print("Fetching full product detail list...")
    detail_data = _call("client/product/pub/getAllProductList", token)
    all_products = detail_data.get("allProducts", detail_data)
    print(f"  {len(all_products.get('products', []))} products with feature modules")
    print(f"  {len(all_products.get('state_list_all', []))} state features")
    print(f"  {len(all_products.get('setting_list_all', []))} setting features")
    print(f"  {len(all_products.get('category_list_all', []))} categories")

    return {
        "products_simple": products_simple,
        "products_detail": all_products.get("products", []),
        "state_list_all": all_products.get("state_list_all", []),
        "setting_list_all": all_products.get("setting_list_all", []),
        "category_list_all": all_products.get("category_list_all", []),
    }


# ── build catalog ──────────────────────────────────────────────────────────────


def build_catalog(raw: dict) -> dict:
    """
    Returns a clean catalog dict with the following structure:

    CATEGORIES: {category_id: {modbus_address, modbus_count, page_path}}
    PRODUCTS:   {uuid_name_key: {product_id, category_id, protocol_version}}
    FEATURES:   {product_id: {states: [...], settings: [...]}}

    Each state:   {id, function_name, holding_index, input_index, children: [{...}]}
    Each setting: {id, function_name, holding_index, data_list, unit}
    """
    # ── categories ──
    categories = {}
    for cat in raw["category_list_all"]:
        categories[cat["_id"]] = {
            "modbus_address": cat.get("modbus_address", 0x11),
            "modbus_count": cat.get("modbus_count", 80),
            "page_path": cat.get("page_path", ""),
        }

    # ── state & setting lookup maps ──
    state_by_id = {s["_id"]: s for s in raw["state_list_all"]}
    setting_by_id = {s["_id"]: s for s in raw["setting_list_all"]}

    # ── join simple (uuid/name) with detail (category_id/function_module) by _id ──
    detail_by_id = {p["_id"]: p for p in raw["products_detail"]}

    # ── full feature map per product ──
    features_by_product: dict[str, dict] = {}
    for prod in raw["products_detail"]:
        pid = prod["_id"]
        fm = prod.get("function_module", {})

        # Resolve state list — top-level entries only; children attached below
        state_parents: dict[str, dict] = {}
        state_order: list[str] = []
        for sid in fm.get("state_list_ids", []):
            s = state_by_id.get(sid)
            if s is None:
                continue
            if s.get("parent_id"):
                # Child — attach to parent if we've seen it
                parent = state_parents.get(s["parent_id"])
                if parent is not None:
                    parent["children"].append(
                        {
                            "id": s["_id"],
                            "function_name": s.get("function_name", ""),
                            "input_index": s.get("input_index"),
                            "icon": s.get("icon", ""),
                        }
                    )
            else:
                entry = {
                    "id": s["_id"],
                    "function_name": s.get("function_name", ""),
                    "holding_index": s.get("holding_index"),
                    "input_index": s.get("input_index"),
                    "protocol_version": s.get("protocol_version", 0),
                    "children": [],
                }
                state_parents[s["_id"]] = entry
                state_order.append(s["_id"])
        states = [state_parents[sid] for sid in state_order if sid in state_parents]

        # Resolve setting list
        settings = []
        for sid in fm.get("setting_list_ids", []):
            s = setting_by_id.get(sid)
            if s is None:
                continue
            unit = ""
            if s.get("unit_list"):
                unit = s["unit_list"][0].get("lang_text", "")
            settings.append(
                {
                    "id": s["_id"],
                    "function_name": s.get("function_name", ""),
                    "holding_index": s.get("holding_index"),
                    "input_index": s.get("input_index"),
                    "data_list": s.get("data_list", []),
                    "data_state": s.get("data_state", False),
                    "protocol_version": s.get("protocol_version", 0),
                    "unit": unit,
                }
            )

        features_by_product[pid] = {"states": states, "settings": settings}

    # ── product map: uuid+name key → product meta ──
    products: dict[str, dict] = {}
    for prod in raw["products_simple"]:
        uuid = prod.get("uuid", "").upper()
        name = prod.get("name", "")
        if not uuid or not name:
            continue
        key = f"{uuid}_{name}"
        detail = detail_by_id.get(prod["_id"], {})
        products[key] = {
            "product_id": prod["_id"],
            "category_id": detail.get("category_id", ""),
            "protocol_version": prod.get("protocol_version", 0),
        }

    return {
        "categories": categories,
        "products": products,
        "features": features_by_product,
    }


# ── write Python module ────────────────────────────────────────────────────────

MODULE_HEADER = '''\
"""
BrightEMS product catalog — auto-generated by apk_analysis/fetch_catalog.py.
DO NOT EDIT BY HAND.

Catalog data © BrightEMS / Sydpower. Fetched from their uniCloud backend.
"""
# ruff: noqa
# fmt: off

'''


def write_module(catalog: dict, path: pathlib.Path) -> None:
    lines = [MODULE_HEADER]

    def repr_compact(obj, indent=0) -> str:
        """Format dicts/lists more compactly than pprint."""
        pad = "    " * indent
        pad1 = "    " * (indent + 1)
        if isinstance(obj, dict):
            if not obj:
                return "{}"
            inner = ",\n".join(
                f"{pad1}{repr(k)}: {repr_compact(v, indent + 1)}"
                for k, v in obj.items()
            )
            return "{\n" + inner + ",\n" + pad + "}"
        if isinstance(obj, list):
            if not obj:
                return "[]"
            # Keep short flat lists on one line
            if (
                all(not isinstance(x, (dict, list)) for x in obj)
                and len(repr(obj)) < 80
            ):
                return repr(obj)
            inner = ",\n".join(f"{pad1}{repr_compact(v, indent + 1)}" for v in obj)
            return "[\n" + inner + ",\n" + pad + "]"
        return repr(obj)

    for varname, value in catalog.items():
        lines.append(f"{varname.upper()} = {repr_compact(value, 0)}\n\n")

    path.write_text("".join(lines))
    print(f"Wrote {path} ({path.stat().st_size:,} bytes)")


# ── write manifest ─────────────────────────────────────────────────────────────


def write_manifest(catalog: dict, path: pathlib.Path) -> None:
    """Regenerate the bluetooth discovery matchers in manifest.json.

    Each product in the catalog advertises its own unique service UUID, so
    every UUID must be listed in the manifest for Home Assistant to trigger
    automatic Bluetooth discovery.
    """
    uuids = sorted({key.split("_", 1)[0].lower() for key in catalog["products"]})

    manifest = json.loads(path.read_text())
    manifest["bluetooth"] = [
        {"service_uuid": uuid, "connectable": True} for uuid in uuids
    ]
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {path} ({len(uuids)} bluetooth matchers)")


# ── main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    raw = fetch()
    catalog = build_catalog(raw)

    print(f"\nCatalog summary:")
    print(f"  {len(catalog['categories'])} categories")
    print(f"  {len(catalog['products'])} products")
    print(f"  {len(catalog['features'])} products with feature data")

    write_module(catalog, OUT_PATH)
    write_manifest(catalog, MANIFEST_PATH)
    print("\nDone.")
