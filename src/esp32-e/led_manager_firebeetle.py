# =============================================================================
# Discrete RGB manager – Non-blocking, readable; great for FireBeetle 2
# =============================================================================
from machine import Pin
from time import ticks_ms, ticks_diff

class RGBLedManager:
    def __init__(
        self, blue_pin, green_pin, red_pin, *,
        mono_led_pin=None, active_low_rgb=False, active_low_mono=False,
        blue_blink_period_ms=1000,
        green_pulse_window_ms=600, green_blink_period_ms=200,
        red_error_window_ms=2000, red_blink_period_ms=180
    ):
        self._blue  = Pin(blue_pin,  Pin.OUT, value=0)
        self._green = Pin(green_pin, Pin.OUT, value=0)
        self._red   = Pin(red_pin,   Pin.OUT, value=0)
        self._mono  = Pin(mono_led_pin, Pin.OUT, value=0) if mono_led_pin is not None else None

        self._rgb_low  = active_low_rgb
        self._mono_low = active_low_mono

        self._connected = False
        self._last_transfer_ms = None
        self._last_error_ms = None

        self._blue_period  = int(blue_blink_period_ms)
        self._green_window = int(green_pulse_window_ms)
        self._green_period = int(green_blink_period_ms)
        self._red_window   = int(red_error_window_ms)
        self._red_period   = int(red_blink_period_ms)

    # Events
    def on_connect(self):    self._connected = True;  self._set_rgb(self._blue,1); self._set_rgb(self._green,0); self._set_rgb(self._red,0); self._set_mono(1)
    def on_disconnect(self): self._connected = False; self._last_transfer_ms = None
    def on_transfer(self):   self._last_transfer_ms = ticks_ms()
    def on_error(self):      self._last_error_ms = ticks_ms()
    def off_all(self):       self._set_rgb(self._blue,0); self._set_rgb(self._green,0); self._set_rgb(self._red,0); self._set_mono(0)

    def update(self):
        now = ticks_ms()

        if self._win(now, self._last_error_ms, self._red_window):
            v = self._blink(now, self._red_period)
            self._set_rgb(self._red, v); self._set_rgb(self._green,0); self._set_rgb(self._blue,0); self._set_mono(v)
            return

        if self._connected and self._win(now, self._last_transfer_ms, self._green_window):
            v = self._blink(now, self._green_period)
            self._set_rgb(self._green, v); self._set_mono(v)
        else:
            self._set_rgb(self._green, 0)

        if self._connected:
            self._set_rgb(self._blue, 1); self._set_mono(1)
        else:
            v = self._blink(now, self._blue_period)
            self._set_rgb(self._blue, v); self._set_mono(v)

    # Helpers
    @staticmethod
    def _win(now, start, window_ms): return (start is not None) and (ticks_diff(now, start) < window_ms)
    @staticmethod
    def _blink(now, period): 
        if period <= 0: return 0
        half = period // 2 or 1
        return (now // half) & 1

    def _set_rgb(self, pin, v):
        if self._rgb_low: v = 0 if v else 1
        if pin.value() != v: pin.value(v)

    def _set_mono(self, v):
        if self._mono is None: return
        if self._mono_low: v = 0 if v else 1
        if self._mono.value() != v: self._mono.value(v)
