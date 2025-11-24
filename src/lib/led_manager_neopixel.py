# =============================================================================
# File    : led_manager_neopixel.py
# Purpose : Drive a NeoPixel (WS2812) RGB LED + optional mono status LED.
# Model   : Non-blocking, tick-driven state machine using ticks_ms().
#
# States:
#   - Disconnected : RGB blue blinks, Mono blinks
#   - Connected    : RGB blue solid, Mono solid
#   - Transfer     : RGB green pulses (short window), Mono pulses
#   - Error        : RGB red pulses (short window),   Mono pulses
# =============================================================================

# =============================================================================
# NeoPixel manager – Non-blocking, readable; works great on ESP32-C6
# =============================================================================
import time
from machine import Pin
from time import ticks_ms, ticks_diff
try:
    import neopixel
except ImportError:
    neopixel = None  # will fallback to mono-only

def _scale(rgb, brightness):
    r,g,b = rgb
    return (int(r*brightness), int(g*brightness), int(b*brightness))

class NeoPixelLedManager:
    C_OFF   = (0,0,0)
    C_BLUE  = (0,0,255)
    C_GREEN = (0,255,0)
    C_RED   = (255,0,0)

    def __init__(
        self, np_pin, *,
        np_count=1, np_index=0, np_brightness=0.2,
        mono_led_pin=None, active_low_mono=False,
        blue_blink_period_ms=1000,
        green_pulse_window_ms=600, green_blink_period_ms=200,
        red_error_window_ms=2000, red_blink_period_ms=180,
        self_test=True
    ):
        self._ok = False
        self._np = None
        self._np_count = int(np_count)
        self._np_index = int(np_index)
        self._np_brightness = float(np_brightness)

        self._mono = Pin(mono_led_pin, Pin.OUT, value=0) if mono_led_pin is not None else None
        self._active_low_mono = active_low_mono

        self._connected = False
        self._last_transfer_ms = None
        self._last_error_ms = None

        self._blue_period  = int(blue_blink_period_ms)
        self._green_window = int(green_pulse_window_ms)
        self._green_period = int(green_blink_period_ms)
        self._red_window   = int(red_error_window_ms)
        self._red_period   = int(red_blink_period_ms)

        if neopixel is None:
            print("[NeoPixel] module missing in firmware.")
        else:
            try:
                self._np = neopixel.NeoPixel(Pin(np_pin, Pin.OUT), self._np_count)
                self._ok = True
            except Exception as e:
                print("[NeoPixel] init error:", e)

        self._set_rgb(self.C_OFF); self._set_mono(0)

        if self._ok and self_test:
            self._self_test()

    # Events
    def on_connect(self):    self._connected = True;  self._set_rgb(self.C_BLUE);  self._set_mono(1)
    def on_disconnect(self): self._connected = False; self._last_transfer_ms = None
    def on_transfer(self):   self._last_transfer_ms = ticks_ms()
    def on_error(self):      self._last_error_ms = ticks_ms()
    def off_all(self):       self._set_rgb(self.C_OFF); self._set_mono(0)

    def update(self):
        now = ticks_ms()

        # Error
        if self._win(now, self._last_error_ms, self._red_window):
            v = self._blink(now, self._red_period)
            self._set_rgb(self.C_RED if v else self.C_OFF)
            self._set_mono(v)
            return

        # Transfer
        if self._connected and self._win(now, self._last_transfer_ms, self._green_window):
            v = self._blink(now, self._green_period)
            self._set_rgb(self.C_GREEN if v else self.C_OFF)
            self._set_mono(v)
            return

        # Baseline
        if self._connected:
            self._set_rgb(self.C_BLUE); self._set_mono(1)
        else:
            v = self._blink(now, self._blue_period)
            self._set_rgb(self.C_BLUE if v else self.C_OFF); self._set_mono(v)

    # Helpers
    @staticmethod
    def _win(now, start, window_ms): return (start is not None) and (ticks_diff(now, start) < window_ms)
    @staticmethod
    def _blink(now, period): 
        if period <= 0: return 0
        half = period // 2 or 1
        return (now // half) & 1

    def _set_rgb(self, rgb):
        if not self._ok: return
        try:
            self._np[self._np_index] = _scale(rgb, self._np_brightness)
            self._np.write()
        except Exception as e:
            print("[NeoPixel] write error:", e)
            self._ok = False

    def _set_mono(self, v):
        if self._mono is None: return
        if self._active_low_mono: v = 0 if v else 1
        if self._mono.value() != v: self._mono.value(v)

    def _self_test(self):
        for c in (self.C_RED, self.C_GREEN, self.C_BLUE, self.C_OFF):
            self._set_rgb(c); time.sleep(0.12)
        for _ in range(3):
            self._set_rgb(self.C_BLUE); self._set_mono(1); time.sleep(0.12)
            self._set_rgb(self.C_OFF);  self._set_mono(0); time.sleep(0.12)
