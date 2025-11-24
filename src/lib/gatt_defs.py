# =============================================================================
# Project  : Unforgotten – ESP BLE Scale
# File     : gatt_defs.py
# Version  : 1.4.0
# Author   : you
# Summary  : GATT schema for gatts_register_services
# Behavior : Simple tuples; notify TX, write RX for 3 topics (weight/fused/gps)
# Purpose  : Central BLE attributes
# Style    : Minimal, explicit
# =============================================================================

import bluetooth
from lib.common_const import FLAG_READ, FLAG_NOTIFY, FLAG_WRITE, FLAG_WRITE_NO_RESPONSE

GATT_SCHEMA_VERSION = "1.4.0"

WEIGHT_SERVICE_UUID = bluetooth.UUID("00001234-0000-1000-8000-00805f9b34fb")

WEIGHT_CHAR_TX = (bluetooth.UUID("00002345-0000-1000-8000-00805f9b34fb"), FLAG_READ | FLAG_NOTIFY)
WEIGHT_CHAR_RX = (bluetooth.UUID("00003345-0000-1000-8000-00805f9b34fb"), FLAG_WRITE | FLAG_WRITE_NO_RESPONSE)

FUSED_CHAR_TX  = (bluetooth.UUID("00004345-0000-1000-8000-00805f9b34fb"), FLAG_READ | FLAG_NOTIFY)
FUSED_CHAR_RX  = (bluetooth.UUID("00005345-0000-1000-8000-00805f9b34fb"), FLAG_WRITE | FLAG_WRITE_NO_RESPONSE)

GPS_CHAR_TX    = (bluetooth.UUID("00006345-0000-1000-8000-00805f9b34fb"), FLAG_READ | FLAG_NOTIFY)
GPS_CHAR_RX    = (bluetooth.UUID("00007345-0000-1000-8000-00805f9b34fb"), FLAG_WRITE | FLAG_WRITE_NO_RESPONSE)

WEIGHT_SERVICE = (
    WEIGHT_SERVICE_UUID,
    (WEIGHT_CHAR_TX, WEIGHT_CHAR_RX, FUSED_CHAR_TX, FUSED_CHAR_RX, GPS_CHAR_TX, GPS_CHAR_RX),
)
