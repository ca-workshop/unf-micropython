# =============================================================================
# File    : calibrate_hx711.py
# Purpose : Calibrate HX711 + load cell and observe live weight
# =============================================================================

from lib.sensors.hx711_driver import HX711
import s3_const as CFG
import time

# Known calibration weight in grams
KNOWN_GRAMS = 2000.0

# Tunable parameters
TARE_DELAY_SEC       = 1.0
SETTLE_DELAY_SEC     = 1.0
AVG_SAMPLES_CAL      = 50
AVG_SAMPLES_VERIFY   = 40
AVG_SAMPLES_LOG      = 20
LOG_INTERVAL_SEC     = 2.0

# Sanity thresholds (rough, but prevent crazy calibrations)
MIN_ABS_RAW_FOR_2KG  = 1000.0   # if |raw_avg| is below this, abort
MAX_VERIFY_FACTOR    = 3.0      # verify must be within [known/3, known*3]
MAX_CORRECTION_FACTOR = 2.0     # fine correction must be in [0.5, 2.0]


def calibrate_hx711():
    hx = HX711(CFG.DT_PIN, CFG.SCK_PIN)
    hx.set_scale(1.0)

    print("")
    print("===========================================")
    print(" HX711 Calibration Tool")
    print("===========================================\n")

    # -------------------------------------------------------------------------
    # Step 1: Tare
    # -------------------------------------------------------------------------
    print("Step 1/3: Remove ALL weight from the scale.")
    print("          Tare will start in %.1f second(s)..." % TARE_DELAY_SEC)
    time.sleep(TARE_DELAY_SEC)

    hx.tare()
    print("Tare complete. Offset set to:", hx.OFFSET, "\n")

    # -------------------------------------------------------------------------
    # Step 2: Place reference weight
    # -------------------------------------------------------------------------
    prompt = (
        "Step 2/3: Place %.1f g on the scale and press Enter to continue..."
        % KNOWN_GRAMS
    )
    try:
        input(prompt)
    except KeyboardInterrupt:
        print("\nCalibration aborted by user.")
        return None

    time.sleep(SETTLE_DELAY_SEC)

    # Debug: immediate small-sample reading
    instant_raw = hx.get_value(times=10)
    print("\nImmediate raw delta after Enter: %0.3f" % instant_raw)

    print("Sampling raw values for stability:")
    for i in range(5):
        sample = hx.get_value(times=5)
        print("  Sample %d: %0.3f" % (i + 1, sample))
        time.sleep(0.2)

    # -------------------------------------------------------------------------
    # Step 2b: Large averaging for calibration
    # -------------------------------------------------------------------------
    raw_avg = hx.get_value(times=AVG_SAMPLES_CAL)
    print("\nAverage raw delta for %.1f g = %0.6f" % (KNOWN_GRAMS, raw_avg))

    # Sanity check: raw must be "large enough"
    if abs(raw_avg) < MIN_ABS_RAW_FOR_2KG:
        print("\nERROR: |raw_avg| is too small for %.1f g (|%0.3f| < %0.1f)." %
              (KNOWN_GRAMS, raw_avg, MIN_ABS_RAW_FOR_2KG))
        print("       This usually means the weight was not fully on the scale,")
        print("       the scale moved, or there is a wiring/mounting issue.")
        print("       Fix the hardware/setup and try again.")
        return None

    scale_initial = raw_avg / KNOWN_GRAMS
    print("Initial SCALE factor =", scale_initial)

    hx.set_scale(scale_initial)
    time.sleep(0.5)

    # -------------------------------------------------------------------------
    # Step 2c: Verification
    # -------------------------------------------------------------------------
    verify = hx.get_units(times=AVG_SAMPLES_VERIFY)
    print(
        "\nVerification with %.1f g: %.3f grams"
        % (KNOWN_GRAMS, verify)
    )

    # Sanity check: verify must be within [known/MAX, known*MAX]
    if verify <= 0 or verify < KNOWN_GRAMS / MAX_VERIFY_FACTOR or verify > KNOWN_GRAMS * MAX_VERIFY_FACTOR:
        print("\nWARNING: Verification reading %.3f g is not in reasonable range." % verify)
        print("         Skipping fine correction. Using initial scale only.")
        scale_final = scale_initial
    else:
        # Fine correction
        correction = KNOWN_GRAMS / verify
        if correction < 1.0 / MAX_CORRECTION_FACTOR or correction > MAX_CORRECTION_FACTOR:
            print("\nWARNING: Correction factor %.3f is too extreme." % correction)
            print("         Skipping fine correction. Using initial scale only.")
            scale_final = scale_initial
        else:
            scale_final = scale_initial * correction
            print("Fine-corrected SCALE factor =", scale_final)

            hx.set_scale(scale_final)
            time.sleep(0.5)
            verify2 = hx.get_units(times=AVG_SAMPLES_VERIFY)
            print("Re-check with corrected scale: %.3f grams" % verify2)

    # -------------------------------------------------------------------------
    # Final result
    # -------------------------------------------------------------------------
    print("\n===========================================")
    print(" Calibration complete (no fatal errors).")
    print("===========================================\n")
    print("👉 Put this into s3_const.py:\n")
    print("    HX711_SCALE = %0.9f" % scale_final)
    print("\n(You can round it to e.g. 6 decimal places if you like.)\n")

    return hx, scale_final


def continuous_logging(hx):
    print("===========================================")
    print(" Step 3/3: Continuous logging started.")
    print(" Remove/add weight and observe readings.")
    print(" Logging weight every %.1f second(s)." % LOG_INTERVAL_SEC)
    print(" Press CTRL+C to stop.\n")
    print("===========================================\n")

    i = 0
    while True:
        try:
            grams = hx.get_units(times=AVG_SAMPLES_LOG)
            print("[%04d] Weight = %0.2f g" % (i, grams))
            i += 1
            time.sleep(LOG_INTERVAL_SEC)
        except KeyboardInterrupt:
            print("\nLogging stopped by user.")
            break
        except Exception as e:
            print("Error during logging:", e)
            time.sleep(LOG_INTERVAL_SEC)


def main():
    result = calibrate_hx711()
    if result is None:
        return

    hx, _scale = result
    continuous_logging(hx)


if __name__ == "__main__":
    main()
