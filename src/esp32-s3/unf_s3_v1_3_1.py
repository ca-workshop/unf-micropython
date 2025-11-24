# =============================================================================
# Project  : Unforgotten – ESP BLE Scale
# File     : unforgotten.py
# Version  : 1.3.1
# Author   : you
# Summary  : BLE + HX711 + LED status with runtime choice of LED driver
# Behavior : Non-blocking loop (LED animation + weight read + power manager)
# =============================================================================

#from time import sleep
#from time import ticks_ms, ticks_diff
#from micropython import const
#from bluetooth import BLE
#import ujson

from time import sleep, ticks_ms, ticks_diff
from machine import Pin
from micropython import const
import bluetooth
import struct
import ujson
from bluetooth import BLE

from lib.sensors.hx711_driver import HX711
from payload import advertising_payload
from lib.common_const import *
import s3_const as CFG

from gatt_defs import WEIGHT_SERVICE_UUID, WEIGHT_SERVICE, GATT_SCHEMA_VERSION
from power_manager import PowerManager
from low_power_scale import LowPowerScale

from lib.s3_neopixel_led_manager_v1_5_0 import S3RGBManager
# from lib.common_const import (
#     IRQ_CENTRAL_CONNECT,
#     IRQ_CENTRAL_DISCONNECT,
#     IRQ_GATTS_WRITE,
#     IRQ_GATTS_READ_REQUEST,
# )

IRQ_CENTRAL_CONNECT = const(1)
IRQ_CENTRAL_DISCONNECT = const(2)
IRQ_GATTS_WRITE = const(3)
IRQ_GATTS_READ_REQUEST = const(4)


