# NeoPixel + Mono LED hardware diagnostic for ESP32 / ESP32-C6
# - Tries multiple candidate pins for NeoPixel DIN
# - Blinks mono LED both polarities to prove the loop and the pin works
# - Uses bright, long holds so you can *see* it

import time
from machine import Pin

try:
    import neopixel
    HAVE_NP = True
except ImportError:
    HAVE_NP = False

# Known pins :
# FireBeetle 2 with esp32-e NeoPixel RGB pin = 5
# esp32-c6  NeoPixel RGB pin = 8
# esp32-s3  NeoPixel RGB pin = 48


# ==== EDIT THESE IF YOU KNOW YOUR EXACT PINS ===============================
CANDIDATE_NP_PINS = [48, 13, 18, 21, 2, 20]  # try these in order (GPIO numbers)
NEOPIXEL_COUNT      = 1
NEOPIXEL_INDEX      = 0
NEOPIXEL_BRIGHTNESS = 0.9   # BRIGHT for the test (0.9 ~ 90%)

MONO_LED_PIN        = 15    # set to None if you have no mono LED
MONO_ACTIVE_LOW     = False # try True later if first mono test fails
# ==========================================================================

def show_np(np, idx, rgb, brightness=1.0):
    r, g, b = rgb
    np[idx] = (int(r*brightness), int(g*brightness), int(b*brightness))
    np.write()

def mono_set(pin_obj, v, active_low=False):
    if pin_obj is None:
        return
    if active_low:
        v = 0 if v else 1
    pin_obj.value(v)

def blink_mono(pin_obj, active_low, times=4, on_ms=250, off_ms=250):
    if pin_obj is None:
        print("Mono LED: (none configured)")
        return
    print("Mono LED blink test (active_low=%s)" % active_low)
    for _ in range(times):
        mono_set(pin_obj, 1, active_low)
        time.sleep(on_ms/1000)
        mono_set(pin_obj, 0, active_low)
        time.sleep(off_ms/1000)

def test_neopixel_on_pin(pin_no):
    print("Trying NeoPixel on GPIO%d ..." % pin_no)
    try:
        np = neopixel.NeoPixel(Pin(pin_no, Pin.OUT), NEOPIXEL_COUNT)
    except Exception as e:
        print("  ! Could not init NeoPixel on GPIO%d: %r" % (pin_no, e))
        return False

    try:
        # Red → Green → Blue (holds)
        show_np(np, NEOPIXEL_INDEX, (255, 0, 0), NEOPIXEL_BRIGHTNESS); time.sleep(0.5)
        show_np(np, NEOPIXEL_INDEX, (0, 255, 0), NEOPIXEL_BRIGHTNESS); time.sleep(0.5)
        show_np(np, NEOPIXEL_INDEX, (0, 0, 255), NEOPIXEL_BRIGHTNESS); time.sleep(0.5)
        # Blink blue
        for _ in range(6):
            show_np(np, NEOPIXEL_INDEX, (0, 0, 255), NEOPIXEL_BRIGHTNESS)
            time.sleep(0.25)
            show_np(np, NEOPIXEL_INDEX, (0, 0, 0), 0.0)
            time.sleep(0.25)
        # Off
        show_np(np, NEOPIXEL_INDEX, (0, 0, 0), 0.0)
        print("  ✅ NeoPixel responded on GPIO%d" % pin_no)
        return True
    except Exception as e:
        print("  ! NeoPixel write failed on GPIO%d: %r" % (pin_no, e))
        return False

def main():
    print("\n=== NeoPixel + Mono LED Diagnostic ===")
    if MONO_LED_PIN is not None:
        mono = Pin(MONO_LED_PIN, Pin.OUT, value=0)
    else:
        mono = None

    # 1) Prove the loop + mono pin works (both polarities)
    blink_mono(mono, MONO_ACTIVE_LOW, times=4)
    if mono is not None:
        # Try inverted once so you can see it either way
        blink_mono(mono, not MONO_ACTIVE_LOW, times=4)

    # 2) Check neopixel module
    if not HAVE_NP:
        print("❌ 'neopixel' module not found in this firmware. Install a build with NeoPixel support.")
        return

    # 3) Try candidate pins for WS2812 DIN
    print("Testing candidate NeoPixel pins:", CANDIDATE_NP_PINS)
    worked = False
    for p in CANDIDATE_NP_PINS:
        if test_neopixel_on_pin(p):
            print(">>> Use NEOPIXEL_PIN = %d in your config.\n" % p)
            worked = True
            break

    if not worked:
        print("\n❌ No response on any candidate pin.")
        print("Check: power (3.3/5V per LED), COMMON GND, DIN direction, brightness, pin list.")
        print("Tip: On many ESP32-C6 devkits the onboard WS2812 is on GPIO8.")

    print("=== Diagnostic end ===\n")

if __name__ == "__main__":
    main()
