import asyncio
from bleak import BleakScanner

TARGET_UUID = "C216FE14-8047-4978-92C3-68919B540D4F".replace("-", "").lower()

async def scan():

    print("Scanning for iBeacon...\n")

    devices = await BleakScanner.discover(return_adv=True)

    found = False

    for address, (device, adv) in devices.items():

        manufacturer_data = adv.manufacturer_data

        # Apple company ID = 76
        if 76 in manufacturer_data:

            raw_bytes = manufacturer_data[76]

            hex_data = raw_bytes.hex()

            print(f"Device: {device.name}")
            print(f"Address: {device.address}")
            print(f"RSSI: {device.rssi}")
            print(f"Raw Beacon Data: {hex_data}\n")

            if TARGET_UUID in hex_data:

                print("================================")
                print("TARGET ASSET DETECTED")
                print("================================")
                print(f"UUID: {TARGET_UUID}")
                print(f"Device: {device.name}")
                print(f"RSSI: {device.rssi}")
                print("================================\n")

                found = True

    if not found:
        print("Target beacon not detected.")

asyncio.run(scan())