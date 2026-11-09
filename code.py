# code.py – MP1 macropad: hardware setup, then hand off to the app loop.
# Behavior lives in lib/macropad/app.py; keys in keymap.js; device settings in settings.js.

import gc
import time
import board
import busio
import digitalio
import displayio
import keypad
import rotaryio
import usb_hid

# Load the app first, while memory is emptiest: CircuitPython compiles each .py file in
# RAM as it loads, and the app is the largest part.
from macropad.app import App
gc.collect()

from i2cdisplaybus import I2CDisplayBus
from adafruit_displayio_ssd1306 import SSD1306
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse
from adafruit_hid.consumer_control import ConsumerControl

import wiring
import keymap
from macropad import settings
from macropad.display import Screen, show_splash
from macropad.actions import Actions
from macropad.lights import Lights
from macropad.sound import Sound
gc.collect()

cfg = settings.load()

# OLED
displayio.release_displays()
i2c = busio.I2C(wiring.I2C_SCL, wiring.I2C_SDA, frequency=wiring.I2C_FREQUENCY)
display = SSD1306(I2CDisplayBus(i2c, device_address=wiring.OLED_ADDRESS), width=128, height=64)

# Start-up screen: boot.bmp, or (boot_debug on) the console text with the start-up messages
boot_started = time.monotonic()
splash = None if cfg["boot_debug"] else show_splash(display)

# Inputs / LED
led = digitalio.DigitalInOut(board.LED)
led.switch_to_output()
button = digitalio.DigitalInOut(wiring.ENC_SW)
button.switch_to_input(pull=digitalio.Pull.UP)

# Optional add-ons: if one fails to start, it's reported and the macropad carries on without it
lights = Lights(cfg, wiring.LED_STRIP_PIN)
sound = Sound(cfg, wiring.BUZZER_PIN)
hardware_errors = [part.error for part in (lights, sound) if part.error]

# USB HID
kbd = Keyboard(usb_hid.devices)
actions = Actions(kbd, KeyboardLayoutUS(kbd), ConsumerControl(usb_hid.devices), Mouse(usb_hid.devices))

gc.collect()
print("Free memory at start-up:", gc.mem_free(), "bytes")

# Keep the start-up screen up for at least boot_screen_seconds
while time.monotonic() - boot_started < cfg["boot_screen_seconds"]:
    time.sleep(0.02)
splash = None

App(
    keymap=keymap,
    cfg=cfg,
    errors=keymap.ERRORS + settings.ERRORS + hardware_errors,
    screen=Screen(display),
    actions=actions,
    keys=keypad.KeyMatrix(row_pins=wiring.ROWS, column_pins=wiring.COLS, columns_to_anodes=True),
    encoder=rotaryio.IncrementalEncoder(wiring.ENC_A, wiring.ENC_B, divisor=cfg["encoder_divisor"]),
    button=button,
    led=led,
    lights=lights,
    sound_out=sound,
).run()
