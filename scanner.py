import asyncio
from bleak import BleakScanner

# Registered BLE Assets
TARGET_ASSETS = {
    "C216FE14-8047-4978-92C3-68919B540D4F": {
        "name": "Ventilator",
        "dept": "ICU WARD A"
    },
    "66:77:88:99:AA:BB": {
        "name": "Infusion Pump",
        "dept": "ER"
    },
}

def estimate_proximity(rssi):
    """Estimate proximity based on RSSI signal strength."""
    
    if rssi >= -60:
        return "Immediate (< 1.5m)"
    
    elif -80 < rssi < -60:
        return "Near (1.5m - 5m)"
    
    return "Far (> 5m)"


async def run_asset_scanner():

    print("=============================================")
    print("      BLE Asset Tracking System (PoC)")
    print("=============================================")
    print("Press Ctrl+C to stop scanning.\n")

    while True:

        print("Scanning environment...\n")

        # Scan BLE devices for 4 seconds
        devices = await BleakScanner.discover(timeout=4.0)

        print(f"Detected {len(devices)} BLE devices\n")

        target_detected = False

        for device in devices:

            # Match scanned device against registered assets
            if device.address in TARGET_ASSETS:

                asset = TARGET_ASSETS[device.address]

                rssi = device.rssi
                proximity = estimate_proximity(rssi)

                print("=================================")
                print(f"Asset Name : {asset['name']}")
                print(f"Department : {asset['dept']}")
                print(f"Address    : {device.address}")
                print(f"Device Name: {device.name}")
                print(f"RSSI       : {rssi} dBm")
                print(f"Proximity  : {proximity}")
                print("=================================\n")

                target_detected = True

        if not target_detected:
            print("No registered assets detected.\n")

        print("-" * 50)

        # Delay before next scan cycle
        await asyncio.sleep(2)


if __name__ == "__main__":

    try:
        asyncio.run(run_asset_scanner())

    except KeyboardInterrupt:
        print("\n[System] Scanner terminated by user.")