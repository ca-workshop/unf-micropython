# =============================================================================
# Board : FireBeetle 2 ESP32-E – Discrete RGB (default) or NeoPixel optional
# File  : v1/common_const.py  (rename this file to that name)
# =============================================================================
from micropython import const

# ---- HX711 pins ----
DT_PIN  = const(5)      # set to your wiring
SCK_PIN = const(18)

# ---- Discrete RGB pins (default on FireBeetle 2 examples) ----
USE_NEOPIXEL  = False   # set True if you attach a WS2812 instead
ACTIVE_LOW_RGB= False   # set True if your RGB is active-low
RED_LED_PIN   = const(12)
GREEN_LED_PIN = const(14)
BLUE_LED_PIN  = const(25)

# ---- Optional mono LED ----
STATUS_LED_PIN = 2      # onboard LED is often GPIO2; set None if not used
ACTIVE_LOW_MONO = False

# ---- If you connect a NeoPixel instead of discrete RGB ----
NEOPIXEL_PIN        = const(13)     # set DIN if you use WS2812
NEOPIXEL_COUNT      = const(1)
NEOPIXEL_INDEX      = const(0)
NEOPIXEL_BRIGHTNESS = 0.20

# ---- BLE IRQ codes ----
IRQ_CENTRAL_CONNECT            = const(1)
IRQ_CENTRAL_DISCONNECT         = const(2)
IRQ_GATTS_WRITE                = const(3)
IRQ_GATTS_READ_REQUEST         = const(4)
IRQ_SCAN_RESULT                = const(5)
IRQ_SCAN_DONE                  = const(6)
IRQ_PERIPHERAL_CONNECT         = const(7)
IRQ_PERIPHERAL_DISCONNECT      = const(8)
IRQ_GATTC_SERVICE_RESULT       = const(9)
IRQ_GATTC_SERVICE_DONE         = const(10)
IRQ_GATTC_CHARACTERISTIC_RESULT= const(11)
IRQ_GATTC_CHARACTERISTIC_DONE  = const(12)
IRQ_GATTC_DESCRIPTOR_RESULT    = const(13)
IRQ_GATTC_DESCRIPTOR_DONE      = const(14)
IRQ_GATTC_READ_RESULT          = const(15)
IRQ_GATTC_READ_DONE            = const(16)
IRQ_GATTC_WRITE_DONE           = const(17)
IRQ_GATTC_NOTIFY               = const(18)
IRQ_GATTC_INDICATE             = const(19)
IRQ_GATTS_INDICATE_DONE        = const(20)
IRQ_MTU_EXCHANGED              = const(21)
IRQ_L2CAP_ACCEPT               = const(22)
IRQ_L2CAP_CONNECT              = const(23)
IRQ_L2CAP_DISCONNECT           = const(24)
IRQ_L2CAP_RECV                 = const(25)
IRQ_L2CAP_notifyClient_READY   = const(26)
IRQ_CONNECTION_UPDATE          = const(27)
IRQ_ENCRYPTION_UPDATE          = const(28)
IRQ_GET_SECRET                 = const(29)
IRQ_SET_SECRET                 = const(30)

# ---- GATT flags ----
FLAG_BROADCAST                  = const(0x0001)
FLAG_READ                       = const(0x0002)
FLAG_WRITE_NO_RESPONSE          = const(0x0004)
FLAG_WRITE                      = const(0x0008)
FLAG_NOTIFY                     = const(0x0010)
FLAG_INDICATE                   = const(0x0020)
FLAG_AUTHENTICATED_SIGNED_WRITE = const(0x0040)
FLAG_AUX_WRITE                  = const(0x0100)
FLAG_READ_ENCRYPTED             = const(0x0200)
FLAG_READ_AUTHENTICATED         = const(0x0400)
FLAG_READ_AUTHORIZED            = const(0x0800)
FLAG_WRITE_ENCRYPTED            = const(0x1000)
FLAG_WRITE_AUTHENTICATED        = const(0x2000)
FLAG_WRITE_AUTHORIZED           = const(0x4000)
