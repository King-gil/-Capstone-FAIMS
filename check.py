import asyncio
from bleak import BleakScanner

async def main():
    print("Scanning for 5 seconds...")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        # Prints everything it sees so you can find your phone's current ID
        print(f"Name: {d.name} | UUID: {d.address} | RSSI: {d.rssi}")

asyncio.run(main())