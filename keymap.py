# keymap.py – loads and checks the keymap (format version 2): keymap.js, or keymap.json if
# there's no keymap.js (see lib/macropad/jsfile.py; the JSON inside is the same).
#
# {
#   "version": 2,
#   "layers": [
#     {
#       "name": "MEDIA",
#       "default": true,                      (optional, one layer)
#       "secret": true,                       (optional: true or 1 = Secret 1, 2 = Secret 2;
#                                              one layer each, never the default)
#       "keys": [ {"icon": "PLY", "media": "PLAYPAUSE"}, ... up to 8, null = unassigned ],
#                 (a key may add "repeat": true: holding it repeats the action, see REPEATABLE,
#                  or "confirm": true: it only fires after being held for CONFIRM TIME)
#       "encoder": {"icon": "VOL", "cw": {"media": "VOL_UP"}, "ccw": {"media": "VOL_DN"}, "accel": true},
#       "lights": {"scene": "breathing", "color1": "BLUE", "color2": "#FF8800"}   (optional; replaces
#                 the device's LIGHTS scene and colours on this layer. Colours: palette name or #RRGGBB)
#     }
#   ]
# }
#
# An action is an object with exactly one of:
#   text  "Hello"                    key   "ENTER"                 combo ["CONTROL", "C"]
#   media "PLAYPAUSE"                url   "https://..."           app   "notepad.exe"
#   scroll 1 (up) / -1 (down)        mouse [dx, dy]                click "left" | "right" | "middle"
#   delay 0.5 (seconds)              sequence [action, action, ...]
#
# Problems are collected in ERRORS (shown on the OLED at boot) instead of crashing.
# A key with a problem shows "ERR" as its icon and does nothing.

from adafruit_hid.keycode import Keycode
from macropad.lights import SCENES, color
from macropad import jsfile

KEYMAP_FILES = ("keymap.js", "keymap.json")

NUM_KEYS = 8
MAX_ICON = 4

MEDIA_CODES = {
    "PREV": 0xB6, "NEXT": 0xB5, "PLAYPAUSE": 0xCD, "STOP": 0xB7, "EJECT": 0xB8,
    "FAST_FORWARD": 0xB3, "REWIND": 0xB4, "MUTE": 0xE2,
    "VOL_UP": 0xE9, "VOL_DN": 0xEA,
    "BRIGHTNESS_UP": 0x6F, "BRIGHTNESS_DOWN": 0x70,
}
MOUSE_BUTTONS = {"left": 1, "right": 2, "middle": 4}

LAYER_FIELDS = ("name", "default", "secret", "keys", "encoder", "lights")
KEY_EXTRAS = ("icon", "repeat", "confirm")     # fields of a key that aren't its action
# Actions that fire once per press can repeat while held. key / combo / click are held
# down for as long as the key is, so the computer already repeats them like a keyboard.
REPEATABLE = ("media", "scroll", "mouse", "text", "sequence")
ENCODER_FIELDS = ("icon", "cw", "ccw", "accel")
LIGHT_FIELDS = ("scene", "color1", "color2")

ERRORS = []


class KeymapError(Exception):
    pass


class Layer:
    def __init__(self, name):
        self.name = name
        self.default = False
        self.secret = 0                     # 0 = regular, 1 = Secret 1, 2 = Secret 2
        self.keys = [None] * NUM_KEYS       # (kind, value) actions
        self.icons = [""] * NUM_KEYS
        self.repeat = [False] * NUM_KEYS    # repeat while held
        self.confirm = [False] * NUM_KEYS   # hold to confirm
        self.enc_icon = ""
        self.cw = None
        self.ccw = None
        self.accel = False
        self.lights = None                  # (scene, color1, color2); colours may be None


def _bad(where, message):
    ERRORS.append("{}: {}".format(where, message))
    return None


def _keycode(name):
    if isinstance(name, str) and not name.startswith("_"):
        code = getattr(Keycode, name, None)
        if isinstance(code, int):
            return code
    return None


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _action_fields(data, extra):
    return [k for k in data if k not in extra]


