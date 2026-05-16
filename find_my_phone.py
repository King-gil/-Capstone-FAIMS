import asyncio
from bleak import BleakScanner

async def scan_close_devices():
    print("==================================================")
    print(" Hold your phone directly touching your laptop! ")
    print("==================================================")
    
    # Run a short 5-second scan
    devices = await BleakScanner.discover(timeout=5.0)
    
    print("\n--- Found these very close devices: ---")
    for d in devices:
        # RSSI values closer to 0 (like -30 to -55) mean the device is physically touching or right next to the antenna
        if d.rssi >= -55: 
            print(f"📱 Name: {d.name or 'Unknown Device'}")
            print(f"   UUID: {d.address}")
            print(f"   Signal Power: {d.rssi} dBm")
            print("-" * 40)

asyncio.run(scan_close_devices())