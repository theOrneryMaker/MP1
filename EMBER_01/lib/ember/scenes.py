# ember/scenes.py (from FIRMWARE_04)
# Drop-in lighting scenes: data files in the drive's scenes/ folder (scenes/NAME.mp1scene.json).
# The file name is the scene's name: ocean.mp1scene.json is OCEAN (up to 10 letters, numbers,
# spaces, - or _).
# A scene is a list of steps, never code, so a shared scene file can only ever change colors.
# This module is only loaded at start-up (to list and check the files) and for a moment when a
# drop-in scene becomes the active scene (to read its steps); lights.py plays them.
#
# {
#   "mp1_scene": 1,
#   "loop": true,                           (optional, default true; false = stay on the last step)
#   "steps": [                              1 to 32 steps, played in order
#     {"color": "INDIGO", "hold": 2, "fade": 3},          fade into the color, then hold it (seconds)
#     {"color": "COLOR 1", "hold": 1},                    COLOR 1 / COLOR 2: the LIGHTS (or layer) colors
#     {"leds": ["AMBER", "ORANGE"], "hold": 4, "fade": 2} a color per LED, repeated along the strip
#   ],
#   "on_key": [{"color": "WHITE"}, {"color": "COLOR 1", "fade": 0.4}]
#                                           (optional: played on each key press, then back)
# }
# Colors: a palette name (RED, WARM_WHITE or WARM WHITE...), "#RRGGBB", OFF, COLOR 1, COLOR 2.
# Times are at SPEED 5: the SPEED setting makes them faster or slower, as for the built-in scenes.

import json

SCENE_DIR = "scenes"
SUFFIX = ".mp1scene.json"
MAX_NAME = 10
MAX_STEPS = 32
MAX_LEDS = 60
MAX_SECONDS = 3600
NAME_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 _-"


class SceneError(Exception):
    pass


def _order(name):
    """A-Z, then 0-9 (letters before numbers), ignoring case: the same as drop-in layers."""
    return [(1 if c.isdigit() else 0, c) for c in name.upper()]


def _files():
    import os
    try:
        names = os.listdir(SCENE_DIR)
    except OSError:
        return []
    names = [n for n in names if n.lower().endswith(SUFFIX) and not n.startswith(".")]
    names.sort(key=_order)
    return names


def _seconds(step, field, where):
    value = step.get(field, 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= MAX_SECONDS:
        raise SceneError("{}: {} should be 0-{} seconds".format(where, field, MAX_SECONDS))
    return int(value * 1000 + 0.5)


def _color(value, where, color):
    """(r, g, b), or 1 / 2 for COLOR 1 / COLOR 2."""
    if isinstance(value, str):
        name = value.strip().upper().replace(" ", "_")
        if name == "OFF":
            return (0, 0, 0)
        if name in ("COLOR_1", "COLOR1"):
            return 1
        if name in ("COLOR_2", "COLOR2"):
            return 2
        rgb = color(name) if not name.startswith("#") else color(value.strip())
        if rgb is not None:
            return rgb
    raise SceneError("{}: unknown color {}".format(where, value))


def _steps(steps, where, color):
    if not isinstance(steps, list) or not steps:
        raise SceneError(where + " should be a list of steps")
    if len(steps) > MAX_STEPS:
        raise SceneError("{} has {} steps; the most is {}".format(where, len(steps), MAX_STEPS))
    out = []
    for i, step in enumerate(steps):
        at = "{} step {}".format(where, i + 1)
        if not isinstance(step, dict):
            raise SceneError(at + " should be {...}")
        for field in step:
            if field not in ("color", "leds", "hold", "fade"):
                raise SceneError("{}: unknown field {}".format(at, field))
        if ("color" in step) == ("leds" in step):
            raise SceneError(at + " needs a color or leds (one of them)")
        if "color" in step:
            value = _color(step["color"], at, color)
        else:
            leds = step["leds"]
            if not isinstance(leds, list) or not 0 < len(leds) <= MAX_LEDS:
                raise SceneError("{}: leds should be a list of 1-{} colors".format(at, MAX_LEDS))
            value = [_color(v, at, color) for v in leds]
        out.append((value, _seconds(step, "hold", at), _seconds(step, "fade", at)))
    return tuple(out)


def read(path, color):
    """(loop, steps, on_key steps or ()) from a scene file. SceneError if it's not valid.
    color = lights.color (passed in: this module doesn't import lights.py)."""
    try:
        with open(path, "rb") as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise SceneError("isn't valid JSON")
    if not isinstance(data, dict) or "steps" not in data:
        raise SceneError("isn't an MP1 scene file")
    for field in data:
        if field not in ("mp1_scene", "name", "loop", "steps", "on_key"):   # name: ignored (older files)
            raise SceneError("unknown field " + field)
    loop = data.get("loop", True)
    if not isinstance(loop, bool):
        raise SceneError("loop should be true or false")
    steps = _steps(data["steps"], "steps", color)
    keys = _steps(data["on_key"], "on_key", color) if data.get("on_key") is not None else ()
    if loop and not sum(s[1] + s[2] for s in steps):
        raise SceneError("a looping scene needs some hold or fade time")
    return loop, steps, keys


def name_of(fname):
    """The scene name a file gives (lowercase, as settings.json and keymap.json store it)."""
    name = fname[:-len(SUFFIX)].strip().upper()
    if not name or len(name) > MAX_NAME or any(c not in NAME_CHARS for c in name):
        raise SceneError("the file name should be 1-{} letters, numbers, spaces, - or _, then {}".format(
            MAX_NAME, SUFFIX))
    return name.lower()


def scan(taken, color):
    """Check every scene file at start-up. Returns (names, files, errors): the scene names in
    order (lowercase, as settings.json and keymap.json store them), name -> file, and problems
    (each file with one is skipped). taken = the built-in scene names."""
    names, files, errors = [], {}, []
    for fname in _files():
        where = SCENE_DIR + "/" + fname
        try:
            name = name_of(fname)
            read(where, color)
        except SceneError as e:
            errors.append("{}: {}; skipped".format(where, e))
            continue
        except MemoryError:
            errors.append(where + ": not enough memory to load it; skipped")
            continue
        if name in taken or name in names or name in ("same", "alert"):
            errors.append("{}: a scene called {} already exists; skipped".format(where, name.upper()))
            continue
        names.append(name)
        files[name] = where
    return names, files, errors
