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
    C_B   = (0, 0, 255)   # Blue  – connection/search
    C_G   = (0, 255, 0)   # Green – transfer
    C_R   = (255, 0, 0)   # Red   – error

    def __init__(
        self, np_pin, *, np_count=1, np_index=0, np_brightness=0.2,
        # blue = connection state
        blue_blink_period_ms=1000,  # how fast to blink blue when NOT connected
        # green = transfer pulse
        green_pulse_window_ms=600,  # how long after transfer to show green blink
        green_blink_period_ms=200,
        # red = error (now constant until cleared)
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
        self._error_active = False  # NEW: error is a simple flag → solid RED

        # Timing
        self._p_blue  = int(blue_blink_period_ms)
        self._w_green = int(green_pulse_window_ms)
        self._p_green = int(green_blink_period_ms)

        # Start OFF
        self._set(self.C_OFF)

        # Quick self-test: R → G → B → OFF
        if self._np_ok and self_test:
            for c in (self.C_R, self.C_G, self.C_B, self.C_OFF):
                self._set(c)
                time.sleep(0.12)

    # ── Public API ──────────────────────────────────────────────────
    def on_connect(self):
        """
        Device connected:
          - Blue solid (connection OK)
        """
        self._connected = True
        # If we were in error, keep error (red) dominating.
        if not self._error_active:
            self._set(self.C_B)

    def on_disconnect(self):
        """
        Device NOT connected:
          - Blue blinking (searching for device)
        """
        self._connected = False
        self._t_xfer = None
        # We don't automatically clear error flag here; optional.
        if not self._error_active:
            self._set(self.C_OFF)

    def on_transfer(self):
        """
        Called whenever we have RX/TX activity (write/read).
        Effect:
          - Green blinking for a short time window (while connected)
        """
        self._t_xfer = ticks_ms()

    def on_error(self):
        """
        Called on severe error.
        Effect:
          - Solid RED, overrides connection/transfer states
          - Stays RED until manually cleared or device reset
        """
        self._error_active = True
        self._set(self.C_R)

    def clear_error(self):
        """
        Optional helper to clear the error state and return to normal behavior.
        After this:
          - update() will again show blue/green according to connection/transfer.
        """
        self._error_active = False
        # Force immediate refresh of LED according to current state
        self.update()

    def off_all(self):
        self._set(self.C_OFF)

    def update(self):
        """
        Call this regularly from the main loop.

        Behavior (priority order):
          1) If error_active: RED solid
          2) If connected & recent transfer: GREEN blinking
          3) If connected: BLUE solid
          4) If not connected: BLUE blinking
        """
        now = ticks_ms()

        # 1) ERROR has highest priority: solid RED
        if self._error_active:
            self._set(self.C_R)
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
            # 4) Not connected → BLUE blinking (searching)
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
