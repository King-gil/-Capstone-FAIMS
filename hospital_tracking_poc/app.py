import asyncio
import threading
import time
from flask import Flask, render_template, jsonify
from bleak import BleakScanner

app = Flask(__name__)

# Configuration: Replace with your actual beacon/phone MAC addresses
TARGET_ASSETS = {
    "C216FE14-8047-4978-92C3-68919B540D4F".replace("-", "").lower(): {"name": "Asset 1 (Ventilator)", "dept": "ICU WARD A"},
    "66:77:88:99:AA:BB": {"name": "Asset 2 (Infusion Pump)", "dept": "EMERGENCY ROOM"}
}

# Shared memory storage for the latest scanned values
LATEST_DATA = {}

def estimate_proximity(rssi):
    if rssi >= -60:
        return {"status": "Immediate", "class": "success", "desc": "< 1.5m (Very Close)"}
    elif -80 < rssi < -60:
        return {"status": "Near", "class": "warning", "desc": "1.5m - 5m (Same Room)"}
    else:
        return {"status": "Far", "class": "danger", "desc": "> 5m (Edge / Displaced)"}

async def ble_scanner_loop():

    global LATEST_DATA

    while True:

        try:

            # IMPORTANT
            devices = await BleakScanner.discover(
                timeout=3.0,
                return_adv=True
            )

            current_scan = {}

            # Initialize all assets as offline
            for uuid, info in TARGET_ASSETS.items():

                current_scan[uuid] = {
                    "name": info["name"],
                    "dept": info["dept"],
                    "rssi": "N/A",
                    "status": "Offline",
                    "class": "secondary",
                    "desc": "Not Detected / Missing",
                    "last_seen": "-"
                }

            # Process detected BLE advertisements
            for address, (device, adv) in devices.items():

                manufacturer_data = adv.manufacturer_data

                # Apple manufacturer ID for iBeacon
                if 76 in manufacturer_data:

                    raw_bytes = manufacturer_data[76]

                    hex_data = raw_bytes.hex().lower()

                    # Remove dashes from UUID registry
                    for uuid, info in TARGET_ASSETS.items():

                        formatted_uuid = uuid.replace("-", "").lower()

                        if formatted_uuid in hex_data:

                            prox = estimate_proximity(device.rssi)

                            current_scan[uuid].update({
                                "rssi": f"{device.rssi} dBm",
                                "status": prox["status"],
                                "class": prox["class"],
                                "desc": prox["desc"],
                                "last_seen": time.strftime("%H:%M:%S")
                            })

                            print(f"Detected: {info['name']}")
                            print(f"UUID: {uuid}")
                            print(f"RSSI: {device.rssi}")
                            print("--------------------------------")

            LATEST_DATA = current_scan

        except Exception as e:

            print(f"Scanner Error: {e}")

        await asyncio.sleep(1)
        
def start_ble_loop():
    """Helper to run the async BLE loop inside a dedicated background thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ble_scanner_loop())

# --- FLASK WEB ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/assets')
def get_assets():
    """API endpoint that the frontend calls to get real-time tracking data."""
    return jsonify(list(LATEST_DATA.values()))

if __name__ == "__main__":
    # Start the BLE scanner thread before spinning up the Flask app
    scanner_thread = threading.Thread(target=start_ble_loop, daemon=True)
    scanner_thread.start()
    
    # Launch the web application
    app.run(debug=True, port=5000)