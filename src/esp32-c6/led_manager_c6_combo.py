# =============================================================================
# Project  : Unforgotten – ESP BLE Scale
# File     : led_manager_c6_combo.py
# Version  : 1.4.0
# Author   : you
# Summary  : ESP32-C6 LED manager that drives BOTH a NeoPixel (GPIO8) and
#            external discrete RGB LEDs (GPIO 18/19/20) in perfect sync.
# Behavior : Non-blocking LED state machine (blue=conn, green=activity, red=error)
# Purpose  : Match clarification: C6 must blink NeoPixel + pins together
# Style    : Clear on/off API + tiny helpers
# =============================================================================

import time
from machine import Pin
from time import ticks_ms, ticks_diff
try:
    import neopixel
except ImportError:
    neopixel = None

def _scale(rgb, b):
    r,g,bb = rgb
    return (int(r*b), int(g*b), int(bb*b))

class C6ComboLEDManager:
    C_OFF=(0,0,0); C_B=(0,0,255); C_G=(0,255,0); C_R=(255,0,0)

    def __init__(
        self,
        *,
        # NeoPixel
        np_pin, np_count=1, np_index=0, np_brightness=0.2,
        # Discrete RGB
        blue_pin, green_pin, red_pin, active_low_rgb=False,
        # Timings
        blue_blink_period_ms=1000,
        green_pulse_window_ms=600, green_blink_period_ms=200,
        red_error_window_ms=2000,  red_blink_period_ms=180,
        self_test=True
    ):
        # NeoPixel init
        self._np_ok=False; self._np=None
        self._idx=int(np_index); self._b=float(np_brightness)
        if neopixel:
            try:
                self._np = neopixel.NeoPixel(Pin(np_pin, Pin.OUT), int(np_count))
                self._np_ok=True
            except Exception as e:
                print("[C6Combo] NeoPixel init error:", e)
        else:
            print("[C6Combo] neopixel module missing.")

        # Discrete RGB init
        self._blue  = Pin(blue_pin,  Pin.OUT, value=0)
        self._green = Pin(green_pin, Pin.OUT, value=0)
        self._red   = Pin(red_pin,   Pin.OUT, value=0)
        self._low   = active_low_rgb

        # State + timings
        self._connected=False; self._t_xfer=None; self._t_err=None
        self._p_blue=int(blue_blink_period_ms)
        self._w_green=int(green_pulse_window_ms); self._p_green=int(green_blink_period_ms)
        self._w_red=int(red_error_window_ms);     self._p_red=int(red_blink_period_ms)

        # Self-test / initial off
        self._set_rgb(self.C_OFF)
        if self._np_ok and self_test:
            for c in (self.C_R,self.C_G,self.C_B,self.C_OFF):
                self._set_rgb(c); time.sleep(0.12)

    # ----- explicit on/off style API -----------------------------------------
    def on_connect(self):    self._connected=True;  self._set_rgb(self.C_B)
    def on_disconnect(self): self._connected=False; self._t_xfer=None
    def on_transfer(self):   self._t_xfer=ticks_ms()
    def on_error(self):      self._t_err=ticks_ms()
    def off_all(self):       self._set_rgb(self.C_OFF)

    def update(self):
        now=ticks_ms()

        # Error dominates
        if self._win(now,self._t_err,self._w_red):
            v=self._blink(now,self._p_red); self._set_rgb(self.C_R if v else self.C_OFF); return

        # Activity pulse
        if self._connected and self._win(now,self._t_xfer,self._w_green):
            v=self._blink(now,self._p_green); self._set_rgb(self.C_G if v else self.C_OFF); return

        # Baseline
        if self._connected:
            self._set_rgb(self.C_B)
        else:
            v=self._blink(now,self._p_blue); self._set_rgb(self.C_B if v else self.C_OFF)

    # ----- helpers ------------------------------------------------------------
    @staticmethod
    def _win(now,t0,win):   return (t0 is not None) and (ticks_diff(now,t0) < win)
    @staticmethod
    def _blink(now,period): return 0 if period<=0 else ((now // (period // 2 or 1)) & 1)

    def _set_rgb(self, rgb):
        # drive NeoPixel
        if self._np_ok:
            try:
                self._np[self._idx]=_scale(rgb,self._b)
                self._np.write()
            except Exception as e:
                print("[C6Combo] NeoPixel write error:", e)
                self._np_ok=False

        # drive discrete
        r,g,b = rgb
        self._pin_set(self._red,   1 if r else 0)
        self._pin_set(self._green, 1 if g else 0)
        self._pin_set(self._blue,  1 if b else 0)

    def _pin_set(self, pin, v):
        if self._low: v = 0 if v else 1
        if pin.value()!=v: pin.value(v)