def parse_action(data, where, extra=()):
    """Turn a JSON action object into a (kind, value) tuple. Returns None (and records
    an error) if it is invalid. Fields named in `extra` (like "icon") are ignored."""
    if not isinstance(data, dict):
        return _bad(where, "should be {...}")
    fields = _action_fields(data, extra)
    if not fields:
        return _bad(where, "no action")
    if len(fields) > 1:
        return _bad(where, "more than one action: " + ", ".join(sorted(fields)))
    kind = fields[0]
    value = data[kind]

    if kind == "key":
        code = _keycode(value)
        return ("key", code) if code is not None else _bad(where, "unknown key {}".format(value))

    if kind == "combo":
        if not isinstance(value, list) or not value:
            return _bad(where, "combo should be a list of keys")
        codes = []
        for name in value:
            code = _keycode(name)
            if code is None:
                return _bad(where, "unknown key {}".format(name))
            codes.append(code)
        return ("combo", tuple(codes))

    if kind in ("text", "url", "app"):
        if not isinstance(value, str) or not value:
            return _bad(where, kind + " is empty")
        return (kind, value)

    if kind == "media":
        code = MEDIA_CODES.get(value)
        return ("media", code) if code is not None else _bad(where, "unknown media key {}".format(value))

    if kind == "scroll":
        if not isinstance(value, int) or isinstance(value, bool) or not value:
            return _bad(where, "scroll should be a whole number, not 0")
        return ("scroll", value)

    if kind == "mouse":
        if (not isinstance(value, list) or len(value) != 2
                or not all(isinstance(v, int) and not isinstance(v, bool) for v in value)):
            return _bad(where, "mouse should be [x, y]")
        return ("mouse", (value[0], value[1]))

    if kind == "click":
        button = MOUSE_BUTTONS.get(value)
        return ("click", button) if button else _bad(where, "click should be left, right or middle")

    if kind == "delay":
        if not _is_number(value) or value <= 0:
            return _bad(where, "delay should be seconds above 0")
        return ("delay", value)

    if kind == "sequence":
        if not isinstance(value, list) or not value:
            return _bad(where, "sequence is empty")
        steps = [parse_action(step, "{} step {}".format(where, i + 1)) for i, step in enumerate(value)]
        # A sequence with a broken step is disabled entirely rather than run partially
        return None if None in steps else ("sequence", steps)

    return _bad(where, "unknown action {}".format(kind))


def _icon(data, where):
    icon = data.get("icon", "")
    if not isinstance(icon, str):
        _bad(where, "icon should be text")
        return "ERR"
    return icon[:MAX_ICON]


def _secret(data, where):
    """"secret": true / 1 = Secret 1, 2 = Secret 2, false / 0 / missing = not secret."""
    value = data.get("secret", False)
    if isinstance(value, bool):
        return 1 if value else 0
    if value in (0, 1, 2) and isinstance(value, int):
        return value
    _bad(where, "secret should be true (Secret 1), 2 (Secret 2) or false")
    return 0


def _flag(data, field, where):
    value = data.get(field, False)
    if not isinstance(value, bool):
        _bad(where, field + " should be true or false")
        return False
    return value


def _parse_layer(index, data):
    if not isinstance(data, dict):
        _bad("Layer {}".format(index + 1), "should be {...}")
        return Layer("LAYER{}".format(index + 1))

    name = data.get("name")
    if not isinstance(name, str) or not name:
        name = "LAYER{}".format(index + 1)
        _bad("Layer {}".format(index + 1), "missing name")
    layer = Layer(name)

    for field in data:
        if field not in LAYER_FIELDS:
            _bad(name, "unknown field {}".format(field))
    layer.default = _flag(data, "default", name)
    layer.secret = _secret(data, name)

    keys = data.get("keys", [])
    if not isinstance(keys, list):
        _bad(name, "keys should be a list")
        keys = []
    if len(keys) > NUM_KEYS:
        _bad(name, "has {} keys, only {} used".format(len(keys), NUM_KEYS))
    for i, key in enumerate(keys[:NUM_KEYS]):
        if key is None:
            continue
        where = "{} key {}".format(name, i + 1)
        if not isinstance(key, dict):
            _bad(where, "should be {...} or null")
            layer.icons[i] = "ERR"
            continue
        layer.icons[i] = _icon(key, where)
        if _action_fields(key, KEY_EXTRAS):            # icon-only keys are just labels
            layer.keys[i] = parse_action(key, where, extra=KEY_EXTRAS)
            if layer.keys[i] is None:
                layer.icons[i] = "ERR"
        if _flag(key, "confirm", where) and layer.keys[i]:
            layer.confirm[i] = True
        if _flag(key, "repeat", where) and layer.keys[i]:
            kind = layer.keys[i][0]
            if layer.confirm[i]:
                _bad(where, "confirm and repeat can't both be on (confirm used)")
                continue
            if kind in REPEATABLE:
                layer.repeat[i] = True
            elif kind in ("key", "combo", "click"):
                _bad(where, "repeat isn't needed: a held {} already repeats".format(kind))
            else:
                _bad(where, "{} can't repeat".format(kind))

    enc = data.get("encoder")
    if enc is not None:
        where = name + " encoder"
        if not isinstance(enc, dict):
            _bad(where, "should be {...}")
        else:
            for field in enc:
                if field not in ENCODER_FIELDS:
                    _bad(where, "unknown field {}".format(field))
            layer.enc_icon = _icon(enc, where)
            layer.accel = _flag(enc, "accel", where)
            if enc.get("cw") is not None:
                layer.cw = parse_action(enc["cw"], where + " cw")
            if enc.get("ccw") is not None:
                layer.ccw = parse_action(enc["ccw"], where + " ccw")
            if ("cw" in enc and layer.cw is None) or ("ccw" in enc and layer.ccw is None):
                layer.enc_icon = "ERR"

    lights = data.get("lights")
    if lights is not None:
        layer.lights = _parse_lights(lights, name + " lights")
    return layer


