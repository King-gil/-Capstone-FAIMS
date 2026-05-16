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