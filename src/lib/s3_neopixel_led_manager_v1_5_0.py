# =============================================================================
# Project  : Unforgotten – ESP BLE Scale
# File     : led_manager_rgb_s3.py
# Version  : 1.5.0
# Author   : you
# Summary  : S3 onboard NeoPixel (GPIO48) manager (no discrete pins)
# Behavior : 
#   - Not connected  : BLUE blinking (toggle) until BLE connects
#   - Connected idle : BLUE solid
#   - Transfer       : GREEN blinking for a short window
#   - Error (optional): RED blinking window
# Purpose  : Simple, dependable state machine for one RGB NeoPixel
# =============================================================================

import time
from machine import Pin
from time import ticks_ms, ticks_diff

try:
    import neopixel
except ImportError:
    neopixel = None


def _scale(rgb, b):
    r, g, bb = rgb
    return (int(r * b), int(g * b), int(bb * b))


class S3RGBManager:
    C_OFF = (0, 0, 0)
    C_B   = (0, 0, 255)
    C_G   = (0, 255, 0)
    C_R   = (255, 0, 0)

    def __init__(
        self, np_pin, *, np_count=1, np_index=0, np_brightness=0.2,
        # blue = connection state
        blue_blink_period_ms=1000,  # how fast to blink blue when NOT connected
        # green = transfer pulse
        green_pulse_window_ms=600,  # how long after transfer to show green blink
        green_blink_period_ms=200,
        # red = error optional
        red_error_window_ms=2000,
        red_blink_period_ms=180,
        self_test=True
    ):
        self._np_ok = False
        self._np = None
        self._idx = int(np_index)
        self._b = float(np_brightness)

        if neopixel:
            try:
                self._np = neopixel.NeoPixel(Pin(np_pin, Pin.OUT), int(np_count))
                self._np_ok = True
            except Exception as e:
                print("[FB2LED] NeoPixel init error:", e)
        else:
            print("[FB2LED] neopixel module missing.")

        # State flags
        self._connected = False
        self._t_xfer = None
        self._t_err = None

        # Timing
        self._p_blue  = int(blue_blink_period_ms)
        self._w_green = int(green_pulse_window_ms)
        self._p_green = int(green_blink_period_ms)
        self._w_red   = int(red_error_window_ms)
        self._p_red   = int(red_blink_period_ms)

        # Start OFF
        self._set(self.C_OFF)

        # Quick self-test: R → G → B → OFF
        if self._np_ok and self_test:
            for c in (self.C_R, self.C_G, self.C_B, self.C_OFF):
                self._set(c)
                time.sleep(0.12)

    # ── Public API ──────────────────────────────────────────────────
    def on_connect(self):
        """Called from BLE IRQ when central connects."""
        self._connected = True
        # Next update() will keep it BLUE solid (unless transfer/error)
        self._set(self.C_B)

    def on_disconnect(self):
        """Called from BLE IRQ when central disconnects."""
        self._connected = False
        self._t_xfer = None
        self._t_err = None
        # Next update() will blink BLUE
        self._set(self.C_OFF)

    def on_transfer(self):
        """Called whenever we have RX/TX activity (write/read)."""
        self._t_xfer = ticks_ms()

    def on_error(self):
        """Optional: call on severe error to blink RED for a while."""
        self._t_err = ticks_ms()

    def off_all(self):
        self._set(self.C_OFF)

    def update(self):
        """
        Call this regularly from the main loop.

        Behavior:
          - If error window: RED blinking
          - Else if connected & recent transfer: GREEN blinking
          - Else if connected: BLUE solid
          - Else (not connected): BLUE blinking
        """
        now = ticks_ms()

        # 1) RED error has highest priority
        if self._win(now, self._t_err, self._w_red):
            v = self._blink(now, self._p_red)
            self._set(self.C_R if v else self.C_OFF)
            return

        # 2) Recent transfer → GREEN blink (only when connected)
        if self._connected and self._win(now, self._t_xfer, self._w_green):
            v = self._blink(now, self._p_green)
            self._set(self.C_G if v else self.C_OFF)
            return

        # 3) Connected but no recent transfer → solid BLUE
        if self._connected:
            self._set(self.C_B)
        else:
            # 4) Not connected → BLUE blinking
            v = self._blink(now, self._p_blue)
            self._set(self.C_B if v else self.C_OFF)

    # ── Internals ───────────────────────────────────────────────────
    @staticmethod
    def _win(now, t0, win):
        return (t0 is not None) and (ticks_diff(now, t0) < win)

    @staticmethod
    def _blink(now, period):
        if period <= 0:
            return 0
        half = period // 2 or 1
        return (now // half) & 1  # 0/1 toggle

    def _set(self, rgb):
        if not self._np_ok:
            return
        try:
            self._np[self._idx] = _scale(rgb, self._b)
            self._np.write()
        except Exception as e:
            print("[FB2LED] NeoPixel write error:", e)
            self._np_ok = False
