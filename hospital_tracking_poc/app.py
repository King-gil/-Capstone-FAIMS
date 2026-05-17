import asyncio
import threading
import time
from flask import Flask, render_template, jsonify
from bleak import BleakScanner

app = Flask(__name__)

# ---------------------------------------------------------------
# ASSET REGISTRY
# ---------------------------------------------------------------
TARGET_ASSETS = {
    "asset_phone": {
        "name": "Jhared's Phone",
        "dept": "MIS DEPARTMENT",
        "match": {
            "ibeacon_uuid": "C216FE14-8047-4978-92C3-68919B540D4F",
        }
    },
    "asset_pump": {
        "name": "Joshua's Phone",
        "dept": "EMERGENCY ROOM",
        "match": {
            "ibeacon_uuid": "00112233-4455-6677-8899-AABBCCDDEEFF",
        }
    }
}

# Known BLE company IDs (subset of Bluetooth SIG registry)
COMPANY_IDS = {
    6:    "Microsoft",
    76:   "Apple",
    89:   "Nordic Semiconductor",
    117:  "Samsung",
    224:  "Google",
    343:  "Garmin",
    1177: "Tile",
}

LATEST_DATA    = {}
NEARBY_DEVICES = []


# -----------------------------
# iBeacon UUID PARSER
# -----------------------------
def parse_ibeacon_uuid(data: bytes):
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
# IBEACON FULL PARSER
# Returns major, minor, tx_power from payload
# -----------------------------
def parse_ibeacon_full(data: bytes):
    try:
        hex_data = data.hex().lower()
        idx = hex_data.find("0215")
        if idx != -1:
            base = idx + 4
            if len(hex_data) >= base + 44:
                major    = int(hex_data[base + 32: base + 36], 16)
                minor    = int(hex_data[base + 36: base + 40], 16)
                tx_power = int(hex_data[base + 40: base + 42], 16)
                # tx_power is signed byte
                if tx_power > 127:
                    tx_power -= 256
                return major, minor, tx_power
    except Exception:
        pass
    return None, None, None


# -----------------------------
# DISTANCE ESTIMATOR
# Uses log-distance path loss model
# -----------------------------
def estimate_distance(rssi, tx_power, path_loss_exp=2.0):
    """
    Returns estimated distance in metres.
    tx_power: measured RSSI at 1m (from iBeacon payload or use -59 default)
    path_loss_exp: 2.0 = free space, 3.0-4.0 = indoor with obstacles
    """
    if rssi is None or tx_power is None:
        return None
    try:
        import math
        distance = 10 ** ((tx_power - rssi) / (10 * path_loss_exp))
        return round(distance, 2)
    except Exception:
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
# FULL ADV DATA EXTRACTOR
# Pulls every available field from device + adv
# -----------------------------
def extract_adv_data(device, adv):
    rssi     = adv.rssi
    mfr_data = adv.manufacturer_data or {}

    # --- Manufacturer data ---
    manufacturers = []
    ibeacon_uuid  = None
    ibeacon_major = None
    ibeacon_minor = None
    ibeacon_tx    = None

    for company_id, payload in mfr_data.items():
        company_name = COMPANY_IDS.get(company_id, f"Unknown (ID {company_id})")
        hex_payload  = payload.hex().upper()

        uuid = parse_ibeacon_uuid(payload)
        if uuid:
            ibeacon_uuid  = uuid
            major, minor, tx = parse_ibeacon_full(payload)
            ibeacon_major = major
            ibeacon_minor = minor
            ibeacon_tx    = tx

        manufacturers.append({
            "company_id":   company_id,
            "company_name": company_name,
            "hex_payload":  hex_payload,
            "ibeacon_uuid": uuid
        })

    # --- Service data ---
    service_data_parsed = []
    for svc_uuid, svc_bytes in (adv.service_data or {}).items():
        service_data_parsed.append({
            "uuid":    svc_uuid,
            "hex":     svc_bytes.hex().upper(),
            "bytes":   len(svc_bytes)
        })

    # --- Distance estimate ---
    # Prefer iBeacon tx_power, fall back to adv.tx_power, then default -59 dBm
    ref_tx   = ibeacon_tx or adv.tx_power or -59
    distance = estimate_distance(rssi, ref_tx)

    # --- Device type hint from company ID ---
    device_type = "Unknown"
    for company_id in mfr_data.keys():
        if company_id == 76:
            device_type = "Apple Device"
        elif company_id == 117:
            device_type = "Samsung Device"
        elif company_id == 6:
            device_type = "Microsoft Device"
        elif company_id == 224:
            device_type = "Google Device"

    return {
        # --- BLEDevice fields ---
        "address":          device.address,
        "device_name":      device.name or "—",

        # --- AdvertisementData fields ---
        "local_name":       adv.local_name or "—",
        "rssi":             rssi,
        "tx_power":         adv.tx_power,           # advertised TX power (may be None)
        "service_uuids":    adv.service_uuids or [],
        "service_data":     service_data_parsed,
        "manufacturers":    manufacturers,

        # --- Parsed iBeacon fields ---
        "ibeacon_uuid":     ibeacon_uuid,
        "ibeacon_major":    ibeacon_major,
        "ibeacon_minor":    ibeacon_minor,
        "ibeacon_tx_power": ibeacon_tx,

        # --- Derived fields ---
        "distance_m":       distance,
        "device_type":      device_type,
    }