def _parse_lights(data, where):
    if not isinstance(data, dict):
        return _bad(where, "should be {...}")
    for field in data:
        if field not in LIGHT_FIELDS:
            _bad(where, "unknown field {}".format(field))
    scene = data.get("scene", "static")
    if scene not in SCENES:
        return _bad(where, "unknown scene {}".format(scene))
    colors = []
    for field in ("color1", "color2"):
        value = data.get(field)
        rgb = None if value is None else color(value)
        if value is not None and rgb is None:
            _bad(where, "unknown colour {}".format(value))
        colors.append(rgb)
    return (scene, colors[0], colors[1])


def _resolve_roles(layers):
    """Pick the default and the secret layers (Secret 1, Secret 2), reporting conflicts.
    Returns (default, (secret1, secret2), regular); a missing secret layer is None."""
    for layer in layers:
        if layer.default and layer.secret:
            _bad(layer.name, "can't be both default and secret; secret ignored")
            layer.secret = 0

    secrets = [None, None]
    for i, layer in enumerate(layers):
        if layer.secret:
            slot = layer.secret - 1
            if secrets[slot] is None:
                secrets[slot] = i
            else:
                _bad(layer.name, "only one Secret {} layer allowed; using {}".format(
                    layer.secret, layers[secrets[slot]].name))
                layer.secret = 0

    regular = [i for i in range(len(layers)) if i not in secrets]
    if not regular:
        _bad(layers[0].name, "the only layer can't be secret" if len(layers) == 1
             else "every layer is secret; secret ignored")
        for layer in layers:
            layer.secret = 0
        secrets, regular = [None, None], list(range(len(layers)))

    default = None
    for i in regular:
        if layers[i].default:
            if default is None:
                default = i
            else:
                _bad(layers[i].name, "only one default layer allowed; using " + layers[default].name)
    if default is None:
        default = regular[0]

    names = set()
    for layer in layers:
        if layer.name in names:
            _bad(layer.name, "two layers have this name")
        names.add(layer.name)
    return default, tuple(secrets), regular


def _load(path=None):
    path = path or jsfile.pick(*KEYMAP_FILES)
    try:
        data = jsfile.load(path)
    except OSError:
        raise KeymapError("keymap.js not found (nor keymap.json)")
    except ValueError:
        raise KeymapError(path + " is not valid JSON. Check it in the configurator")

    if not isinstance(data, dict):
        raise KeymapError(path + " should be {...}")
    if "keymap" in data and "layers" not in data:
        raise KeymapError(path + " is the old v1 format. Convert it in the configurator")
    if data.get("version") != 2:
        raise KeymapError(path + " needs \"version\": 2")
    layers = data.get("layers")
    if not isinstance(layers, list) or not layers:
        raise KeymapError(path + " has no layers")
    for field in data:
        if field not in ("version", "layers"):
            _bad(path, "unknown field {}".format(field))
    return [_parse_layer(i, layer) for i, layer in enumerate(layers)]


try:
    LAYERS = _load()
except Exception as e:
    ERRORS.insert(0, str(e) if isinstance(e, KeymapError) else "keymap: unexpected error {}".format(e))
    LAYERS = [Layer("NO KEYMAP")]

DEFAULT_LAYER, SECRET_LAYERS, REGULAR_LAYERS = _resolve_roles(LAYERS)
SECRET_LAYER = SECRET_LAYERS[0]     # Secret 1
LAYER_NAMES = [layer.name for layer in LAYERS]

for _message in ERRORS:
    print("KEYMAP ERROR:", _message)
print("Loaded {} layers, default: {}, secret 1: {}, secret 2: {}".format(
    len(LAYERS), DEFAULT_LAYER, SECRET_LAYERS[0], SECRET_LAYERS[1]))