class BLEScale:
    def __init__(self, name="ESP32S3"):
        
        # Last measured weight **in kilograms** sent to the phone
        self.weight_tx = 0.0

        # Partial received data buffer for JSON lines
        self.rx_buffer = b""

        # Last raw weight in grams (for debug if needed)
        self.last_weight_g = 0.0

        self._init_ble()
        self._init_state()
        self._init_sensors()
        self._init_leds()
        self._init_gatt(name)

    # ---- init blocks ---------------------------------------------------------
    def _init_ble(self):
        self.ble = BLE()
        self.ble.active(True)
        self.ble.config(mtu=100)
        self.ble.irq(self._irq)

    def _init_state(self):
        self._connections = set()
        self.connected = False

        # Last measured weight **in kilograms** sent to the phone
        #self.weight_tx = 0.0

        # Partial received data buffer for JSON lines
        #self.rx_buffer = b""

        # Last raw weight in grams (for debug if needed)
        #self.last_weight_g = 0.0

        # RX data buffers for fused and GPS (received from Android)
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

    def _init_gatt(self, name):
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
        print("BLE services registered (GATT schema = %s)" % GATT_SCHEMA_VERSION)
        self._payload = advertising_payload(name=name, services=[WEIGHT_SERVICE_UUID])
        self._advertise()

    # ---- BLE IRQs ------------------------------------------------------------
    def _irq(self, event, data):
        if event == IRQ_CENTRAL_CONNECT:
            self._on_connect(data)
        elif event == IRQ_CENTRAL_DISCONNECT:
            self._on_disconnect(data)
        #elif event == IRQ_GATTS_WRITE:
        #    self._on_write(data)
        #elif event == IRQ_GATTS_READ_REQUEST:
        #    self._on_read(data)
        elif event == IRQ_GATTS_WRITE:
            # Data written by central to one of the RX characteristics.
            conn_handle, char_handle = data
            raw_data = self.ble.gatts_read(char_handle)
            # Parse JSON line(s) and update fused_rx_data / gps_rx_data.
            #self.save_received_data_1(char_handle, raw_data)
            self.save_received_data(char_handle, raw_data)
            self.leds.on_transfer()  # -> GREEN blink window

        elif event == IRQ_GATTS_READ_REQUEST:
            # Central reads one of our TX characteristics.
            conn_handle, char_handle = data
            self.send_tx_as_json_response(char_handle)
            print("onread")
            self.leds.on_transfer()  # -> GREEN blink window

    def _on_connect(self, data):
        conn_handle, _, _ = data
        self._connections.add(conn_handle)
        self.connected = True
        self.leds.on_connect()  # -> BLUE solid handling
        print("New connection:", conn_handle)

    def _on_disconnect(self, data):
        conn_handle, _, _ = data
        self._connections.discard(conn_handle)
        self.connected = False
        self.leds.on_disconnect()  # -> BLUE blink (via update)
        self._advertise()
        print("Disconnected:", conn_handle)
        self.clear()

    def _on_write(self, data):
        _conn, char_handle = data
        #raw = self.ble.gatts_read(char_handle)
        #self._ingest_rx(char_handle, raw)
        
    
        raw_data = self.ble.gatts_read(char_handle)
        # Parse JSON line(s) and update fused_rx_data / gps_rx_data.
        self.save_received_data_1(char_handle, raw_data)
        #self.save_received_data(char_handle, raw_data)
        self.leds.on_transfer()  # -> GREEN blink window
        # (weight is always read in run loop)

    def _on_read(self, data):
        conn_handle, char_handle = data
        #_conn, h = data
        #//self._reply_tx(h)
        
        #conn_handle, char_handle = data
        #self.toggle_led(self.led_green)
        self.send_tx_as_json_response(char_handle)
        self.leds.on_transfer()  # -> GREEN blink window

    # ---- Advertising ---------------------------------------------------------
    def _advertise(self, interval_us=500000):
        """
        Start BLE advertising so the device can be discovered.
        Called on startup and on disconnect.
        """
        try:
            self.ble.gap_advertise(None)
            sleep(0.05)
            self.ble.gap_advertise(interval_us, adv_data=self._payload)
            print("BLEScale - Advertising started")
        except OSError as e:
            print("Failed to advertise:", e)

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
        self.leds.update()

    def off_all(self):
        """Turn off all LEDs."""
        self.leds.off_all()

    # ─────────────────────────────────────────────────────────────────
    # Weight reading + power-optimized HX711 usage via LowPowerScale
    # ─────────────────────────────────────────────────────────────────
    def get_weight(self):
        try:
            if self.pm.idle:
                weight_g = self.scale.read_weight_low_power(
                    times=1,
                    idle_sleep_ms=0,  # loop controls sleep
                )
            else:
                weight_g = self.scale.read_weight_normal(times=3)

            self.last_weight_g = weight_g
            weight_kg = weight_g / 1000.0
            return weight_kg
        except Exception as e:
            print("HX711 error:", e)
            return 0.0

    def check_scale(self):
        weight_kg = self.get_weight()
        self.weight_tx = weight_kg

    # ─────────────────────────────────────────────────────────────────
    # Reset RX/TX state (on disconnect)
    # ─────────────────────────────────────────────────────────────────
    def clear(self):
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

    # ---- RX/TX JSON (simple version) -----------------------------------------
    def _ingest_rx(self, attr, raw):
        """
        Robust JSON-line parser for fused / gps RX.

        Expected format from Android:
            b'{"time":..., "latitude":..., ...}\\n'

        This function:
        - Accumulates bytes in self.rx_buffer
        - Splits on '\n'
        - Strips spaces and '\r'
        - Tries to decode + parse JSON
        - On error: prints debug info but does NOT crash
        """
        # 1) Accumulate raw bytes (may be partial)
        self.rx_buffer += raw

        while True:
            nl = self.rx_buffer.find(b"\n")
            if nl == -1:
                # No full line yet – wait for more data
                break

            # 2) Extract one line and keep the rest in buffer
            js_bytes = self.rx_buffer[:nl]
            self.rx_buffer = self.rx_buffer[nl + 1:]

            # 3) Strip whitespace / CR
            js_bytes = js_bytes.strip()
            if not js_bytes:
                # Empty line – ignore
                continue

            # 4) Decode to text
            try:
                js_str = js_bytes.decode()
            except UnicodeError as e:
                print("RX decode error:", e, "raw bytes:", js_bytes)
                continue

            # Remove trailing '\r' just in case it's CRLF
            if js_str.endswith("\r"):
                js_str = js_str[:-1]

            # 5) Try parse JSON
            try:
                d = ujson.loads(js_str)
            except Exception as e:
                print("RX parse error:", e, "raw JSON string:", js_str)
                # optional: continue waiting for next line
                continue

            # 6) Route to fused/gps
            if attr == self.fused_rx_handle:
                self.fused_rx_data.update(d)
                # print("fused_rx_data updated:", self.fused_rx_data)
            elif attr == self.gps_rx_handle:
                self.gps_rx_data.update(d)
                # print("gps_rx_data updated:", self.gps_rx_data)
            else:
                # Unknown handle (shouldn't happen)
                print("RX on unknown handle:", attr, "data:", d)


    def _reply_tx(self, attr):
        tx = {
            "from": "",
            "weight": self.weight_tx,
            "time": 0,
            "latitude": 0.0,
            "longitude": 0.0,
            "speed": 0.0,
            "altitude": 0.0,
            "accuracy": 0.0,
        }
        if attr == self.weight_tx_handle:
            tx["from"] = "weight"
        elif attr == self.fused_tx_handle:
            tx.update(self.fused_rx_data)
            tx["from"] = "fused"
        elif attr == self.gps_tx_handle:
            tx.update(self.gps_rx_data)
            tx["from"] = "gps"
        else:
            return

        try:
            self.ble.gatts_write(attr, ujson.dumps(tx).encode())
        except Exception as e:
            print("TX write error:", e)
            
    
    # ─────────────────────────────────────────────────────────────────
    # RX: handling fused/GPS JSON from Android
    # ─────────────────────────────────────────────────────────────────
    def save_received_data_1(self, attr_handle, raw_data):
        """
        STRICT, per-characteristic JSON-line parser.

        - Keeps a separate buffer *per* RX handle (fused/gps), so their bytes
          never mix.
        - Only accepts complete JSON objects: '{ ... }' terminated by '\n'.
        - Silently ignores partial / corrupt fragments.
        """

        # Lazy-init per-handle buffers dict
        if not hasattr(self, "_rx_buffers"):
            self._rx_buffers = {}

        # Get current buffer for this handle, append new raw bytes
        buf = self._rx_buffers.get(attr_handle, b"") + raw_data

        # Process all complete lines
        while True:
            nl = buf.find(b"\n")
            if nl == -1:
                # No full line yet – keep partial in buffer
                break

            line = buf[:nl].strip()
            buf = buf[nl + 1:]  # rest stays for next round

            if not line:
                # Empty line – skip
                continue

            # Decode bytes → string
            try:
                json_str = line.decode()
            except Exception:
                # Bad encoding – drop this line and keep going
                continue

            # Must look like a full JSON object
            if not (json_str.startswith("{") and json_str.endswith("}")):
                # Just ignore fragments like '41"}' or '...accuracy":"7.8}'
                continue

            # Parse JSON
            try:
                data = ujson.loads(json_str)
            except Exception:
                # Corrupted JSON – ignore this line
                continue

            # ------ Valid JSON here: update the right dict ------
            if attr_handle == self.fused_rx_handle:
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

            elif attr_handle == self.gps_rx_handle:
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

        # Save leftover partial bytes for this handle
        self._rx_buffers[attr_handle] = buf



    def save_received_data(self, attr_handle, raw_data):
        """
        Alternative debug version of the parser (kept from original).
        Prints raw JSON bytes and decoded string for debugging.
        """
        self.rx_buffer += raw_data

        while b"\n" in self.rx_buffer:
            try:
                json_bytes, self.rx_buffer = self.rx_buffer.split(b"\n", 1)
                json_bytes = json_bytes.strip()
                if not json_bytes:
                    continue

                print("Raw JSON bytes:", json_bytes)

                # Decode
                try:
                    json_str = json_bytes.decode()
                except UnicodeError as e:
                    print("RX decode error:", e)
                    continue

                print("json str data:", json_str)

                # Ignore obvious fragments that are not a full JSON object
                if not (json_str.startswith("{") and json_str.endswith("}")):
                    print("RX fragment ignored (not full JSON):", json_str)
                    continue

                # Parse JSON
                try:
                    data = ujson.loads(json_str)
                except Exception as e:
                    print("Failed to parse data:", e, "raw JSON:", json_str)
                    continue

                # Extra debug: show parsed latitude/longitude if exist
                if "latitude" in data:
                    print("Latitude (after decoding):", data["latitude"])
                if "longitude" in data:
                    print("Longitude (after decoding):", data["longitude"])

                # If we want to round here (optional)
                if "latitude" in data:
                    data["latitude"] = round(float(data["latitude"]), 7)
                if "longitude" in data:
                    data["longitude"] = round(float(data["longitude"]), 7)

                # Correct: update dict with dict, NOT with json_str
                if attr_handle == self.fused_rx_handle:
                    print("fused(fusedRx):", json_str, "\n")
                    self.fused_rx_data.update(data)

                elif attr_handle == self.gps_rx_handle:
                    print("gps(gpsRx):", json_str, "\n")
                    self.gps_rx_data.update(data)

            except Exception as e:
                print("save_received_data (debug) unexpected error:", e)


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
    # Main loop – dynamic sleep based on PowerManager state
    # ─────────────────────────────────────────────────────────────────
    def run(self):
        """
        Main loop:

        - Reads the scale (with power manager).
        - Always calls leds.update():

            * Not connected  → BLUE blinking (toggle)
            * Connected      → BLUE solid
            * Transfer event → GREEN blinking for a short window

        - Adapts sleep time based on idle/active state.
        """
        while True:
            # 1. Read latest weight and update power manager (inside LowPowerScale)
            self.check_scale()

            # 2. Advance LED state machine:
            #    - blue blink until connected
            #    - blue solid when connected
            #    - green blink on transfer
            self.leds.update()

            # 3. Decide sleep time based on power state
            if self.pm.should_enter_deep_idle():
                base_sleep = 5.0
            elif self.pm.idle:
                base_sleep = 2.0
            else:
                base_sleep = 0.5

            sleep(base_sleep)


if __name__ == "__main__":
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
