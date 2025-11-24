# =============================================================================
# Board : ESP32-C6 DevKit  (Reference constants – copy values into common_const)
# RGB   : Discrete RGB pins (example wiring)
# =============================================================================
from micropython import const

# HX711 pins (example; set to your wiring)
DT_PIN  = const(5)
SCK_PIN = const(4)

# Discrete RGB on dedicated pins
USE_NEOPIXEL  = False               # ✅ C6 uses discrete RGB in this setup
ACTIVE_LOW_RGB = False
RED_LED_PIN     = const(18)
GREEN_LED_PIN   = const(19)
BLUE_LED_PIN    = const(20)

# Optional mono status LED (set None if not used)
STATUS_LED_PIN = None
ACTIVE_LOW_MONO = False

# If you ever attach a NeoPixel on C6
NEOPIXEL_PIN         = const(8)     # common working pin on C6
NEOPIXEL_COUNT       = const(1)
NEOPIXEL_INDEX       = const(0)
NEOPIXEL_BRIGHTNESS  = 0.20

BOARD = "ESP32-C6"
