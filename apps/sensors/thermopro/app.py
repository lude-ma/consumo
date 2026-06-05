#!/usr/bin/python3
"""An application reading ThermoPro Bluetooth thermo- and hygrometers."""

import asyncio
import time


from bleak import BleakScanner


DEBUG = False

SENSORS_MAC_TO_NAME = {
    "438E": "Keller Garage",
    "1016": "Keller Haus",
    "C812": "Flur Erdgeschoss",
    "A53C": "Wohnzimmer",
    "0506": "Zimmer Lea",
    "D3C4": "Büro",
    "ECE8": "Schlafzimmer",
    "EDCD": "Kinderzimmer",
    "1BB1": "Bad",
    "5443": "Außen"
}
"""Mapping from Sensor MAC address to human-readable name."""


def decode_tp357(manufacturer_data):
    """Decodes raw data of a ThermoPro TP357 sensor.
    
    Convert bleak manufacturer_data to raw data, then extract TP357 data.
    See https://github.com/hbldh/bleak/issues/1819.
    """
    for identifier, data in manufacturer_data.items():
        if DEBUG:
            key = hex(identifier)
            byte_array = hex(int.from_bytes(data, byteorder="little", signed=False))
            print(f"[DEBUG] Raw manufacturer data: {key} {byte_array}.")

        if len(data) >= 4:
            # Temperature is in second to third byte of the manufacturer data,
            # i.e., in low byte of identifier and first byte of data.
            # Divide by 10 to get degree Celsius.
            temp_raw_low = (identifier>>8) & 0xFF
            temp_raw_high = data[0]
            temp_raw = temp_raw_low + temp_raw_high*256
            temperature = temp_raw / 10.0

            # Humidity is in third byte of manufacturer data,
            # i.e., in second byte of data.
            humidity = data[1]

            # Battery flag is in first and second bit of fifth byte of
            # manufacturer data, i.e., in first and second bit of third byte of
            # data.
            bat_raw = data[2] & 0x03
            match bat_raw:
                case 0:
                    battery = 0  # Empty battery.
                case 1:
                    battery = 50  # 50 % battery.
                case 2:
                    battery = 100  # Full battery.
                case _:
                    print(f"[ERROR] bat_raw={bat_raw} not supported")
                    battery = None
            return temperature, humidity, battery
    return None, None, None


async def main():
    """Function scanning for all available ThermoPro TP357 sensors."""
    read_sensors = []

    def callback(device, advertising_data):
        """Parse the advertisement.
        
        This will only return data if it's a recognized ThermoPro device.
        """
        if device.name and "TP357" in device.name:
            temp, hum, bat = decode_tp357(advertising_data.manufacturer_data)
            if temp is not None:
                mac = device.name[8:12]
                if mac in read_sensors:
                    return
                try:
                    device_name = SENSORS_MAC_TO_NAME[mac]
                except KeyError:
                    device_name = device.name

                # Write as line protocol.
                lp_name = device_name.replace(' ', r'\ ')
                print(f"tp357,mac={mac},name={lp_name} temp={temp},hum={hum}i,bat={bat}i {time.time_ns()}")
                if DEBUG:
                    print(f"Sensor: {device_name} ({device.address})")
                    print(f"Temperature: {temp}C")
                    print(f"Humidity: {hum}%")
                    print(f"Battery: {bat}%")
                    print("-" * 20)

                read_sensors.append(mac)

    # Start the scanner
    scanner = BleakScanner(callback)
    await scanner.start()

    print("#Scanning for ThermoPro devices... (Ctrl+C to stop)")
    try:
        while len(read_sensors) < len(SENSORS_MAC_TO_NAME):
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await scanner.stop()


if __name__ == "__main__":
    asyncio.run(main())
