import asyncio
import threading
import time
from flask import Flask, render_template, jsonify
from bleak import BleakScanner

app = Flask(__name__)

# Configuration: Replace with your actual beacon/phone MAC addresses
TARGET_ASSETS = {
    "00:11:22:33:44:55": {"name": "Asset 1 (Ventilator)", "dept": "ICU WARD A"},
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
    """Continuous async loop that scans for BLE signals."""
    global LATEST_DATA
    while True:
        try:
            devices = await BleakScanner.discover(timeout=3.0)
            
            # Initialize/Reset active registry state for this cycle
            current_scan = {}
            for mac, info in TARGET_ASSETS.items():
                current_scan[mac] = {
                    "name": info["name"],
                    "dept": info["dept"],
                    "rssi": "N/A",
                    "status": "Offline",
                    "class": "secondary",
                    "desc": "Not Detected / Missing",
                    "last_seen": time.strftime("%H:%M:%S")
                }
                
            # Populate data for found assets
            for device in devices:
                if device.address in TARGET_ASSETS:
                    prox = estimate_proximity(device.rssi)
                    current_scan[device.address].update({
                        "rssi": f"{device.rssi} dBm",
                        "status": prox["status"],
                        "class": prox["class"],
                        "desc": prox["desc"],
                        "last_seen": time.strftime("%H:%M:%S")
                    })
                    
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