# ember/settings.py - the pad's settings (NOTES/PAD_CORE.md: 64 in FIRMWARE_04, 20 in Ember).
# settings.json: {"ember": "settings", ...}. Anything missing or wrong uses its default (and is
# reported); a FIRMWARE_04 settings.json is ignored (the page converts it).

import json

PATH = "/settings.json"

# name: (default, allowed values: a tuple of choices or (low, high), or ("bits", n): n "1" / "0" switches)
# sounds: "1001" = where the pad beeps: SOUND_PARTS, in that order (1 = on)
SOUND_PARTS = ("Boot", "Layers", "Keys", "Alarms")
OLD_SOUNDS = {"off": "0001", "keys": "0011", "everything": "1111"}     # (the earlier off / keys / everything)
SETTINGS = {
    "click_single": ("layer_keys", ("layer_picker", "layer_keys", "layer_cards")),     # (gestures.SINGLE_CLICK: layer lists only)
    "click_double": ("spotify", None),               # encoder clicks: one of gestures.NAMES
    "click_triple": ("home_layer", None),
    "hold_turn_right": ("jiggle", None),
    "hold_turn_left": ("secret", None),
    "encoder_reverse": (False, (False, True)),
    "repeat_speed": ("normal", ("slow", "normal", "fast")),
    "type_speed": ("normal", ("normal", "careful", "slow")),     # text and macros (a key can have its own)
    "key_lines": ("grid", ("grid", "shelves", "boxes", "dotted")),
    "screen_dim_minutes": (5, (0, 120)),
    "screen_off_minutes": (20, (0, 240)),
    "idle_screen": ("dim", ("dim", "clock")),        # at "Dim after": dim, or the bouncing clock (extras.Saver)
    "lock_boxes": (True, (False, True)),
    "secret_lock_seconds": (15, (0, 600)),
    "light_scene": ("reactive", None),               # lights.SCENES (piece 5)
    "light_color1": ("WHITE", None),
    "light_color2": ("GREEN", None),
    "light_level": (4, (1, 10)),
    "lights_asleep": (False, (False, True)),
    "sound_level": (4, (1, 10)),
    "sounds": ("1001", ("bits", 4)),                 # Boot, Layers, Keys, Alarms (user, 2026-11-21)
    "jiggle_at_start": (False, (False, True)),
}
# Hardware overrides: typed into settings.json by hand (for a hand-wired pad), never shown in the pad's menu or the
# page, kept when the pad saves its settings. "led_count": 0-60 replaces wiring.json's LED count (default: none).
OVERRIDES = {"led_count": (0, 60)}
ERRORS = []


def _ok(name, value):
    default, allowed = SETTINGS[name]
    if allowed is None:
        return isinstance(value, str)
    if allowed[0] == "bits":
        return isinstance(value, str) and len(value) == allowed[1] and all(c in "01" for c in value)
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool) and allowed[0] <= value <= allowed[1]
    return value in allowed


def load():
    cfg = {name: d for name, (d, _) in SETTINGS.items()}
    try:
        with open(PATH) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return cfg
    if not isinstance(data, dict) or data.get("ember") != "settings":
        return cfg
    for name, value in data.items():
        if name == "ember":
            continue
        if name == "sounds" and value in OLD_SOUNDS:
            value = OLD_SOUNDS[value]
        if name in OVERRIDES:
            low, high = OVERRIDES[name]
            if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high:
                cfg[name] = value
            else:
                ERRORS.append("settings.json: {} should be {}-{}".format(name, low, high))
        elif name not in SETTINGS:
            ERRORS.append("settings.json: unknown setting {}".format(name))
        elif not _ok(name, value):
            ERRORS.append("settings.json: {} can't be {!r}".format(name, value))
        else:
            cfg[name] = value
    return cfg


def save(cfg):
    """Write settings.json (only what differs from the defaults). False if the drive can't be written."""
    out = {"ember": "settings"}
    for name, (d, _) in SETTINGS.items():
        if cfg.get(name, d) != d:
            out[name] = cfg[name]
    for name in OVERRIDES:
        if name in cfg:
            out[name] = cfg[name]
    try:
        with open(PATH + ".new", "w") as f:
            json.dump(out, f)
        import os
        try:
            os.remove(PATH)
        except OSError:
            pass
        os.rename(PATH + ".new", PATH)
        return True
    except OSError:
        return False
