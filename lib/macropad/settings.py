# /lib/macropad/settings.py
# Loads settings as one live dict: built-in defaults <- default.js <- settings.js.
# Each file may instead be the older .json form (same JSON inside; see jsfile.py); the .js
# file wins if both are there. The device saves settings.js.
# The CONFIG and LIGHTS menus edit this same dict, so changes take effect immediately.
# Problems are collected in ERRORS (shown on the OLED at boot) and the default is used.

import json
import os
from macropad.lights import SCENES, COLOR_NAMES
from macropad import gestures, jsfile

SETTINGS_FILE = "settings.js"
SETTINGS_FILES = (SETTINGS_FILE, "settings.json")
DEFAULTS_FILES = ("default.js", "default.json")
SETTINGS_NOTE = "MP1 macropad settings. Edit with settings_editor.html, or on the device (Settings menu)."
JS_NAME = "MP1_SETTINGS"

BUILTIN_DEFAULTS = {
    # Encoder button
    "long_press_duration": 1.5,
    "medium_press_duration": 0.4,
    "hold_turn_threshold": 5,
    "hold_gesture_min_duration": 0.3,
    "button_debounce": 0.03,        # seconds the button must be steady before a press/release counts
    # Encoder gestures (Settings -> GESTURES); values are names from gestures.py
    "multi_click_time": 0.25,       # max gap between clicks of a double/triple click
    "gesture_double": "layer_keys",
    "gesture_triple": "timer",
    "gesture_hold_cw": "jiggle",
    "gesture_hold_ccw": "secret",
    "gesture_click_hold_cw": "stopwatch",     # click, then hold + turn
    "gesture_click_hold_ccw": "none",
    # Timeouts
    "secret_timeout": 15.0,
    "menu1_timeout": 5.0,           # layers menu
    "menu2_timeout": 10.0,          # settings menu
    # Encoder rotation
    "encoder_speed_fast": 0.03,
    "encoder_speed_medium": 0.08,
    "encoder_multiplier_fast": 4,
    "encoder_multiplier_medium": 2,
    # Keys with "repeat": true (keymap.js)
    "repeat_delay": 0.5,            # hold this long before repeating starts
    "repeat_rate": 10,              # repeats per second
    # Keys with "confirm": true (keymap.js)
    "confirm_time": 0.6,            # hold this long to fire
    "encoder_reverse": False,       # flip if the knob turns the wrong way everywhere
    "encoder_press_guard": 0.06,    # ignore knob movement this long after the button contact
                                    # changes (pressing rocks the shaft); 0 = off
    "encoder_divisor": 4,           # pin steps per click: 4 for most encoders, 2 if only every
                                    # other click registers (restart to apply)
    # Display
    "display_layer_flash_delay": 0.6,
    "boot_debug": False,            # start-up: show the console text instead of boot.bmp
    "boot_screen_seconds": 1.5,     # keep the start-up screen up at least this long (0 = no wait)
    "screen_dim_minutes": 5,        # dim the OLED after this long idle (0 = never)
    "screen_off_minutes": 20,       # turn the OLED off after this long idle (0 = never)
    "screen_dim_level": 0.1,        # brightness while dimmed (0.05-1)
    "screen_off_leds": True,        # LED strip goes dark with the screen
    "caps_box": True,               # white CAPS box in the top bar while Caps Lock is on
    "caps_flash": True,             # flash CAPS ON / CAPS OFF when it changes
    "menu_roll_time": 0.15,         # how long a menu takes to roll one item (0 = no animation)
    "menu_roll_steps": 4,           # frames drawn during each roll (more = smoother)
    "display_jiggle_blink_rate": 2,
    "jiggle_display_flash_duration": 1.0,
    # Mouse jiggle
    "jiggle_min_interval": 25,
    "jiggle_max_interval": 40,
    "jiggle_max_pixels": 1,
    # RGB LED strip add-on (led_count 0 = not fitted)
    "led_count": 0,
    "led_scene": "reactive",        # every layer's scene, unless the layer has its own lights
    "led_color1": "INDIGO",
    "led_color2": "VERMILION",
    "led_brightness": 0.25,
    "led_speed": 4,                 # 1 (slow) - 10 (fast)
    # Buzzer add-on
    "buzzer": "none",               # "none", "passive" (tones) or "active" (on/off)
    "buzzer_active_low": False,     # active buzzers wired to sound when the pin is low
    "buzzer_volume": 1.0,           # passive only, 0.1 - 1.0
    "sound_startup": True,
    "sound_keys": False,            # click on key press
    "sound_layers": False,          # tone on layer change
    # Other
    "main_loop_delay": 0.001,
    "loop_stats": False,            # print main-loop timing to the serial console every 5 s
    "watchdog": True,               # restart automatically if the macropad ever freezes
    "debug_gestures": False,        # print every encoder-button press to the serial console
    "about_url": "https://mp1-help.theornerymaker.com",
    "keymapper_url": "https://mp1-configurator.theornerymaker.com",
}

