import asyncio
import threading
import time
from flask import Flask, render_template, jsonify
from bleak import BleakScanner

app = Flask(__name__)

# ---------------------------------------------------------------
# ASSET REGISTRY
# Match strategies (set as many as you want per asset):
#   "ibeacon_uuid" : UUID found in iBeacon manufacturer payload
#   "address"      : BLE MAC address (case-insensitive)
#   "name"         : Advertised device name (substring, case-insensitive)
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
            "address": "66:77:88:99:AA:BB",
        }
    }
}

LATEST_DATA = {}
NEARBY_DEVICES = []


# -----------------------------
# iBeacon UUID PARSER
# -----------------------------
def parse_ibeacon_uuid(data: bytes):
    """
    Extract UUID from raw iBeacon manufacturer payload.
    iBeacon: 02 15 <16-byte UUID> <major 2b> <minor 2b> <tx power 1b>
    """
    try:
        hex_data = data.hex().lower()
        idx = hex_data.find("0215")
        if idx != -1:
            uuid_hex = hex_data[idx + 4: idx + 4 + 32]
            if len(uuid_hex) == 32:
                return (
                    uuid_hex[0:8]   + "-" +
                    uuid_hex[8:12]  + "-" +
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
        return {"status": "Unknown",   "class": "secondary", "desc": "No Signal Data"}
    if rssi >= -60:
        return {"status": "Immediate", "class": "success",   "desc": "< 1.5m"}
    elif rssi >= -80:
        return {"status": "Near",      "class": "warning",   "desc": "1.5m – 5m"}
    else:
        return {"status": "Far",       "class": "danger",    "desc": "> 5m"}


# -----------------------------
# ASSET MATCHER
# -----------------------------
def match_device(device, adv):
    """Return asset_id if the device matches any registered rule, else None."""
    address  = (device.address or "").upper()
    adv_name = (adv.local_name or device.name or "").lower()
    mfr_data = adv.manufacturer_data or {}

    # Parse iBeacon UUID from all manufacturer payloads
    detected_uuid = None
    for payload in mfr_data.values():
        u = parse_ibeacon_uuid(payload)
        if u:
            detected_uuid = u
            break

    # Flat hex string for raw substring fallback
    all_hex = "".join(v.hex() for v in mfr_data.values()).lower()

    for asset_id, asset in TARGET_ASSETS.items():
        rules = asset.get("match", {})

        if "ibeacon_uuid" in rules:
            target     = rules["ibeacon_uuid"].upper()
            target_raw = target.replace("-", "").lower()
            if detected_uuid and detected_uuid == target:
                return asset_id
            if target_raw in all_hex:          # raw hex fallback
                return asset_id

        if "address" in rules:
            if address == rules["address"].upper():
                return asset_id

        if "name" in rules:
            if rules["name"].lower() in adv_name:
                return asset_id

    return None


# ---------------------------------------------------------------
# BLE SCANNER LOOP
#
# THE KEY FIX: return_adv=True
#   Without it, BleakScanner.discover() returns BLEDevice objects
#   that do NOT reliably carry RSSI or manufacturer_data on Windows.
#   With return_adv=True it returns:
#       { address: (BLEDevice, AdvertisementData) }
#   AdvertisementData has .rssi, .manufacturer_data, .local_name, etc.
# ---------------------------------------------------------------
async def ble_scanner_loop():
    global LATEST_DATA, NEARBY_DEVICES

    while True:
        try:
            results = await BleakScanner.discover(timeout=3.0, return_adv=True)

            nearby   = []
            scan_out = {}

            # Initialise all assets as offline
            for asset_id, info in TARGET_ASSETS.items():
                scan_out[asset_id] = {
                    "name":      info["name"],
                    "dept":      info["dept"],
                    "rssi":      "N/A",
                    "status":    "Offline",
                    "class":     "secondary",
                    "desc":      "Not Detected",
                    "last_seen": "-"
                }

            print(f"\n--- Scan: {len(results)} device(s) found ---")

            for address, (device, adv) in results.items():
                rssi = adv.rssi
                name = adv.local_name or device.name or "Unknown Device"

                nearby.append({
                    "name":    name,
                    "address": device.address,
                    "rssi":    f"{rssi} dBm" if rssi is not None else "N/A"
                })

                # Print every device so you can verify your phone appears
                mfr_keys = list(adv.manufacturer_data.keys())
                print(f"  [{device.address}] {name:<30} RSSI: {rssi:>5}  MFR: {mfr_keys}")

                asset_id = match_device(device, adv)
                if asset_id:
                    prox = estimate_proximity(rssi)
                    scan_out[asset_id].update({
                        "rssi":      f"{rssi} dBm" if rssi is not None else "N/A",
                        "status":    prox["status"],
                        "class":     prox["class"],
                        "desc":      prox["desc"],
                        "last_seen": time.strftime("%H:%M:%S")
                    })
                    print(f"  ✅ MATCHED → {TARGET_ASSETS[asset_id]['name']} | "
                          f"RSSI: {rssi} | {prox['status']}")

            # Sort nearest first
            def rssi_sort_key(d):
                try:
                    return int(d["rssi"].split()[0])
                except Exception:
                    return -999

            NEARBY_DEVICES = sorted(nearby, key=rssi_sort_key, reverse=True)
            LATEST_DATA    = scan_out

        except Exception as e:
            print(f"Scanner Error: {e}")

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