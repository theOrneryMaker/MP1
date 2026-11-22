#!/bin/bash
# Build MP1 Ember's custom CircuitPython for the YD-RP2040, with the whole pad program frozen in:
#   wsl -d Ubuntu-24.04 -u root -- bash "/mnt/c/PATH/TO/THE/PROJECT/tools/cpbuild/build.sh" EMBER_01
# Needs setup.sh run once (shared with the original line: /opt/cp). Frozen: lib/ember (all of it),
# adafruit_hid, neopixel and adafruit_displayio_ssd1306. The UF2 lands in <EMBER_NN>/BUILD_FROZEN/firmware/.
# Its own board folder and staging folder, so the original line's build (MP1 ORIGINAL) is untouched.
set -euo pipefail
FW=${1:-EMBER_01}
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"     # (the project folder: two up from here)
BOARD=mp1_ember_yd_rp2040
CP=/opt/cp
export PATH=/opt/arm-gnu-toolchain-15.2.rel1-x86_64-arm-none-eabi/bin:$PATH
. /opt/cpvenv/bin/activate

# the board: the stock YD-RP2040 one, renamed, with the frozen code
B=$CP/ports/raspberrypi/boards/$BOARD
rm -rf "$B"
cp -r $CP/ports/raspberrypi/boards/vcc_gnd_yd_rp2040 "$B"
sed -i 's/#define MICROPY_HW_BOARD_NAME .*/#define MICROPY_HW_BOARD_NAME "MP1 Ember (YD-RP2040)"/' "$B/mpconfigboard.h"
cat >> "$B/mpconfigboard.mk" <<'MK'

# MP1: built-in modules the MP1 doesn't use, left out (room for frozen code; approved 2026-11-14)
CIRCUITPY_ULAB = 0
CIRCUITPY__EVE = 0
CIRCUITPY_RGBMATRIX = 0
CIRCUITPY_SHARPDISPLAY = 0
CIRCUITPY_EPAPERDISPLAY = 0
CIRCUITPY_AURORA_EPAPER = 0
CIRCUITPY_PARALLELDISPLAYBUS = 0
CIRCUITPY_IMAGECAPTURE = 0
CIRCUITPY_GIFIO = 0
CIRCUITPY_JPEGIO = 0
CIRCUITPY_QRIO = 0
CIRCUITPY_SDCARDIO = 0
CIRCUITPY_FLOPPYIO = 0
CIRCUITPY_WIZNET = 0
CIRCUITPY_BLEIO_HCI = 0
CIRCUITPY_USB_HOST = 0
CIRCUITPY_USB_VIDEO = 0
CIRCUITPY_USB_AUDIO = 0
CIRCUITPY_USB_MIDI = 0
CIRCUITPY_MSGPACK = 0
CIRCUITPY_ZLIB = 0
CIRCUITPY_HASHLIB = 0
CIRCUITPY_CODEOP = 0
CIRCUITPY_GETPASS = 0
CIRCUITPY_LOCALE = 0
CIRCUITPY_MEMORYMAP = 0
CIRCUITPY_BITMAPFILTER = 0
CIRCUITPY_LVFONTIO = 0
CIRCUITPY_KEYPAD_DEMUX = 0
CIRCUITPY_VECTORIO = 0
CIRCUITPY_AUDIOBUSIO = 0
CIRCUITPY_AUDIOCORE = 0
CIRCUITPY_AUDIOMIXER = 0
CIRCUITPY_AUDIOMP3 = 0
CIRCUITPY_AUDIOPWMIO = 0
CIRCUITPY_AUDIODELAYS = 0
CIRCUITPY_AUDIOFILTERS = 0
CIRCUITPY_AUDIOFREEVERB = 0
CIRCUITPY_AUDIOEFFECTS = 0
CIRCUITPY_AUDIOSPEED = 0
CIRCUITPY_AUDIOFILEWRITER = 0
CIRCUITPY_AUDIOI2SIN = 0
CIRCUITPY_SYNTHIO = 0
CIRCUITPY_ALARM = 0
CIRCUITPY_TOUCHIO = 0
CIRCUITPY_COUNTIO = 0
CIRCUITPY_PULSEIO = 0
CIRCUITPY_ONEWIREIO = 0
CIRCUITPY_ANALOGBUFIO = 0
CIRCUITPY_I2CTARGET = 0
# (bitbangio stays: busio I2C on the RP2040 uses it inside)

# Ember: the pad program and the libraries it uses, frozen (run from flash: less RAM)
FROZEN_MPY_DIRS += /opt/emberfrozen
FROZEN_MPY_DIRS += $(TOP)/frozen/Adafruit_CircuitPython_HID
FROZEN_MPY_DIRS += $(TOP)/frozen/Adafruit_CircuitPython_NeoPixel
FROZEN_MPY_DIRS += $(TOP)/frozen/Adafruit_CircuitPython_DisplayIO_SSD1306
MK

# the Ember modules, staged on the Linux disk
rm -rf /opt/emberfrozen
mkdir -p /opt/emberfrozen/ember
cp "$ROOT/$FW/lib/ember/"*.py /opt/emberfrozen/ember/

rm -rf $CP/ports/raspberrypi/build-$BOARD     # (always clean: switched-off modules must leave the module table)
make -C $CP/ports/raspberrypi BOARD=$BOARD -j"$(nproc)" 2>&1 | tail -15
OUT="$ROOT/$FW/BUILD_FROZEN/firmware"
mkdir -p "$OUT"
cp $CP/ports/raspberrypi/build-$BOARD/firmware.uf2 "$OUT/$BOARD.uf2"
ls -l "$OUT/$BOARD.uf2"
echo BUILD DONE
