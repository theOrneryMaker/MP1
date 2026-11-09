# boot.py – Hold the encoder button during the first 3 seconds after power-up to
# expose the CIRCUITPY USB drive (for editing keymap.json). Otherwise the drive is
# hidden, which also lets the firmware save settings.json from the CONFIG menu.

import time
import digitalio
import storage
import wiring

button = digitalio.DigitalInOut(wiring.ENC_SW)
button.switch_to_input(pull=digitalio.Pull.UP)

deadline = time.monotonic() + 3
pressed = False
while time.monotonic() < deadline and not pressed:
    pressed = not button.value
    time.sleep(0.1)

if pressed:
    print("Button pressed, mounting USB drive")
else:
    print("Button not pressed, USB drive disabled")
    storage.disable_usb_drive()
