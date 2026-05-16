import asyncio
from bleak import BleakScanner

# Configuration: Replace these placeholder MAC/Bluetooth addresses 
# with the actual addresses of your beacons or simulator apps.
TARGET_ASSETS = {
    "00:11:22:33:44:55": "Asset 1 (Ventilator)",
    "66:77:88:99:AA:BB": "Asset 2 (Infusion Pump)"
}

def estimate_proximity(rssi):
    """Provides a rough human-readable distance category based on RSSI."""
    if rssi >= -60:
        return "Immediate (Very Close, < 1.5m)"
    elif -80 < rssi < -60:
        return "Near (Same Room, 1.5m - 5m)"
    else:
        return "Far (Edge of Room / Displaced, > 5m)"

async def run_asset_scanner():
    print("=============================================")
    print("   Initializing BLE Asset Tracking PoC...   ")
    print("   Press Ctrl+C to terminate the scanner.    ")
    print("=============================================\n")
    
    while True:
        # BleakScanner.discover scans for the specified timeout duration (in seconds)
        print("Scanning environment...")
        devices = await BleakScanner.discover(timeout=4.0)
        
        print(f"\n--- Scan Complete: Found {len(devices)} total BLE signals ---")
        
        target_detected = False
        
        for device in devices:
            # Check if the detected device matches our target asset registry
            if device.address in TARGET_ASSETS:
                asset_name = TARGET_ASSETS[device.address]
                rssi = device.rssi  # Signal strength indicator (e.g., -65)
                proximity = estimate_proximity(rssi)
                
                print(f"📍 Detected: {asset_name}")
                print(f"   Hardware ID: {device.address}")
                print(f"   Signal Power: {rssi} dBm")
                print(f"   Proximity:    {proximity}")
                print("-" * 40)
                print(device.address, device.name)
                target_detected = True
        
        if not target_detected:
            print("No registered assets detected in this area.")
            print("-" * 40)
            
        # Brief pause between scanning cycles to optimize network and hardware load
        await asyncio.sleep(2)

if __name__ == "__main__":
    try:
        asyncio.run(run_asset_scanner())
    except KeyboardInterrupt:
        print("\n[System Info] Asset scanning suspended by user.")