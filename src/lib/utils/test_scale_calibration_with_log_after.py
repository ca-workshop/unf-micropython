# =============================================================================
# HX711 calibration helper
# - Tares with empty scale
# - Asks user to place known weight
# - Logs immediate weight after Enter
# - Computes SCALE factor and verifies it
# =============================================================================

from lib.sensors.hx711_driver import HX711
import s3_const as CFG
import time

KNOWN_GRAMS = 2000.0   # Change if your reference weight is different


def main():
    hx = HX711(CFG.DT_PIN, CFG.SCK_PIN)

    # 1) Start in raw mode (SCALE=1)
    hx.set_scale(1.0)

    print("\nStep 1/3: Remove ALL weight → tare in 1 second...")
    time.sleep(1.0)
    hx.tare()
    print("Tare complete.\n")

    # 2) Wait for user to load reference weight
    input(f"Step 2/3: Place {KNOWN_GRAMS} g on the scale and press Enter...")

    time.sleep(1.0)  # settle

    # Debug: immediate reading after pressing Enter
    instant = hx.get_value(times=10)
    print("\nImmediate raw delta after Enter:", instant)

    # Sample stability check (debug only)
    print("Sampling raw values for stability:")
    for i in range(5):
        print(f"  Sample {i+1}: {hx.get_value(times=5)}")
        time.sleep(0.2)

    # 3) Compute SCALE
    raw = hx.get_value(times=15)
    print(f"\nAverage raw delta for {KNOWN_GRAMS} g =", raw)

    scale = raw / KNOWN_GRAMS
    print("Calculated SCALE factor =", scale)

    # Apply calibration
    hx.set_scale(scale)
    time.sleep(0.5)

    # Verification
    check = hx.get_units(times=15)
    print(f"\nVerification: reading with {KNOWN_GRAMS} g =", check, "grams")

    print("\nCalibration complete.")
    print("👉 Put this into s3_const.py:\n")
    print(f"    HX711_SCALE = {scale}\n")

    # ------------------------------------------------------------
    # Step 4: CONTINUOUS LOGGING (every 2 seconds)
    # ------------------------------------------------------------
    print("Step 3/3: Continuous logging started.")
    print("Remove weight, add weight, test movement.")
    print("Logging weight every 2 seconds...\n")

    while True:
        grams = hx.get_units(times=20)     # smooth reading
        print(f"[{time.time():.0f}] Weight = {grams:.2f} g")
        time.sleep(2)


if __name__ == "__main__":
    main()