CHOICES = {
    "encoder_divisor": (1, 2, 4),
    "buzzer": ("none", "passive", "active"),
    "led_scene": SCENES,
    "led_color1": COLOR_NAMES,
    "led_color2": COLOR_NAMES,
    "gesture_double": gestures.NAMES,
    "gesture_triple": gestures.NAMES,
    "gesture_hold_cw": gestures.NAMES,
    "gesture_hold_ccw": gestures.NAMES,
    "gesture_click_hold_cw": gestures.NAMES,
    "gesture_click_hold_ccw": gestures.NAMES,
}

ERRORS = []


def _type_ok(key, value, default):
    if key in CHOICES:
        return value in CHOICES[key]
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0
    return isinstance(value, type(default))


def _read(path, report=True):
    def problem(message):
        if report:
            ERRORS.append(message)

    try:
        data = jsfile.load(path)
    except OSError:
        return {}                              # missing file: defaults are fine
    except ValueError:
        problem(path + " is not valid JSON; using defaults")
        return {}
    if not isinstance(data, dict):
        problem(path + " should be {...}; using defaults")
        return {}

    good = {}
    for key, value in data.items():
        if key.startswith("gesture_"):
            if value == "layer_menu":
                value = "layer_keys"           # LAYER MENU was replaced by LAYER KEYS
            elif value in gestures.REMOVED:
                value = "none"                 # LAST / NEXT / PREV LAYER were removed
        if key == "led_scene" and value == "layer":
            value = "static"                   # PER LAYER was removed: layer lights always win now
        if key not in BUILTIN_DEFAULTS:
            problem("{}: unknown setting {}".format(path, key))
        elif not _type_ok(key, value, BUILTIN_DEFAULTS[key]):
            problem("{}: bad value for {}".format(path, key))
        else:
            good[key] = value
    return good


def defaults(report=False):
    values = dict(BUILTIN_DEFAULTS)
    values.update(_read(jsfile.pick(*DEFAULTS_FILES), report))
    return values


def load():
    values = defaults(report=True)
    values.update(_read(jsfile.pick(*SETTINGS_FILES)))
    if values["jiggle_min_interval"] > values["jiggle_max_interval"]:
        ERRORS.append("jiggle_min_interval is above jiggle_max_interval; swapped")
        values["jiggle_min_interval"], values["jiggle_max_interval"] = (
            values["jiggle_max_interval"], values["jiggle_min_interval"])
    values["led_brightness"] = min(1.0, values["led_brightness"])
    values["led_count"] = int(values["led_count"])
    for message in ERRORS:
        print("SETTINGS ERROR:", message)
    return values


def to_text(values):
    """One setting per line, sorted, so the file stays easy to edit by hand."""
    lines = ['  {}: {}'.format(json.dumps(k), json.dumps(values[k])) for k in sorted(values)]
    return "{\n" + ",\n".join(lines) + "\n}\n"


def save(values):
    """Write settings.js safely: write a temp file, keep the old file as settings.js.bak,
    then swap. Fails (returns False) while the USB drive is mounted."""
    temp, backup = SETTINGS_FILE + ".tmp", SETTINGS_FILE + ".bak"
    try:
        with open(temp, "w") as f:
            f.write(jsfile.wrap(JS_NAME, to_text(values), SETTINGS_NOTE))
        try:
            os.remove(backup)
        except OSError:
            pass
        try:
            os.rename(SETTINGS_FILE, backup)
        except OSError:
            pass                                # no existing file yet
        os.rename(temp, SETTINGS_FILE)
        return True
    except Exception as e:
        print("Could not save", SETTINGS_FILE, "-", e)
        try:
            os.remove(temp)
        except OSError:
            pass
        return False
