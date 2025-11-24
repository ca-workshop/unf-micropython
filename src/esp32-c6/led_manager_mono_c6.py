# =============================================================================
# Mono status LED manager (single pin)
# =============================================================================
from machine import Pin
from time import ticks_ms, ticks_diff

class MonoLedManager:
    def __init__(self, pin, *, active_low=False, blink_period_ms=1000, pulse_window_ms=600, pulse_period_ms=200):
        self._led = Pin(pin, Pin.OUT, value=0)
        self._low = active_low
        self._connected=False; self._t_xfer=None; self._t_err=None
        self._blink= int(blink_period_ms); self._pulse=int(pulse_period_ms); self._win=int(pulse_window_ms)

    def on_connect(self):    self._connected=True;  self._set(1)
    def on_disconnect(self): self._connected=False; self._t_xfer=None
    def on_transfer(self):   self._t_xfer=ticks_ms()
    def on_error(self):      self._t_err=ticks_ms()
    def off_all(self):       self._set(0)

    def update(self):
        now=ticks_ms()
        if self._win_active(now,self._t_err): self._set(self._blinkf(now,self._pulse)); return
        if self._connected and self._win_active(now,self._t_xfer): self._set(self._blinkf(now,self._pulse)); return
        self._set(1 if self._connected else self._blinkf(now,self._blink))

    def _set(self, v):
        if self._low: v = 0 if v else 1
        if self._led.value()!=v: self._led.value(v)
    def _blinkf(self, now, period):
        if period<=0: return 0
        half=period//2 or 1
        return (now//half)&1
    def _win_active(self, now, t0):
        return (t0 is not None) and (ticks_diff(now, t0) < self._win)
