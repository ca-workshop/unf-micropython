# np_diag_esp32_all.py
#
# NeoPixel hardware diagnostic for ESP32 / ESP32-C3 / ESP32-C6 / ESP32-S3
#
# - Detects board family from os.uname().machine
# - Picks a set of candidate GPIO pins for the NeoPixel DIN
# - Optionally blinks a mono LED to prove the loop is working
#
# Usage:
#   1. Copy this file to your board.
#   2. Run it from Thonny.
#   3. Watch the onboard or external NeoPixel.
#   4. When you see red/green/blue + blink, the current GPIO is correct.

import time
import sys
import os
from machine import Pin

try:
    import neopixel
    HAVE_NP = True
except ImportError:
    HAVE_NP = False

# ===================== USER SETTINGS =======================
# Mono LED configuration (optional)
# Set MONO_LED_PIN to the GPIO of a simple LED (or None if you do not have one)
MONO_LED_PIN = None      # example: 15, 2, 8, etc. or None
MONO_ACTIVE_LOW = False  # set True if your LED is wired active-low

# NeoPixel brightness (0.0 to 1.0)
NEOPIXEL_BRIGHTNESS = 0.9
NEOPIXEL_COUNT = 1
NEOPIXEL_INDEX = 0
# ===========================================================


def detect_board_family():
    """
    Try to detect ESP32 family (plain ESP32, C3, C6, S3)
    based on os.uname().machine string.
    """
    try:
        m = os.uname().machine.lower()
    except Exception:
        m = ""
    if "c3" in m:
        return "esp32-c3"
    if "c6" in m:
        return "esp32-c6"
    if "s3" in m:
        return "esp32-s3"
    if "esp32" in m:
        return "esp32"
    return "unknown"


def get_candidate_pins(board_family):
    """
    Return a list of candidate NeoPixel DIN GPIO pins
    for the given board family.
    These are guesses based on common devkits.
    Adjust if needed.
    """
    # Default candidates for generic ESP32 devkits
    generic = [5, 4, 2, 18, 21]

    if board_family == "esp32-c3":
        # Common guesses for C3 devkits:
        # - Some have WS2812 on GPIO8
        # - Others on GPIO2 or GPIO3
        return [8, 2, 3, 1]
    if board_family == "esp32-c6":
        # Many ESP32-C6 devkits have onboard NeoPixel on GPIO8
        # Then try some common extra pins
        return [8, 9, 18, 21, 2]
    if board_family == "esp32-s3":
        # Many S3 devkits (including some FireBeetle-style boards) use GPIO48
        return [48, 5, 38, 18, 21, 2]
    if board_family == "esp32":
        return generic

    # Unknown board: use a safe fallback
    return [8, 5, 4, 2, 18, 21]


def show_np(np_obj, idx, rgb, brightness):
    r, g, b = rgb
    r_val = int(r * brightness)
    g_val = int(g * brightness)
    b_val = int(b * brightness)
    np_obj[idx] = (r_val, g_val, b_val)
    np_obj.write()


def mono_set(pin_obj, value, active_low):
    if pin_obj is None:
        return
    if active_low:
        pin_obj.value(0 if value else 1)
    else:
        pin_obj.value(1 if value else 0) if False else pin_obj.value(value)


def blink_mono(pin_obj, active_low, times, on_ms, off_ms):
    if pin_obj is None:
        print("Mono LED: not configured")
        return

    print("Mono LED blink test (active_low = %s)" % active_low)

    for _ in range(times):
        mono_set(pin_obj, 1, active_low)
        time.sleep(on_ms / 1000.0)
        mono_set(pin_obj, 0, active_low)
        time.sleep(off_ms / 1000.0)


def test_neopixel_on_pin(pin_no):
    print("Trying NeoPixel on GPIO %d ..." % pin_no)

    try:
        pin = Pin(pin_no, Pin.OUT)
        np_obj = neopixel.NeoPixel(pin, NEOPIXEL_COUNT)
    except Exception as e:
        print("  Could not init NeoPixel on this pin:", e)
        return False

    try:
        # Red
        show_np(np_obj, NEOPIXEL_INDEX, (255, 0, 0), NEOPIXEL_BRIGHTNESS)
        time.sleep(0.5)

        # Green
        show_np(np_obj, NEOPIXEL_INDEX, (0, 255, 0), NEOPIXEL_BRIGHTNESS)
        time.sleep(0.5)

        # Blue
        show_np(np_obj, NEOPIXEL_INDEX, (0, 0, 255), NEOPIXEL_BRIGHTNESS)
        time.sleep(0.5)

        # Blink blue several times
        for _ in range(6):
            show_np(np_obj, NEOPIXEL_INDEX, (0, 0, 255), NEOPIXEL_BRIGHTNESS)
            time.sleep(0.25)
            show_np(np_obj, NEOPIXEL_INDEX, (0, 0, 0), 0.0)
            time.sleep(0.25)

        # Off
        show_np(np_obj, NEOPIXEL_INDEX, (0, 0, 0), 0.0)

        print("  NeoPixel responded on GPIO %d" % pin_no)
        return True

    except Exception as e:
        print("  NeoPixel write failed on GPIO %d:" % pin_no, e)
        return False


def main():
    print("")
    print("=== NeoPixel Diagnostic for ESP32 family ===")

    board_family = detect_board_family()
    print("Detected board family:", board_family)

    candidate_pins = get_candidate_pins(board_family)
    print("Candidate NeoPixel DIN pins:", candidate_pins)

    # Mono LED setup (optional)
    if MONO_LED_PIN is not None:
        try:
            mono_pin = Pin(MONO_LED_PIN, Pin.OUT, value=0)
        except Exception as e:
            print("Could not init mono LED pin:", e)
            mono_pin = None
    else:
        mono_pin = None

    # Step 1: test mono LED normal polarity
    if mono_pin is not None:
        blink_mono(mono_pin, MONO_ACTIVE_LOW, times=4, on_ms=250, off_ms=250)
        # Step 2: test inverse polarity
        blink_mono(mono_pin, not MONO_ACTIVE_LOW, times=4, on_ms=250, off_ms=250)

    # Step 3: check neopixel module presence
    if not HAVE_NP:
        print("")
        print("Error: 'neopixel' module not found in firmware.")
        print("Use a MicroPython build that includes the neopixel module.")
        return

    # Step 4: test all candidate GPIO pins
    worked = False
    for pin_no in candidate_pins:
        ok = test_neopixel_on_pin(pin_no)
        if ok:
            print("")
            print("Success: use NEOPIXEL DIN on GPIO %d." % pin_no)
            worked = True
            break

    if not worked:
        print("")
        print("No NeoPixel response on any candidate pin.")
        print("Check:")
        print("- Correct GPIO number for DIN")
        print("- Power (3.3 V or 5 V as required)")
        print("- Common ground between ESP and LED")
        print("- Data direction and wiring")

    print("=== Diagnostic end ===")
    print("")


if __name__ == "__main__":
    main()
