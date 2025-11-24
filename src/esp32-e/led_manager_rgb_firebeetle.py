# =============================================================================
# NeoPixel RGB manager (FireBeetle 2 onboard WS2812 on GPIO2)
# =============================================================================
import time
from machine import Pin
from time import ticks_ms, ticks_diff
try:
    import neopixel
except ImportError:
    neopixel = None

def _scale(rgb, b):
    r,g,bv = rgb
    return (int(r*b), int(g*b), int(bv*b))

class FireBeetleRGBManager:
    C_OFF=(0,0,0); C_B=(0,0,255); C_G=(0,255,0); C_R=(255,0,0)

    def __init__(
        self, np_pin, *, np_count=1, np_index=0, np_brightness=0.2,
        mono_led_pin=None, active_low_mono=False,
        blue_blink_period_ms=1000, green_pulse_window_ms=600, green_blink_period_ms=200,
        red_error_window_ms=2000, red_blink_period_ms=180, self_test=True
    ):
        self._ok=False; self._np=None
        self._idx=int(np_index); self._b=float(np_brightness)
        if neopixel:
            try:
                self._np = neopixel.NeoPixel(Pin(np_pin, Pin.OUT), int(np_count))
                self._ok=True
            except Exception as e:
                print("[NeoPixel] init error:", e)
        else:
            print("[NeoPixel] module missing.")

        self._mono = Pin(mono_led_pin, Pin.OUT, value=0) if mono_led_pin is not None else None
        self._mono_low = active_low_mono

        self._connected=False; self._t_xfer=None; self._t_err=None
        self._blue_period=int(blue_blink_period_ms)
        self._green_window=int(green_pulse_window_ms); self._green_period=int(green_blink_period_ms)
        self._red_window=int(red_error_window_ms);     self._red_period=int(red_blink_period_ms)

        self._set_rgb(self.C_OFF); self._set_mono(0)
        if self._ok and self_test:
            for c in (self.C_R,self.C_G,self.C_B,self.C_OFF):
                self._set_rgb(c); time.sleep(0.12)

    # on/off style calls
    def on_connect(self):    self._connected=True;  self._set_rgb(self.C_B); self._set_mono(1)
    def on_disconnect(self): self._connected=False; self._t_xfer=None
    def on_transfer(self):   self._t_xfer=ticks_ms()
    def on_error(self):      self._t_err=ticks_ms()
    def off_all(self):       self._set_rgb(self.C_OFF); self._set_mono(0)

    def update(self):
        now=ticks_ms()

        if self._win(now,self._t_err,self._red_window):
            v=self._blink(now,self._red_period)
            self._set_rgb(self.C_R if v else self.C_OFF); self._set_mono(v); return

        if self._connected and self._win(now,self._t_xfer,self._green_window):
            v=self._blink(now,self._green_period)
            self._set_rgb(self.C_G if v else self.C_OFF); self._set_mono(v); return

        if self._connected:
            self._set_rgb(self.C_B); self._set_mono(1)
        else:
            v=self._blink(now,self._blue_period)
            self._set_rgb(self.C_B if v else self.C_OFF); self._set_mono(v)

    @staticmethod
    def _win(now,t0,win): return (t0 is not None) and (ticks_diff(now,t0) < win)
    @staticmethod
    def _blink(now,period):
        if period<=0: return 0
        half=period//2 or 1
        return (now//half)&1

    def _set_rgb(self, rgb):
        if not self._ok: return
        try:
            self._np[self._idx]=_scale(rgb,self._b)
            self._np.write()
        except Exception as e:
            print("[NeoPixel] write error:", e)
            self._ok=False

    def _set_mono(self, v):
        if self._mono is None: return
        if self._mono_low: v = 0 if v else 1
        if self._mono.value()!=v: self._mono.value(v)