# -----------------------------
# ASSET MATCHER
# -----------------------------
def match_device(device, adv, extracted):
    address  = (device.address or "").upper()
    adv_name = (adv.local_name or device.name or "").lower()
    mfr_data = adv.manufacturer_data or {}
    all_hex  = "".join(v.hex() for v in mfr_data.values()).lower()

    for asset_id, asset in TARGET_ASSETS.items():
        rules = asset.get("match", {})

        if "ibeacon_uuid" in rules:
            target     = rules["ibeacon_uuid"].upper()
            target_raw = target.replace("-", "").lower()
            if extracted["ibeacon_uuid"] and extracted["ibeacon_uuid"] == target:
                return asset_id
            if target_raw in all_hex:
                return asset_id

        if "address" in rules:
            if address == rules["address"].upper():
                return asset_id

        if "name" in rules:
            if rules["name"].lower() in adv_name:
                return asset_id

    return None


# -----------------------------
# BLE SCANNER LOOP
# -----------------------------
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
                    "rssi":      None,
                    "status":    "Offline",
                    "class":     "secondary",
                    "desc":      "Not Detected",
                    "last_seen": "-",
                    "adv":       None        # full adv data block
                }

            print(f"\n--- Scan: {len(results)} device(s) ---")

            for address, (device, adv) in results.items():
                extracted = extract_adv_data(device, adv)
                rssi      = extracted["rssi"]
                name      = extracted["local_name"] if extracted["local_name"] != "—" \
                            else extracted["device_name"]

                nearby.append({
                    "name":         name,
                    "address":      extracted["address"],
                    "rssi":         rssi,
                    "tx_power":     extracted["tx_power"],
                    "device_type":  extracted["device_type"],
                    "local_name":   extracted["local_name"],
                    "device_name":  extracted["device_name"],
                    "service_uuids":extracted["service_uuids"],
                    "service_data": extracted["service_data"],
                    "manufacturers":extracted["manufacturers"],
                    "ibeacon_uuid": extracted["ibeacon_uuid"],
                    "ibeacon_major":extracted["ibeacon_major"],
                    "ibeacon_minor":extracted["ibeacon_minor"],
                    "ibeacon_tx_power": extracted["ibeacon_tx_power"],
                    "distance_m":   extracted["distance_m"],
                })

                print(f"  [{extracted['address']}] {name:<28} "
                      f"RSSI:{rssi:>5}  TX:{str(extracted['tx_power']):>5}  "
                      f"Dist:{extracted['distance_m']}m  "
                      f"Type:{extracted['device_type']}")

                asset_id = match_device(device, adv, extracted)
                if asset_id:
                    prox = estimate_proximity(rssi)
                    scan_out[asset_id].update({
                        "rssi":      rssi,
                        "status":    prox["status"],
                        "class":     prox["class"],
                        "desc":      prox["desc"],
                        "last_seen": time.strftime("%H:%M:%S"),
                        "adv":       extracted
                    })
                    print(f"  ✅ MATCHED → {TARGET_ASSETS[asset_id]['name']} | "
                          f"RSSI:{rssi} | {prox['status']} | "
                          f"~{extracted['distance_m']}m")

            # Sort nearby: strongest RSSI first
            NEARBY_DEVICES = sorted(
                nearby,
                key=lambda d: d["rssi"] if d["rssi"] is not None else -999,
                reverse=True
            )
            LATEST_DATA = scan_out

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