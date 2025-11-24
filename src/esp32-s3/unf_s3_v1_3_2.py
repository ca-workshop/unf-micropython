"""
BLEScale_v1
===========

Project   : Unforgotten – ESP32S3 BLE Scale + GPS/Fused bridge
File      : BLEScale.py
Version   : 1.1.0
Author    : (your name)
Board     : ESP32-S3
Created   : 2025-11-09

Overview
--------
- BLE peripheral exposing 1 service with 3 logical channels:
    * Weight (TX/RX)
    * Fused location (TX/RX)
    * GPS location (TX/RX)
- Integrates HX711 load cell amplifier for weight measurement.
- Receives Fused + GPS JSON lines from Android over BLE.
- Sends JSON responses (weight/fused/gps) back to Android.

Power optimisation
------------------
- Uses PowerManager to detect "no load" state on the scale.
- Uses LowPowerScale to:
    * Power-up HX711 only when needed.
    * Power-down HX711 when idle.
    * Feed PowerManager with readings in **grams**.
- Main loop adapts sleep time:
    * Active   : 0.5 seconds
    * Idle     : 2.0 seconds
    * Deep idle: 5.0 seconds
- JSON responses include an "idle" flag so Android
  (UnforgottenServiceHelper) can switch to a low-power profile.

Changelog
---------
1.1.0  (2025-11-10)
    - Integrated LowPowerScale (HX711 + PowerManager wrapper).
    - get_weight() now delegates to LowPowerScale.
    - PowerManager now always receives readings in grams.
    - BLE JSON still sends weight in kilograms for the phone.

1.0.0  (2025-11-09)
    - Initial refactor with PowerManager integration.
    - Added power-optimized get_weight() with HX711 power_up/power_down.
    - Added dynamic loop timing (active / idle / deep idle).
    - Added "idle" field to BLE TX JSON payload.
"""

from time import sleep, ticks_ms, ticks_diff
from machine import Pin
from micropython import const
import bluetooth
import struct
import ujson
from bluetooth import BLE

# from v1.hx711 import HX711
from lib.sensors.hx711_driver import HX711
from payload import advertising_payload
from lib.common_const import *
import s3_const as CFG

from gatt_defs import WEIGHT_SERVICE_UUID, WEIGHT_SERVICE, GATT_SCHEMA_VERSION
from power_manager import PowerManager
from low_power_scale import LowPowerScale

from lib.s3_neopixel_led_manager_v1_5_1 import S3RGBManager

# IRQ constants for handling BLE events (MicroPython BLE)
IRQ_CENTRAL_CONNECT = const(1)
IRQ_CENTRAL_DISCONNECT = const(2)
IRQ_GATTS_WRITE = const(3)
IRQ_GATTS_READ_REQUEST = const(4)

# UUIDs for the weight, fused, and GPS services and characteristics
# These must match what your Android app expects.
WEIGHT_SERVICE_UUID = bluetooth.UUID("00001234-0000-1000-8000-00805f9b34fb")

WEIGHT_CHAR_TX = (
    bluetooth.UUID("00002345-0000-1000-8000-00805f9b34fb"),
    FLAG_READ | FLAG_NOTIFY,
)
WEIGHT_CHAR_RX = (
    bluetooth.UUID("00003345-0000-1000-8000-00805f9b34fb"),
    FLAG_WRITE | FLAG_WRITE_NO_RESPONSE,
)

FUSED_CHAR_TX = (
    bluetooth.UUID("00004345-0000-1000-8000-00805f9b34fb"),
    FLAG_READ | FLAG_NOTIFY,
)
FUSED_CHAR_RX = (
    bluetooth.UUID("00005345-0000-1000-8000-00805f9b34fb"),
    FLAG_WRITE | FLAG_WRITE_NO_RESPONSE,
)

GPS_CHAR_TX = (
    bluetooth.UUID("00006345-0000-1000-8000-00805f9b34fb"),
    FLAG_READ | FLAG_NOTIFY,
)
GPS_CHAR_RX = (
    bluetooth.UUID("00007345-0000-1000-8000-00805f9b34fb"),
    FLAG_WRITE | FLAG_WRITE_NO_RESPONSE,
)

