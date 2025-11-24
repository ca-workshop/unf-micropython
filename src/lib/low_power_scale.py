# low_power_scale.py
import time

from power_manager import PowerManager
from sensors.hx711_driver import HX711


class LowPowerScale:
    """
    Wraps HX711 + PowerManager to provide:
    - normal read mode (active, frequent)
    - low-power read mode (HX711 mostly powered down)
    """

    def __init__(self, hx: HX711, pm: PowerManager):
        self.hx = hx
        self.pm = pm
        self._last_weight_g = 0.0

    @property
    def last_weight(self) -> float:
        return self._last_weight_g

    def read_weight_normal(self, times: int = 3) -> float:
        """
        Active mode:
        - HX711 stays powered (power_up called just in case)
        - we read with more averaging and higher frequency.
        """
        self.hx.power_up()
        # get_units() returns grams if SCALE/OFFSET are calibrated
        weight = self.hx.get_units(times=times)
        self.pm.update_with_weight(weight)
        self._last_weight_g = weight
        return weight

    def read_weight_low_power(self,
                              times: int = 1,
                              idle_sleep_ms: int = 500) -> float:
        """
        Idle mode:
        - Quickly power up, read once (or few times)
        - Update idle state
        - If still idle, power_down and sleep for idle_sleep_ms
        """
        self.hx.power_up()
        # HX711 needs a bit of time to settle after power up
        time.sleep_ms(50)

        weight = self.hx.get_units(times=times)
        self.pm.update_with_weight(weight)
        self._last_weight_g = weight

        if self.pm.idle:
            self.hx.power_down()
            time.sleep_ms(idle_sleep_ms)

        return weight
