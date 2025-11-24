# power_manager.py
import time

# Tune these for your real noise level and behavior:
#NO_LOAD_THRESHOLD_G = 50.0      # abs(weight) below this ⇒ "no load"
NO_LOAD_THRESHOLD_G = 1.0      # abs(weight) below this ⇒ "no load"
NO_LOAD_STABLE_SAMPLES = 20     # consecutive no-load samples
NO_LOAD_IDLE_SECONDS = 30       # after this idle time ⇒ deep-idle candidate


class PowerManager:
    """
    Tracks whether the scale is under load or idle and
    decides when we can go into deep idle (for max battery).
    """

    def __init__(self):
        self._no_load_count = 0
        self._last_active_ms = time.ticks_ms()
        self.idle = False  # "soft" idle (no load, stable)

    def update_with_weight(self, weight_g: float):
        """
        Call this after each weight reading.
        """
        if abs(weight_g) < NO_LOAD_THRESHOLD_G:
            self._no_load_count += 1
        else:
            # any real load = active
            self._no_load_count = 0
            self._last_active_ms = time.ticks_ms()
            self.idle = False
            return

        if self._no_load_count >= NO_LOAD_STABLE_SAMPLES:
            self.idle = True

    def should_enter_deep_idle(self) -> bool:
        """
        Returns True when we've been idle long enough
        to justify deep sleep.
        """
        if not self.idle:
            return False

        elapsed_ms = time.ticks_diff(time.ticks_ms(), self._last_active_ms)
        elapsed_s = elapsed_ms / 1000.0
        return elapsed_s > NO_LOAD_IDLE_SECONDS