# Single service with 6 characteristics:
# - weight tx/rx
# - fused tx/rx
# - gps   tx/rx
WEIGHT_SERVICE = (
    WEIGHT_SERVICE_UUID,
    (
        WEIGHT_CHAR_TX,
        WEIGHT_CHAR_RX,
        FUSED_CHAR_TX,
        FUSED_CHAR_RX,
        GPS_CHAR_TX,
        GPS_CHAR_RX,
    ),
)


class BLEScale:
    """
    BLEScale
    ========

    Responsibilities:
    - Initialize and manage BLE (services, characteristics, IRQ).
    - Read weight from HX711 (via LowPowerScale).
    - Receive fused/GPS JSON from Android over BLE.
    - Send JSON responses (weight/fused/gps) back to Android.
    - Use PowerManager to:
        * Detect "no load" on HX711.
        * Reduce measurement frequency (active / idle / deep idle).
        * Power-down HX711 when idle to save battery.
    """

    def __init__(self, name="ESP32S3"):
        # ─────────────────────────────────────────────────────────────
        # BLE state and configuration
        # ─────────────────────────────────────────────────────────────
        self.ble = BLE()
        self.ble.active(True)
        self.ble.config(mtu=100)  # Larger MTU for JSON payloads
        self.ble.irq(self._irq)   # Register interrupt handler for BLE events

        self._connections = set()  # Holds connection handles
        self.connected = False     # True when at least one central is connected
        self.timer = 0             # Used for LED blink timing when not connected

        # Last measured weight **in kilograms** sent to the phone
        self.weight_tx = 0.0

        # Partial received data buffer for JSON lines
        self.rx_buffer = b""

        # ─────────────────────────────────────────────────────────────
        # Power manager + HX711 + LowPowerScale
        # ─────────────────────────────────────────────────────────────
        # PowerManager works in **grams**.
        #         self.pm = PowerManager()
        # 
        #         # HX711 load cell amplifier.
        #         # You should calibrate SCALE so that hx.get_units() returns grams.
        #         self.hx = HX711(DT_PIN, SCK_PIN)
        #         self.hx.set_scale(2280)   # Calibration factor (tune so get_units() ≈ grams)
        #         self.hx.tare()            # Zero the scale at startup
        # 
        #         # Wrap HX711 + PowerManager into a single helper.
        #         self.scale = LowPowerScale(self.hx, self.pm)

        # Last raw weight in grams (for debug if needed)
        self.last_weight_g = 0.0

        # ─────────────────────────────────────────────────────────────
        # RX data buffers for fused and GPS (received from Android)
        # ─────────────────────────────────────────────────────────────
        self.fused_rx_data = {
            "time": 0,
            "latitude": 0.0,
            "longitude": 0.0,
            "speed": 0.0,
            "altitude": 0.0,
            "accuracy": 0.0,
        }
        self.gps_rx_data = {
            "time": 0,
            "latitude": 0.0,
            "longitude": 0.0,
            "speed": 0.0,
            "altitude": 0.0,
            "accuracy": 0.0,
        }
        # tx_data is built per-request in send_tx_as_json_response()
        self.tx_data = {}

        # ─────────────────────────────────────────────────────────────
        # Register BLE services + start advertising
        # ─────────────────────────────────────────────────────────────
        try:
            # Register our single service with 6 characteristics
            (
                (
                    self.weight_tx_handle,
                    self.weight_rx_handle,
                    self.fused_tx_handle,
                    self.fused_rx_handle,
                    self.gps_tx_handle,
                    self.gps_rx_handle,
                ),
            ) = self.ble.gatts_register_services((WEIGHT_SERVICE,))
            print("BLEScale - BLE services registered")

            # Advertising payload: device name + service UUID
            self._payload = advertising_payload(
                name=name, services=[WEIGHT_SERVICE_UUID]
            )
            self._advertise()
        except Exception as e:
            print("BLE setup error:", e)
            #self.blink_led(self.led_red, 3)
            self.leds.on_error()   # LED goes solid red and stays that way

        
        self._init_sensors()
        self._init_leds()

    # ─────────────────────────────────────────────────────────────────
    # BLE IRQ handler
    # ─────────────────────────────────────────────────────────────────
    def _irq(self, event, data):
        """
        Handle BLE events:
        - Connect / disconnect
        - Writes from central (Android)
        - Read requests from central
        """
        if event == IRQ_CENTRAL_CONNECT:
            # A new central (e.g., Android phone) has connected.
            conn_handle, _, _ = data
            self._connections.add(conn_handle)
            self.connected = True
            self.leds.on_connect()  # -> BLUE blink (via update)
            print("New connection:", conn_handle)

        elif event == IRQ_CENTRAL_DISCONNECT:
            # A central disconnected.
            conn_handle, _, _ = data
            self._connections.discard(conn_handle)
            self.connected = False
            self.leds.on_disconnect()  # -> BLUE blink (via update)
            # Go back to advertising mode for new connections.
            self._advertise()
            print("Disconnected:", conn_handle)

            # Clear last received fused/GPS and TX buffers on disconnect.
            self.clear()

        elif event == IRQ_GATTS_WRITE:
            # Data written by central to one of the RX characteristics.
            conn_handle, char_handle = data
            raw_data = self.ble.gatts_read(char_handle)
            # Parse JSON line(s) and update fused_rx_data / gps_rx_data.
            self.save_received_data(char_handle, raw_data)
            self.leds.on_transfer()

        elif event == IRQ_GATTS_READ_REQUEST:
            # Central reads one of our TX characteristics.
            conn_handle, char_handle = data
            #self.toggle_led(self.led_green)
            self.send_tx_as_json_response(char_handle)
            self.leds.on_transfer()

    def _advertise(self, interval_us=500000):
        """
        Start BLE advertising so the device can be discovered.
        Called on startup and on disconnect.
        """
        try:
            # First stop any previous advertising to avoid conflicts.
            self.ble.gap_advertise(None)
            sleep(0.05)
            # Start advertising with our payload.
            self.ble.gap_advertise(interval_us, adv_data=self._payload)
            print("BLEScale - Advertising started")
        except OSError as e:
            print("Failed to advertise:", e)

    def _init_sensors(self):
        self.hx = HX711(CFG.DT_PIN, CFG.SCK_PIN)
        self.hx.set_scale(2280)
        self.offset = 0
        self.hx.tare()

        # Power manager + LowPowerScale (grams internally)
        self.pm = PowerManager()
        self.scale = LowPowerScale(self.hx, self.pm)

    def _init_leds(self):
        # For S3 with onboard NeoPixel
        self.leds = S3RGBManager(
            CFG.NEOPIXEL_PIN,
            np_count=CFG.NEOPIXEL_COUNT,
            np_index=CFG.NEOPIXEL_INDEX,
            np_brightness=CFG.NEOPIXEL_BRIGHTNESS,
        )
    # ─────────────────────────────────────────────────────────────────
    # RX: handling fused/GPS JSON from Android
    # ─────────────────────────────────────────────────────────────────
    def save_received_data_1(self, attr_handle, raw_data):
        """
        Process and save received data (GPS and fused data).
        Data is expected as one or more JSON lines separated by '\n'.

        - Accumulates raw bytes into rx_buffer.
        - Splits by '\n'.
        - For each full JSON line: decode + parse + update fused_rx_data / gps_rx_data.
        """
        self.rx_buffer += raw_data

        while b"\n" in self.rx_buffer:
            try:
                # Extract one JSON line (bytes) and leave the rest in rx_buffer.
                json_bytes, self.rx_buffer = self.rx_buffer.split(b"\n", 1)
                json_str = json_bytes.decode()

                # Parse into Python dict.
                data = ujson.loads(json_str)

                # Fused location data update.
                if attr_handle == self.fused_rx_handle:
                    #print("fused - Decoded data:", data, "\n")

                    if "latitude" in data:
                        self.fused_rx_data["latitude"] = str(data["latitude"])
                    if "longitude" in data:
                        self.fused_rx_data["longitude"] = str(data["longitude"])
                    if "altitude" in data:
                        self.fused_rx_data["altitude"] = str(data["altitude"])
                    if "speed" in data:
                        self.fused_rx_data["speed"] = str(data["speed"])
                    if "time" in data:
                        self.fused_rx_data["time"] = str(data["time"])
                    if "accuracy" in data:
                        self.fused_rx_data["accuracy"] = str(data["accuracy"])

                # GPS location data update.
                if attr_handle == self.gps_rx_handle:
                    #print("gps - Decoded data:", data, "\n")

                    if "latitude" in data:
                        self.gps_rx_data["latitude"] = str(data["latitude"])
                    if "longitude" in data:
                        self.gps_rx_data["longitude"] = str(data["longitude"])
                    if "altitude" in data:
                        self.gps_rx_data["altitude"] = str(data["altitude"])
                    if "speed" in data:
                        self.gps_rx_data["speed"] = str(data["speed"])
                    if "time" in data:
                        self.gps_rx_data["time"] = str(data["time"])
                    if "accuracy" in data:
                        self.gps_rx_data["accuracy"] = str(data["accuracy"])

            except Exception as e:
                print("Failed to parse data:", e)

    def save_received_data_2(self, attr_handle, raw_data):
        """
        Alternative debug version of the parser (kept from original).
        Not used in the main flow, but left here for debugging if needed.
        """
        self.rx_buffer += raw_data

        while b"\n" in self.rx_buffer:
            try:
                json_bytes, self.rx_buffer = self.rx_buffer.split(b"\n", 1)
                print("Raw JSON bytes:", json_bytes)
                data = ujson.loads(json_bytes.decode())
                json_str = json_bytes.decode()
                print("json str data:", json_str)

                if "latitude" in data:
                    print("Latitude (after decoding):", data["latitude"])
                if "longitude" in data:
                    print("Longitude (after decoding):", data["longitude"])

                if "latitude" in data:
                    data["latitude"] = round(data["latitude"], 7)
                if "longitude" in data:
                    data["longitude"] = round(data["longitude"], 7)

                if attr_handle == self.fused_rx_handle:
                    #print("fused(fusedRx):", json_str, "\n")
                    self.fused_rx_data.update(json_str)

                elif attr_handle == self.gps_rx_handle:
                    #print("gps(gpsRx):", json_str, "\n")
                    self.gps_rx_data.update(json_str)

            except Exception as e:
                print("Failed to parse data:", e)

    def save_received_data_3(self, attr_handle, raw_data):
        """
        Robust JSON-line parser for fused/gps RX.

        Differences vs older version:
        - Keeps a single buffer (self.rx_buffer) like before.
        - For each line, we:
            * decode with errors='ignore'
            * strip BOM / NUL / CR
            * crop to the first '{' and last '}'
            * only then call ujson.loads(...)
        - Any garbage outside the JSON object is ignored.
        """

        # 1) Accumulate raw bytes
        self.rx_buffer += raw_data

        # 2) Process complete lines separated by '\n'
        while b"\n" in self.rx_buffer:
            try:
                json_bytes, self.rx_buffer = self.rx_buffer.split(b"\n", 1)
                json_bytes = json_bytes.strip()
                if not json_bytes:
                    continue

                # For debugging – see exactly what we got:
                print("Raw JSON bytes:", json_bytes)

                # 3) Decode, but ignore invalid UTF-8 sequences
                try:
                    json_str = json_bytes.decode("utf-8", "ignore")
                except Exception as e:
                    print("RX decode error:", e)
                    continue

                # 4) Remove common junk: BOM, NULs, CR
                json_str = json_str.replace("\ufeff", "").replace("\x00", "").replace("\r", "")
                json_str = json_str.strip()

                # 5) Crop to the first '{' and last '}' – like you do on Android
                lb = json_str.find("{")
                rb = json_str.rfind("}")
                if lb == -1 or rb == -1 or rb <= lb:
                    print("RX fragment ignored (no full JSON object):", repr(json_str))
                    continue

                json_str = json_str[lb:rb + 1]

                print("Clean JSON string:", json_str)

                # 6) Finally, parse JSON
                try:
                    data = ujson.loads(json_str)
                except Exception as e:
                    print("Failed to parse data:", e, "raw JSON:", json_str)
                    continue

                # 7) Optional: debug some key fields
                if "latitude" in data:
                    print("Latitude (after decoding):", data["latitude"])
                if "longitude" in data:
                    print("Longitude (after decoding):", data["longitude"])

                # 8) Optional rounding (as before)
                if "latitude" in data:
                    data["latitude"] = round(float(data["latitude"]), 7)
                if "longitude" in data:
                    data["longitude"] = round(float(data["longitude"]), 7)

                # 9) Route to correct RX dict
                if attr_handle == self.fused_rx_handle:
                    print("fused(fusedRx):", json_str, "\n")
                    self.fused_rx_data.update(data)

                elif attr_handle == self.gps_rx_handle:
                    print("gps(gpsRx):", json_str, "\n")
                    self.gps_rx_data.update(data)

                else:
                    print("save_received_data: unknown handle", attr_handle, "data:", data)

            except Exception as e:
                print("save_received_data (debug) unexpected error:", e)


    def save_received_data(self, attr_handle, raw_data):
        """
        Tolerant parser for fused/gps JSON-ish data.

        - Uses a single buffer (self.rx_buffer) for the stream.
        - For each newline-terminated chunk:
            * decode UTF-8 with errors ignored
            * strip BOM / NUL / CR / spaces
            * crop to the first '{' and last '}'
            * manually extract numeric fields from the string
        - Does NOT use ujson.loads(), so it survives partially broken JSON
          that the ESP32-S3 BLE stack likes to sprinkle around.
        """

        # 1) Accumulate raw bytes
        self.rx_buffer += raw_data

        # 2) Process every complete line
        while b"\n" in self.rx_buffer:
            try:
                json_bytes, self.rx_buffer = self.rx_buffer.split(b"\n", 1)
                json_bytes = json_bytes.strip()
                if not json_bytes:
                    continue

                # Debug raw bytes
                print("Raw JSON bytes:", json_bytes)

                # 3) Decode (ignore bad sequences)
                try:
                    s = json_bytes.decode("utf-8", "ignore")
                except Exception as e:
                    print("RX decode error:", e)
                    continue

                # 4) Strip common garbage
                s = s.replace("\ufeff", "").replace("\x00", "").replace("\r", "")
                s = s.strip()
                if not s:
                    continue

                # 5) Crop to first '{' and last '}'
                lb = s.find("{")
                rb = s.rfind("}")
                if lb == -1 or rb == -1 or rb <= lb:
                    print("RX fragment ignored (no full JSON object):", repr(s))
                    continue

                s = s[lb:rb + 1]
                print("Clean JSON string:", s)

                # 6) Helper to extract a numeric value from "json-ish" text
                def _extract_number(text, key, default=None):
                    pattern = '"' + key + '"'
                    i = text.find(pattern)
                    if i == -1:
                        return default
                    # find colon after the key
                    i = text.find(":", i)
                    if i == -1:
                        return default
                    i += 1
                    # skip spaces
                    while i < len(text) and text[i] in " \t":
                        i += 1
                    start = i
                    while i < len(text) and text[i] in "-+0123456789.eE":
                        i += 1
                    if start == i:
                        return default
                    try:
                        return float(text[start:i])
                    except Exception:
                        return default

                # 7) Extract fields
                lat  = _extract_number(s, "latitude")
                lon  = _extract_number(s, "longitude")
                alt  = _extract_number(s, "altitude")
                spd  = _extract_number(s, "speed")
                t    = _extract_number(s, "time")
                acc  = _extract_number(s, "accuracy")

                # Optional rounding for lat/lon
                if lat is not None:
                    lat = round(float(lat), 7)
                if lon is not None:
                    lon = round(float(lon), 7)

                # 8) Route to correct RX dict and update only existing values
                target = None
                if attr_handle == self.fused_rx_handle:
                    target = self.fused_rx_data
                    print("Updating fused_rx_data from:", s)
                elif attr_handle == self.gps_rx_handle:
                    target = self.gps_rx_data
                    print("Updating gps_rx_data from:", s)
                else:
                    print("save_received_data: unknown handle", attr_handle, "line:", s)
                    target = None

                if target is not None:
                    if lat is not None:
                        target["latitude"] = lat
                    if lon is not None:
                        target["longitude"] = lon
                    if alt is not None:
                        target["altitude"] = alt
                    if spd is not None:
                        target["speed"] = spd
                    if t is not None:
                        # keep as int-ish timestamp if you like
                        try:
                            target["time"] = int(t)
                        except Exception:
                            target["time"] = t
                    if acc is not None:
                        target["accuracy"] = acc

            except Exception as e:
                # Very defensive: never let a bad line crash the loop
                print("save_received_data tolerant parser unexpected error:", e)

    # ─────────────────────────────────────────────────────────────────
    # TX: JSON response for weight / fused / gps
    # ─────────────────────────────────────────────────────────────────
    def send_tx_as_json_response(self, attr_handle):
        """
        Build and send JSON response over a TX characteristic.

        Format (example):
        {
          "from": "weight" | "fused" | "gps",
          "weight": <kg>,
          "time": ...,
          "latitude": ...,
          "longitude": ...,
          "speed": ...,
          "altitude": ...,
          "accuracy": ...,
          "idle": true|false    # <— allows Android to switch power profile
        }
        """
        # Base payload: always include weight and idle flag.
        self.tx_data = {
            "from": "",
            "weight": self.weight_tx,  # kilograms for the app
            "time": 0,
            "latitude": 0.0,
            "longitude": 0.0,
            "speed": 0.0,
            "altitude": 0.0,
            "accuracy": 0.0,
            "idle": self.pm.idle,
        }

        # Decide which data block to fill based on the requested handle.
        if attr_handle == self.weight_tx_handle:
            self.tx_data["from"] = "weight"

        elif attr_handle == self.fused_tx_handle:
            self.tx_data.update(self.fused_rx_data)
            self.tx_data["from"] = "fused"
            print("sending fused_rx_data :", self.tx_data, "\n")

        elif attr_handle == self.gps_tx_handle:
            self.tx_data.update(self.gps_rx_data)
            self.tx_data["from"] = "gps"
            print("sending gps_rx_data :", self.tx_data, "\n")

        else:
            print("Unknown TX handle:", attr_handle)
            return

        try:
            self.ble.gatts_write(attr_handle, ujson.dumps(self.tx_data).encode())
        except Exception as e:
            print("Failed to send response:", e)

    # ─────────────────────────────────────────────────────────────────
    # LED helpers
    # ─────────────────────────────────────────────────────────────────
    # ─────────────────────────────────────────────────────────────────
    # LED helpers
    # ─────────────────────────────────────────────────────────────────
    def toggle_led(self):
        """
        For backward compatibility: just advance LED animation.
        Effect:
          - If not connected : blue blink/toggle via S3RGBManager
          - If connected     : solid blue or green blink (on transfer)
        """
        #self.leds.update()
        pass

    def off_all(self):
        """Turn off all LEDs."""
        #self.leds.off_all()
        pass


    # ─────────────────────────────────────────────────────────────────
    # Weight reading + power-optimized HX711 usage via LowPowerScale
    # ─────────────────────────────────────────────────────────────────
    def get_weight(self):
        """
        Read weight using LowPowerScale.

        Internally:
        - LowPowerScale always works in grams (HX711 calibrated accordingly).
        - PowerManager.update_with_weight() is called inside LowPowerScale.
        - HX711 is powered down when idle (inside LowPowerScale low-power mode).

        Externally:
        - This method returns kilograms (for LEDs / JSON to phone).
        """
        try:
            # Choose mode based on current idle state:
            # - When NOT idle  -> normal active mode (more averaging).
            # - When idle      -> low-power read (still without extra sleep;
            #                    outer loop controls timing).
            if self.pm.idle:
                weight_g = self.scale.read_weight_low_power(
                    times=1,
                    idle_sleep_ms=0,  # no internal sleep; run() controls loop timing
                )
            else:
                weight_g = self.scale.read_weight_normal(times=3)

            self.last_weight_g = weight_g

            # Convert to kilograms for the rest of the app.
            #weight_kg = weight_g / 1000.0
            weight_kg = weight_g / 1000
            return weight_kg

        except Exception as e:
            print("HX711 error:", e)
            return 0.0

    def check_scale(self):
        """
        Periodic call from main loop:
        - Reads weight (in kg) using get_weight().
        - Keeps weight_tx updated (so TX JSON always has fresh weight).
        - Uses LEDs to signal basic weight state.
        """
        weight_kg = self.get_weight()
        self.weight_tx = weight_kg

        # Example visual logic:
        # - If weight > 1 kg and not some error (e.g. -128) → turn on green LED.
        # - Otherwise, blink red lightly (this can be changed as you wish).
        if weight_kg > 1 and weight_kg != -128:
            pass
            #self.led_green.on()
        else:
            pass
            #self.blink_led(self.led_red, 1)

    # ─────────────────────────────────────────────────────────────────
    # Reset RX/TX state (on disconnect)
    # ─────────────────────────────────────────────────────────────────
    def clear(self):
        """
        Reset received fused/GPS data and TX buffer.
        Called on BLE disconnect.
        """
        self.fused_rx_data = {
            "time": 0,
            "latitude": 0.0,
            "longitude": 0.0,
            "speed": 0.0,
            "altitude": 0.0,
            "accuracy": 0.0,
        }
        self.gps_rx_data = {
            "time": 0,
            "latitude": 0.0,
            "longitude": 0.0,
            "speed": 0.0,
            "altitude": 0.0,
            "accuracy": 0.0,
        }
        self.tx_data = {}

        print("RX and TX data reset")

    # ─────────────────────────────────────────────────────────────────
    # Main loop – dynamic sleep based on PowerManager state
    # ─────────────────────────────────────────────────────────────────
    def run(self):
        """
        Main loop for the device:
        - Continuously reads scale.
        - Handles BLE connection LED.
        - Adapts sleep time based on load/idle state (via PowerManager):

             * Active (load present):   fast loop (0.5 s)
             * Idle (no load, recent):  medium loop (2 s)
             * Deep idle (long idle):   slow loop (5 s)

        This reduces:
        - HX711 active time (via LowPowerScale + PowerManager).
        - CPU wakeups and power consumption.
        """
        self.timer = ticks_ms()

        while True:
            # 1. Read latest weight and update PowerManager (via LowPowerScale).
            self.check_scale()

            # 2. Connection LED behavior:
            #    - If not connected: blink blue every 1s.
            #    - If connected: keep blue ON.
            if not self.connected:
                now = ticks_ms()
                if ticks_diff(now, self.timer) > 1000:
                    #self.toggle_led(self.led_blue)
                    self.leds.on_connect()
                    self.timer = now
            else:
                #self.led_blue.on()
                self.leds.update()

            # 3. Decide how long to sleep based on power state:
            #    This is purely CPU / loop timing (does NOT deep sleep the chip).
            if self.pm.should_enter_deep_idle():
                base_sleep = 5.0   # seconds – very slow loop when long idle
            elif self.pm.idle:
                base_sleep = 2.0   # seconds – no load but not long enough for deep idle
            else:
                base_sleep = 0.5   # seconds – active mode, more frequent reads

            sleep(base_sleep)


if __name__ == "__main__":
    # Simple launcher for standalone testing.
    scale = BLEScale()
    try:
        scale.run()
    except KeyboardInterrupt:
        print("Stopping...")
    except Exception as e:
        print("Error:", e)
    finally:
        scale.off_all()
        print("Shutdown complete.")

