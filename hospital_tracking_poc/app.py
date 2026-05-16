import asyncio
import threading
import time
from flask import Flask, render_template, jsonify
from bleak import BleakScanner

app = Flask(__name__)

# ---------------------------------------------------------------
# ASSET REGISTRY
# Each asset can match by:
#   - "ibeacon_uuid" : UUID found in iBeacon manufacturer payload
#   - "address"      : BLE MAC address (case-insensitive)
#   - "name"         : Advertised device name (substring match)
# You can set multiple match keys per asset for redundancy.
# ---------------------------------------------------------------
TARGET_ASSETS = {
    "asset_phone": {
        "name": "My Custom Phone Beacon",
        "dept": "MIS DEPARTMENT",
        "match": {
            "ibeacon_uuid": "C216FE14-8047-4978-92C3-68919B540D4F",
        }
    },
    "asset_pump": {
        "name": "Asset 2 (Infusion Pump)",
        "dept": "EMERGENCY ROOM",
        "match": {
            "address": "66:77:88:99:AA:BB",   # MAC address match
            # "name": "InfusionPump"           # uncomment as fallback
        }
    }
}

LATEST_DATA = {}
NEARBY_DEVICES = []


# -----------------------------
# RSSI SAFE EXTRACTION
# -----------------------------
def get_rssi(device):
    """Try all Bleak-compatible RSSI sources."""
    if hasattr(device, 'rssi') and device.rssi is not None:
        return device.rssi
    try:
        return device.details["props"]["RSSI"]
    except Exception:
        return None


# -----------------------------
# iBeacon UUID PARSER
# -----------------------------
def parse_ibeacon_uuid(hex_data: str):
    """Extract UUID from iBeacon manufacturer payload (02 15 prefix)."""
    try:
        if "0215" in hex_data:
            uuid_hex = hex_data.split("0215")[1][0:32]
            if len(uuid_hex) < 32:
                return None
            return (
                uuid_hex[0:8] + "-" +
                uuid_hex[8:12] + "-" +
                uuid_hex[12:16] + "-" +
                uuid_hex[16:20] + "-" +
                uuid_hex[20:]
            ).upper()
    except Exception:
        pass
    return None


# -----------------------------
# PROXIMITY MODEL
# -----------------------------
def estimate_proximity(rssi):
    if rssi is None:
        return {"status": "Unknown", "class": "secondary", "desc": "No Signal Data"}
    if rssi >= -60:
        return {"status": "Immediate", "class": "success", "desc": "< 1.5m"}
    elif rssi >= -80:
        return {"status": "Near", "class": "warning", "desc": "1.5m – 5m"}
    else:
        return {"status": "Far", "class": "danger", "desc": "> 5m"}


# -----------------------------
# ASSET MATCHER
# Returns asset_id if the device matches any rule, else None.
# -----------------------------
def match_device_to_asset(device, rssi):
    device_address = (device.address or "").upper()
    device_name    = (device.name or "").lower()

    # Extract iBeacon UUID from manufacturer data
    md = getattr(device, "metadata", {}).get("manufacturer_data", {})
    detected_uuid = None
    for company_id, data in md.items():
        hex_data = data.hex().lower()
        detected_uuid = parse_ibeacon_uuid(hex_data)
        if detected_uuid:
            break

    for asset_id, asset in TARGET_ASSETS.items():
        rules = asset.get("match", {})

        # Rule 1: iBeacon UUID
        if "ibeacon_uuid" in rules and detected_uuid:
            if detected_uuid.upper() == rules["ibeacon_uuid"].upper():
                return asset_id

        # Rule 1b: raw UUID substring search (belt-and-suspenders)
        if "ibeacon_uuid" in rules:
            target_raw = rules["ibeacon_uuid"].replace("-", "").lower()
            for company_id, data in md.items():
                if target_raw in data.hex().lower():
                    return asset_id

        # Rule 2: MAC address
        if "address" in rules:
            if device_address == rules["address"].upper():
                return asset_id

        # Rule 3: advertised name (substring)
        if "name" in rules:
            if rules["name"].lower() in device_name:
                return asset_id

    return None


# -----------------------------
# BLE SCANNER LOOP
# -----------------------------
async def ble_scanner_loop():
    global LATEST_DATA, NEARBY_DEVICES

    while True:
        try:
            devices = await BleakScanner.discover(timeout=3.0)

            NEARBY_DEVICES = []
            current_scan = {}

            # Initialise all assets as offline
            for asset_id, info in TARGET_ASSETS.items():
                current_scan[asset_id] = {
                    "name":      info["name"],
                    "dept":      info["dept"],
                    "rssi":      "N/A",
                    "status":    "Offline",
                    "class":     "secondary",
                    "desc":      "Not Detected",
                    "last_seen": "-"
                }

            for device in devices:
                rssi = get_rssi(device)
                display_name = device.name or "Unknown Device"

                # Populate nearby-devices list (all BLE, for diagnostics)
                NEARBY_DEVICES.append({
                    "name":    display_name,
                    "address": device.address,
                    "rssi":    f"{rssi} dBm" if rssi is not None else "N/A"
                })

                # Try to match this device to a tracked asset
                asset_id = match_device_to_asset(device, rssi)
                if asset_id:
                    prox = estimate_proximity(rssi)
                    current_scan[asset_id].update({
                        "rssi":      f"{rssi} dBm" if rssi is not None else "N/A",
                        "status":    prox["status"],
                        "class":     prox["class"],
                        "desc":      prox["desc"],
                        "last_seen": time.strftime("%H:%M:%S")
                    })
                    print(f"✅ Matched: {TARGET_ASSETS[asset_id]['name']} | "
                          f"RSSI: {rssi} dBm | Proximity: {prox['status']}")

            LATEST_DATA = current_scan

        except Exception as e:
            print("Scanner Error:", e)

        await asyncio.sleep(1)


# -----------------------------
# THREAD WRAPPER
# -----------------------------
def start_ble_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ble_scanner_loop())


# -----------------------------
# FLASK ROUTES
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/assets")
def get_assets():
    return jsonify(list(LATEST_DATA.values()))


@app.route("/api/nearby")
def nearby():
    return jsonify(NEARBY_DEVICES)


# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    scanner_thread = threading.Thread(target=start_ble_loop, daemon=True)
    scanner_thread.start()
    app.run(debug=True, port=5000)
