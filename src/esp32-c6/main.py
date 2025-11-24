# =============================================================================
# Project : Unforgotten – ESP32 BLE Scale (MicroPython)
# File    : main.py
# Version : 1.0.0 (2025-10-20)
# Author  : CA
#
# Summary:
#   Entrypoint – constructs BLEScale and runs the main loop.
# =============================================================================

# =============================================================================
# Purpose : Entrypoint — construct and run BLEScale with safe error signal.
# =============================================================================

from time import sleep

from lib.unforgotten_v3 import BLEScale

def main():
    scale = BLEScale()
    try:
        scale.run()
    except KeyboardInterrupt:
        print("Stopping...")
    except Exception as e:
        print("Fatal error:", e)
        try:
            scale.leds.on_error()
            for _ in range(15):
                scale.leds.update()
                sleep(0.08)
        except:
            pass
    finally:
        scale.leds.off_all()
        print("Shutdown complete.")

if __name__ == "__main__":
    main()

