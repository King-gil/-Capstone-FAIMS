import asyncio
import threading
import time
from flask import Flask, render_template, jsonify
from bleak import BleakScanner

app = Flask(__name__)

# iBeacon UUID registry (this is correct for simulators)
TARGET_ASSETS = {
   "F99EF136-9609-4CED-BF67-8B69C8999A8C": {
        "name": "My Custom Phone Beacon",  # <--- Change your beacon's name here
        "dept": "MIS DEPARTMENT"           # <--- You can also change the department
    },
    "66:77:88:99:AA:BB": {
        "name": "Asset 2 (Infusion Pump)",
        "dept": "EMERGENCY ROOM"
    }
}

LATEST_DATA = {}
NEARBY_DEVICES = []


# -----------------------------
# RSSI SAFE EXTRACTION
# -----------------------------
def get_rssi(device):
    """Try all Bleak-compatible RSSI sources."""
    
    # 1. Try the standard property used in modern Bleak versions
    if hasattr(device, 'rssi') and device.rssi is not None:
        return device.rssi
        
    # 2. Fallback to the dictionary method for older setups
    try:
        return device.details["props"]["RSSI"]
    except Exception:
        return None


# -----------------------------
# iBeacon UUID PARSER
# -----------------------------
def parse_ibeacon_uuid(hex_data):
    """
    Extract UUID from iBeacon manufacturer payload.
    """
    try:
        # iBeacon structure:
        # 02 15 + UUID (16 bytes)
        if "0215" in hex_data:
            uuid_hex = hex_data.split("0215")[1][0:32]
            return (
                uuid_hex[0:8] + "-" +
                uuid_hex[8:12] + "-" +
                uuid_hex[12:16] + "-" +
                uuid_hex[16:20] + "-" +
                uuid_hex[20:]
            ).upper()
    except:
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
    elif -80 < rssi < -60:
        return {"status": "Near", "class": "warning", "desc": "1.5m - 5m"}
    else:
        return {"status": "Far", "class": "danger", "desc": "> 5m"}


# -----------------------------
# BLE SCANNER LOOP
# -----------------------------
# -----------------------------
# BLE SCANNER LOOP
# -----------------------------
async def ble_scanner_loop():

    # 1. ADD NEARBY_DEVICES HERE SO FLASK CAN READ IT
    global LATEST_DATA, NEARBY_DEVICES 

    while True:

        try:
            devices = await BleakScanner.discover(timeout=3.0)

            NEARBY_DEVICES = []
            current_scan = {}

            # initialize all assets as offline
            for uuid, info in TARGET_ASSETS.items():
                current_scan[uuid] = {
                    "name": info["name"],
                    "dept": info["dept"],
                    "rssi": "N/A",
                    "status": "Offline",
                    "class": "secondary",
                    "desc": "Not Detected",
                    "last_seen": "-"
                }

            for device in devices:

                rssi = get_rssi(device)

                # 2. ADD YOUR NEW CODE RIGHT HERE
                name = device.name or "Unknown Device"
                NEARBY_DEVICES.append({
                    "name": name,
                    "address": device.address,
                    "rssi": f"{rssi} dBm" if rssi else "N/A"
                })
                # ----------------------------------------

                # manufacturer data access (iBeacon)
                md = getattr(device, "metadata", {}).get("manufacturer_data", {})

                for company_id, data in md.items():

                    hex_data = data.hex().lower()
                    parsed_uuid = parse_ibeacon_uuid(hex_data)

                    if parsed_uuid:

                        parsed_uuid = parsed_uuid.upper()

                        if parsed_uuid in TARGET_ASSETS:

                            prox = estimate_proximity(rssi)

                            current_scan[parsed_uuid].update({
                                "rssi": f"{rssi} dBm" if rssi else "N/A",
                                "status": prox["status"],
                                "class": prox["class"],
                                "desc": prox["desc"],
                                "last_seen": time.strftime("%H:%M:%S")
                            })

                            print(f"Detected: {TARGET_ASSETS[parsed_uuid]['name']}")
                            print(f"UUID: {parsed_uuid}")
                            print(f"RSSI: {rssi}")
                            print("---------------------------")

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