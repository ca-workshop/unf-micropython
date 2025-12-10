# =============================================================================
# Project  : Unforgotten – ESP BLE Scale
# File     : unforgotten.py
# Version  : 1.3.0
# Author   : you
# Summary  : BLE + HX711 + LED status with runtime choice of LED driver
# Behavior : Non-blocking loop (LED animation + 1 Hz weight read)
# Purpose  : Ship a readable, robust BLE scale peripheral
# Style    : Small methods; explicit control calls; safe fallbacks
# =============================================================================

from time import sleep
from micropython import const
from bluetooth import BLE
import ujson

from lib.sensors.hx711_driver import HX711
from lib.payload import advertising_payload
from s3_const import *
import s3_const as CFG
from lib.gatt_defs import WEIGHT_SERVICE_UUID, WEIGHT_SERVICE, GATT_SCHEMA_VERSION
from lib.power_manager import PowerManager          # Tracks "no load" / idle state
from lib.low_power_scale import LowPowerScale       # New wrapper around HX711 + PowerManager

from lib.s3_neopixel_led_manager import S3RGBManager

from lib.common_const import (
    IRQ_CENTRAL_CONNECT,
    IRQ_CENTRAL_DISCONNECT,
    IRQ_GATTS_WRITE,
    IRQ_GATTS_READ_REQUEST,
)


