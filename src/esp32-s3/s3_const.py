# =============================================================================
# Board :  ESP32-S3  (Reference constants – copy values into common_const)
# RGB   : Onboard WS2812 NeoPixel on GPIO48 (per working guide)
# =============================================================================
from micropython import const

# HX711 pins (example; set to your wiring)
DT_PIN  = const(5)
SCK_PIN = const(18)

# Onboard NeoPixel
USE_NEOPIXEL         = True
NEOPIXEL_PIN         = const(48)      # ✅ S3 guide: GPIO48
NEOPIXEL_COUNT       = const(1)
NEOPIXEL_INDEX       = const(0)
NEOPIXEL_BRIGHTNESS  = 0.20

# Optional mono LED (set None if not used)
STATUS_LED_PIN = None
ACTIVE_LOW_MONO = False

# Discrete RGB fallback ()
ACTIVE_LOW_RGB  = False
RED_LED_PIN     = const(12)
GREEN_LED_PIN   = const(14)
BLUE_LED_PIN    = const(25)

BOARD = "ESP32-S3"
