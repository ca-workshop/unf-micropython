# =============================================================================
# Project  : Unforgotten – ESP BLE Scale
# File     : led_manager_rgb_firebeetle.py
# Version  : 1.4.0
# Author   : you
# Summary  : FireBeetle 2 onboard NeoPixel (GPIO2) manager (no discrete pins)
# Behavior : Non-blocking state machine (blue=conn, green=activity, red=error)
# Purpose  : Match clarification: FireBeetle blinks only the RGB NeoPixel
# Style    : Minimal, dependable
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

class FireBeetleRGBManager:
    C_OFF=(0,0,0); C_B=(0,0,255); C_G=(0,255,0); C_R=(255,0,0)

    def __init__(
        self, np_pin, *, np_count=1, np_index=0, np_brightness=0.2,
        blue_blink_period_ms=1000,
        green_pulse_window_ms=600, green_blink_period_ms=200,
        red_error_window_ms=2000,  red_blink_period_ms=180,
        self_test=True
    ):
        self._np_ok=False; self._np=None
        self._idx=int(np_index); self._b=float(np_brightness)
        if neopixel:
            try:
                self._np = neopixel.NeoPixel(Pin(np_pin, Pin.OUT), int(np_count))
                self._np_ok=True
            except Exception as e:
                print("[FB2LED] NeoPixel init error:", e)
        else:
            print("[FB2LED] neopixel module missing.")

        self._connected=False; self._t_xfer=None; self._t_err=None
        self._p_blue=int(blue_blink_period_ms)
        self._w_green=int(green_pulse_window_ms); self._p_green=int(green_blink_period_ms)
        self._w_red=int(red_error_window_ms);     self._p_red=int(red_blink_period_ms)

        self._set(self.C_OFF)
        if self._np_ok and self_test:
            for c in (self.C_R,self.C_G,self.C_B,self.C_OFF):
                self._set(c); time.sleep(0.12)

    # API
    def on_connect(self):    self._connected=True;  self._set(self.C_B)
    def on_disconnect(self): self._connected=False; self._t_xfer=None
    def on_transfer(self):   self._t_xfer=ticks_ms()
    def on_error(self):      self._t_err=ticks_ms()
    def off_all(self):       self._set(self.C_OFF)

    def update(self):
        now=ticks_ms()
        if self._win(now,self._t_err,self._w_red):
            v=self._blink(now,self._p_red); self._set(self.C_R if v else self.C_OFF); return
        if self._connected and self._win(now,self._t_xfer,self._w_green):
            v=self._blink(now,self._p_green); self._set(self.C_G if v else self.C_OFF); return
        if self._connected:
            self._set(self.C_B)
        else:
            v=self._blink(now,self._p_blue); self._set(self.C_B if v else self.C_OFF)

    @staticmethod
    def _win(now,t0,win):    return (t0 is not None) and (ticks_diff(now,t0) < win)
    @staticmethod
    def _blink(now,period):  return 0 if period<=0 else ((now // (period // 2 or 1)) & 1)
    def _set(self, rgb):
        if not self._np_ok: return
        try:
            self._np[self._idx]=_scale(rgb,self._b)
            self._np.write()
        except Exception as e:
            print("[FB2LED] NeoPixel write error:", e)
            self._np_ok=False
