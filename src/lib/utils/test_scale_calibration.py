from lib.sensors.hx711_driver import HX711
import s3_const as CFG
import time

hx = HX711(CFG.DT_PIN, CFG.SCK_PIN)


# 1. Start with SCALE = 1 so we can see the raw delta
hx.set_scale(1)

print("Remove all weight, taring...")
hx.tare()
time.sleep(2)

input("Now put a known weight (e.g. 2000 g) on the scale and press Enter...")

# 2. Read the raw delta for this known weight
#raw = hx.get_value(times=15)   # this is (reading - OFFSET) with SCALE=1
raw = hx.get_value(times=15)   # this is (reading - OFFSET) with SCALE=1
print("Raw delta for known weight:", raw)

known_grams = 2000.0  # <-- your known weight in grams, change if needed
scale = raw / known_grams
print("Calculated SCALE factor =", scale)

# 3. Set this SCALE and check
hx.set_scale(scale)
#check = hx.get_units(times=15)
check = hx.get_units(times=15)
print("Check reading (grams) =", check)

