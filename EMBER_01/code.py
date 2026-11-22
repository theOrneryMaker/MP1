# code.py - MP1 Ember 01 (being built: step 5 = MP1 Link).
# Hardware set-up, the keymap, then the main loop in ember/app.py.

import gc
import sys
import busio
import digitalio
import displayio
import keypad
import rotaryio
import usb_hid

# The keymap first, while memory is in one piece; its loader is let go afterwards.
from ember import keymap
km = keymap.load()
errors = list(keymap.ERRORS)
del keymap
from ember import forget
forget("keymap")
gc.collect()

from i2cdisplaybus import I2CDisplayBus
from adafruit_displayio_ssd1306 import SSD1306
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS
from adafruit_hid.mouse import Mouse
from adafruit_hid.consumer_control import ConsumerControl
from ember import pins, settings
from ember.screen import Screen
from ember.actions import Actions
from ember.app import App

cfg = settings.load()
errors += settings.ERRORS
wiring = pins.load()
errors += wiring.errors
displayio.release_displays()
i2c = busio.I2C(wiring.I2C_SCL, wiring.I2C_SDA, frequency=wiring.I2C_FREQUENCY)
display = SSD1306(I2CDisplayBus(i2c, device_address=wiring.OLED_ADDRESS), width=128, height=64)

kbd = Keyboard(usb_hid.devices)
actions = Actions(kbd, KeyboardLayoutUS(kbd), ConsumerControl(usb_hid.devices), Mouse(usb_hid.devices))
keys = keypad.KeyMatrix(row_pins=wiring.ROWS, column_pins=wiring.COLS, columns_to_anodes=True)
encoder = rotaryio.IncrementalEncoder(wiring.ENC_A, wiring.ENC_B, divisor=wiring.ENCODER_DIVISOR)
button = digitalio.DigitalInOut(wiring.ENC_SW)
button.switch_to_input(pull=digitalio.Pull.UP)
# Lights and sound (FIRMWARE_04's modules: they read these names; App keeps them in step with the settings)
hw = {"led_count": wiring.LED_COUNT, "led_level": cfg["light_level"], "led_scene": cfg["light_scene"], "led_speed": 3,
      "buzzer": wiring.BUZZER_TYPE, "buzzer_active_low": wiring.BUZZER_ACTIVE_LOW, "buzzer_level": cfg["sound_level"]}
from ember.app import NoAddon
lights = sound = NoAddon()
if wiring.LED_COUNT:
    from ember.lights import Lights
    lights = Lights(hw, wiring.LED_STRIP_PIN)
    if lights.pixels is None:
        errors.append(lights.error)
        lights = NoAddon()
if wiring.BUZZER_TYPE != "none":
    from ember.sound import Sound
    sound = Sound(hw, wiring.BUZZER_PIN)
    if sound.error:
        errors.append(sound.error)
        sound = NoAddon()
del wiring, pins, settings
forget("pins")
forget("settings")
gc.collect()

import usb_cdc
app = App(km, cfg, Screen(display), actions, keys, encoder, button, display, errors, lights, sound, hw, usb_cdc.data)
try:
    app.run()
except Exception as e:                  # a crash: let go of every key, keep the details, show them, restart
    import traceback
    import time
    text = "".join(traceback.format_exception(e))
    print(text)
    try:
        actions.release_all()
    except Exception:
        pass
    try:
        with open("/crash.txt", "a") as f:
            f.write("--- {}\n{}\n".format(time.monotonic(), text))
    except OSError:
        pass
    try:
        lines = [l.strip() for l in text.splitlines() if l.strip()][-4:]
        app.screen.show_list("CRASHED", lines + ["Restarting in 10 s"])
        app.screen.refresh()
    except Exception:
        pass
    time.sleep(10)
    import supervisor
    supervisor.reload()