class BLEScale:
    def __init__(self, name="ESP32S3"):
        self.init_ble()
        self.init_state()
        self.init_sensors()
        self.init_leds()
        self.init_gatt(name)

    # ---- init blocks ---------------------------------------------------------
    def init_ble(self):
        self.ble = BLE()
        self.ble.active(True)
        self.ble.config(mtu=100)
        self.ble.irq(self.irq)

    def init_state(self):
        self._connections = set()
        self.connected = False

        # Last measured weight **in kilograms** sent to the phone
        self.weight_tx = 0.0

        # Partial received data buffer for JSON lines
        self.rx_buffer = b""

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

    def init_sensors(self):
        # HX711 load cell amplifier.
        # You should calibrate SCALE so that hx.get_units() returns grams.
        #self.hx = HX711(CFG.DT_PIN, CFG.SCK_PIN)
        #self.hx.set_scale(2280)   # calibration factor
        #self.offset = 0
        #self.hx.tare()
        
        self.hx = HX711(CFG.DT_PIN, CFG.SCK_PIN)
        self.hx.set_scale(CFG.HX711_SCALE)  # <-- same as in test script
        self.hx.tare()
        

        # ─────────────────────────────────────────────────────────────
        # Power manager + HX711 + LowPowerScale
        # ─────────────────────────────────────────────────────────────
        # PowerManager works in **grams**.
        self.pm = PowerManager()

        # Wrap HX711 + PowerManager into a single helper.
        self.scale = LowPowerScale(self.hx, self.pm)

    def init_leds(self):
        if CFG.USE_NEOPIXEL:
            self.leds = S3RGBManager(
                CFG.NEOPIXEL_PIN,
                np_count=CFG.NEOPIXEL_COUNT,
                np_index=CFG.NEOPIXEL_INDEX,
                np_brightness=CFG.NEOPIXEL_BRIGHTNESS,
            )
        else:
            # NOTE: Requires C6RGBManager import if you actually use this branch.
            from lib.c6_rgb_led_manager import C6RGBManager
            self.leds = C6RGBManager(
                CFG.BLUE_LED_PIN,
                CFG.GREEN_LED_PIN,
                CFG.RED_LED_PIN,
                active_low_rgb=getattr(CFG, "ACTIVE_LOW_RGB", False),
            )

    def init_gatt(self, name):
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
        self.advertise()

    # ---- BLE IRQs ------------------------------------------------------------
    def irq(self, event, data):
        if event == IRQ_CENTRAL_CONNECT:
            self.on_connect(data)
        elif event == IRQ_CENTRAL_DISCONNECT:
            self.on_disconnect(data)
        elif event == IRQ_GATTS_WRITE:
            self.on_write(data)
        elif event == IRQ_GATTS_READ_REQUEST:
            self.on_read(data)

    def on_connect(self, data):
        conn_handle, _, _ = data
        self._connections.add(conn_handle)
        self.connected = True
        self.leds.on_connect()
        print("New connection:", conn_handle)

    def on_disconnect(self, data):
        conn_handle, _, _ = data
        self._connections.discard(conn_handle)
        self.connected = False
        self.leds.on_disconnect()
        self.advertise()
        self.clear()
        print("Disconnected:", conn_handle)

    def on_write(self, data):
        _conn, h = data
        raw = self.ble.gatts_read(h)
        # Use the robust line-based JSON parser
        self.save_received_data_1(h, raw)
        self.leds.on_transfer()

    def on_read(self, data):
        _conn, h = data
        self.reply_tx(h)
        self.leds.on_transfer()

    # ---- Advertising ---------------------------------------------------------
    def advertise(self, interval_us=500_000):
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
                if not json_bytes:
                    continue

                json_str = json_bytes.decode()

                # Parse into Python dict.
                data = ujson.loads(json_str)

                # Fused location data update.
                if attr_handle == self.fused_rx_handle:
                    if "latitude" in data:
                        self.fused_rx_data["latitude"] = data["latitude"]
                    if "longitude" in data:
                        self.fused_rx_data["longitude"] = data["longitude"]
                    if "altitude" in data:
                        self.fused_rx_data["altitude"] = data["altitude"]
                    if "speed" in data:
                        self.fused_rx_data["speed"] = data["speed"]
                    if "time" in data:
                        self.fused_rx_data["time"] = data["time"]
                    if "accuracy" in data:
                        self.fused_rx_data["accuracy"] = data["accuracy"]

                # GPS location data update.
                elif attr_handle == self.gps_rx_handle:
                    if "latitude" in data:
                        self.gps_rx_data["latitude"] = data["latitude"]
                    if "longitude" in data:
                        self.gps_rx_data["longitude"] = data["longitude"]
                    if "altitude" in data:
                        self.gps_rx_data["altitude"] = data["altitude"]
                    if "speed" in data:
                        self.gps_rx_data["speed"] = data["speed"]
                    if "time" in data:
                        self.gps_rx_data["time"] = data["time"]
                    if "accuracy" in data:
                        self.gps_rx_data["accuracy"] = data["accuracy"]

            except Exception as e:
                print("Failed to parse data:", e)

    def save_received_data(self, attr_handle, raw_data):
        """
        Alternative debug version of the parser (kept from original).
        Not used in the main flow, but left here for debugging if needed.
        """
        self.rx_buffer += raw_data

        while b"\n" in self.rx_buffer:
            try:
                json_bytes, self.rx_buffer = self.rx_buffer.split(b"\n", 1)
                print("Raw JSON bytes:", json_bytes)
                json_str = json_bytes.decode()
                data = ujson.loads(json_str)
                print("json str data:", json_str)

                if "latitude" in data:
                    print("Latitude (after decoding):", data["latitude"])
                if "longitude" in data:
                    print("Longitude (after decoding):", data["longitude"])
            except Exception as e:
                print("Failed to parse data:", e)

    # Legacy parser – NOT used now, kept only as reference
    def ingest_rx(self, attr, raw):
        """
        Old RX parser (not used in the current flow).
        WARNING: References to __fused/__gps were removed from the state.
        Left here only as a historical reference – do not call.
        """
        try:
            self.rx_buffer += raw
            while b"\n" in self.rx_buffer:
                js, self.rx_buffer = self.rx_buffer.split(b"\n", 1)
                if not js:
                    continue
                _ = ujson.loads(js.decode())
        except Exception as e:
            print("RX parse error:", e)

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

    def reply_tx_1(self, attr):
        """
        Backward-compatible TX handler used by the READ IRQ.

        Simply delegates to send_tx_as_json_response(), so all JSON
        formatting lives in a single place.
        """
        self.send_tx_as_json_response(attr)
        
    def reply_tx(self, attr):
        """
        TX handler used by the READ IRQ.

        IMPORTANT:
        - Take a fresh weight reading before sending.
        - This makes the scale work even if run() is never called.
        """
        # 1. Update weight_tx with a fresh measurement
        self.check_scale()

        # 2. Build and send the JSON response
        self.send_tx_as_json_response(attr)

    # ─────────────────────────────────────────────────────────────────
    # LED helpers (delegating to S3RGBManager)
    # ─────────────────────────────────────────────────────────────────
    def toggle_led(self):
        """
        Kept only for API compatibility.
        For the RGB manager, 'toggle' just means 'advance animation'.
        """
        self.leds.update()

    def off_all(self):
        """Turn off all LEDs via the RGB manager."""
        self.leds.off_all()

    def blink_led(self, led, times=1, delay=200):
        """
        Blink the given LED a number of times.
        delay is in ms.
        """
        for _ in range(times):
            led.on()
            sleep(delay / 1000)
            led.off()
            sleep(delay / 1000)

    # ─────────────────────────────────────────────────────────────────
    # Weight reading + power-optimized HX711 usage via LowPowerScale
    # ─────────────────────────────────────────────────────────────────
    def get_weight_1(self):
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
            if self.pm.idle:
                weight_g = self.scale.read_weight_low_power(
                    times=1,
                    idle_sleep_ms=0,  # no internal sleep; run() controls loop timing
                )
            else:
                weight_g = self.scale.read_weight_normal(times=3)

            self.last_weight_g = weight_g
            #weight_kg = weight_g / 1000.0
            weight_kg = self.last_weight_g / 1000.0
            return weight_kg

        except Exception as e:
            print("HX711 error:", e)
            return 0.0
    def get_weight(self):
        """
        Read weight using LowPowerScale.

        Internally:
        - LowPowerScale always works in grams (HX711 calibrated accordingly).
        - PowerManager.update_with_weight() is called inside LowPowerScale.
        - HX711 is powered down when idle (inside LowPowerScale low-power mode).

        Externally:
        - Returns kilograms.
        - Also keeps weight_tx in sync.
        """
        try:
            if self.pm.idle:
                weight_g = self.scale.read_weight_low_power(
                    times=1,
                    idle_sleep_ms=0,  # no internal sleep; run() controls loop timing
                )
            else:
                weight_g = self.scale.read_weight_normal(times=3)

            self.last_weight_g = weight_g
            weight_kg = weight_g / 1000.0

            # Keep the TX field always up to date
            self.weight_tx = weight_kg

            return weight_kg

        except Exception as e:
            print("HX711 error:", e)
            self.weight_tx = 0.0
            return 0.0


    #working fine - method for testing 
    def get_weight_for_testing(self):
        """
        Minimal version that behaves like the working test loop:
        - Always use read_weight_low_power(times=1, idle_sleep_ms=0)
        - Return kilograms
        - Keep weight_tx in sync
        """
        try:
            # Use the same logic as your test: always low-power read, no branch on pm.idle
            weight_g = self.scale.read_weight_low_power(
                times=1,
                idle_sleep_ms=0
            )

            self.last_weight_g = weight_g
            weight_kg = weight_g / 1000.0

            self.weight_tx = weight_kg
            return weight_kg

        except Exception as e:
            print("HX711 error:", e)
            self.weight_tx = 0.0
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

        # Example visual logic can be added here if you want to use LED colours
        # based on weight threshold, etc.

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
        self.rx_buffer = b""

        print("RX and TX data reset")

    # ─────────────────────────────────────────────────────────────────
    # Main loop – dynamic sleep based on PowerManager state
    # ─────────────────────────────────────────────────────────────────
    def run(self):
        """
        Main loop for the device:

        - Reads scale (with power optimization via LowPowerScale + PowerManager).
        - Lets the RGB manager handle LED states:

              * Not connected       → blue blinking
              * Connected idle      → blue steady
              * Recent data transfer→ green blinking
              * Error window        → red blinking

        - Adapts loop sleep duration based on idle/active state.
        """
        while True:
            # 1. Read latest weight and update power manager.
            self.check_scale()

            # 2. Let the LED manager update its animation.
            self.leds.update()

            # 3. Decide sleep time based on power state.
            if self.pm.should_enter_deep_idle():
                base_sleep = 5.0   # seconds – deep idle
            elif self.pm.idle:
                base_sleep = 2.0   # seconds – idle but not long enough
            else:
                base_sleep = 0.5   # seconds – active load, faster updates

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
