# ember/keymap.py - reads and checks the Ember keymap (NOTES/KEYMAP_FORMAT.md) at start-up and
# packs it (layers.py). Only used at start-up: code.py lets it go afterwards.
#
#   keymap.json      {"ember": "keymap", "layers": ["excel.json", ...], "home": "EXCEL",
#                     "hold_keys": [key or null x 8]}
#   layers/NAME.json {"ember": "layer", "name": "EXCEL", "keys": [key or null x 8],
#                     "encoder": {"label", "cw", "ccw", "accel"}, "lights", "jiggle", "num_lock", "module_view"}
#   a key            {"label": "Copy", "pic": {"w", "h", "bits"}, <one action>, "repeat", "confirm", "speed"}
#                    (speed: "normal" / "careful" / "slow": how fast its text and macro steps are typed; none = the pad's)
#
# An action is an object with exactly one of:
#   key "ENTER"   combo ["CONTROL", "C"]   text "Hello"   media "PLAYPAUSE"   open "https://..." / "notepad.exe"
#   scroll 1 / -1   mouse [dx, dy]   click "left" / "right" / "middle"   delay 0.5   sequence [action, ...]
#   tool "lock"   layer "EXCEL"   number "LINE" (types that counter's next number)   stamp "MM/DD/YYYY" (the date / time)
#   in a macro only: pause "Pick the plant" (waits for a click, the note on the screen)   mark [row, rows] (the CSV row
#   it's on: the progress screen)
# A step in a sequence may add "times": 2-999. Problems go in ERRORS (shown at start-up), never a crash:
# a key with a problem shows "ERR" and does nothing.

import json
import binascii
from adafruit_hid.keycode import Keycode
from ember.layers import Keymap, NUM_KEYS, SPEEDS

MEDIA_CODES = {
    "PREV": 0xB6, "NEXT": 0xB5, "PLAYPAUSE": 0xCD, "STOP": 0xB7, "EJECT": 0xB8,
    "FAST_FORWARD": 0xB3, "REWIND": 0xB4, "MUTE": 0xE2,
    "VOL_UP": 0xE9, "VOL_DN": 0xEA,
    "BRIGHTNESS_UP": 0x6F, "BRIGHTNESS_DOWN": 0x70,
}
MOUSE_BUTTONS = {"left": 1, "right": 2, "middle": 4}
OP = {"key": 1, "combo": 2, "click": 3, "media": 4, "scroll": 5, "mouse": 6, "delay": 7,
      "text": 8, "open": 9, "tool": 13, "layer": 14, "number": 15, "stamp": 16, "mark": 17, "pause": 18}
SEQUENCE_OP = 11    # a whole packed macro (4-byte length first): only in packed layers
REPEAT_OP = 12      # in a macro: a count (2 bytes), then one step to run that many times
TEXT_KINDS = ("text", "open", "tool", "layer", "number", "stamp", "pause")
KEY_EXTRAS = ("label", "pic", "repeat", "confirm", "speed")
REPEATABLE = ("media", "scroll", "mouse", "text", "sequence")
MODULE_VIEWS = ("status", "half", "full", "off")
MAX_TIMES = 999
MAX_LAYERS = 24
PIC_W, PIC_H = 29, 24
CARD_W, CARD_H = 40, 40     # a layer's picture: its layer card (the Layer cards picker)

ERRORS = []


def _place(where):
    if isinstance(where, tuple):
        return "{} step {}".format(_place(where[0]), where[1])
    return where


def _bad(where, message):
    ERRORS.append("{}: {}".format(_place(where), message))
    return None


def _int16(out, value):
    value &= 0xFFFF
    out.append(value & 255)
    out.append(value >> 8)


def _repeat(out, data, n):
    while n > 0:
        k = min(n, 0xFFFF)
        if 3 + len(data) < k * len(data):
            out.append(REPEAT_OP)
            _int16(out, k)
            out.extend(data)
        else:
            for _ in range(k):
                out.extend(data)
        n -= k


def _pack(step, out, where):
    """Add a checked action to out (a packed layer or macro). Returns how many steps it added (0 = a problem)."""
    kind, value = step
    if kind == "sequence":
        out.extend(memoryview(value)[2:])
        return value[0] | value[1] << 8
    if kind in ("scroll", "mouse"):
        for v in (value if kind == "mouse" else (value,)):
            if not -32768 <= v <= 32767:
                return _bad(where, kind + " is too big") or 0
    if kind in TEXT_KINDS:
        data = value.encode()
        if len(data) > 0xFFFF:
            return _bad(where, kind + " is too long") or 0
        out.append(OP[kind])
        _int16(out, len(data))
        out.extend(data)
        return 1
    out.append(OP[kind])
    if kind in ("key", "click"):
        out.append(value)
    elif kind == "combo":
        out.append(len(value))
        out.extend(bytes(value))
    elif kind in ("media", "scroll"):
        _int16(out, value)
    elif kind in ("mouse", "mark"):
        _int16(out, value[0])
        _int16(out, value[1])
    else:                                   # delay, in ms
        ms = min(int(value * 1000 + 0.5), 0xFFFFFFFF)
        _int16(out, ms)
        _int16(out, ms >> 16)
    return 1


def _pack_action(action, out):
    """An action in a packed layer (a whole macro gets a length first)."""
    if action[0] == "sequence":
        out.append(SEQUENCE_OP)
        n = len(action[1])
        out.extend(bytes((n & 255, n >> 8 & 255, n >> 16 & 255, n >> 24)))
        out.extend(action[1])
    else:
        _pack(action, out, "")


def _keycode(name):
    if isinstance(name, str) and not name.startswith("_"):
        code = getattr(Keycode, name, None)
        if isinstance(code, int):
            return code
    return None


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_action(data, where, extra=()):
    """A JSON action -> (kind, value), or None (with the problem in ERRORS)."""
    if not isinstance(data, dict):
        return _bad(where, "should be {...}")
    fields = [k for k in data if k not in extra]
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
    if kind in TEXT_KINDS:
        if not isinstance(value, str) or not value:
            return _bad(where, kind + " is empty")
        if kind == "number" and len(value) > 16:
            return _bad(where, "a counter's name is up to 16 letters")
        if kind == "stamp" and len(value) > 40:
            return _bad(where, "a date format is up to 40 characters")
        return (kind, value)
    if kind == "media":
        code = MEDIA_CODES.get(value)
        return ("media", code) if code is not None else _bad(where, "unknown media key {}".format(value))
    if kind == "scroll":
        if not isinstance(value, int) or isinstance(value, bool) or not value:
            return _bad(where, "scroll should be a whole number, not 0")
        return ("scroll", value)
    if kind == "mouse":
        if not isinstance(value, list) or len(value) != 2 or not all(isinstance(v, int) and not isinstance(v, bool) for v in value):
            return _bad(where, "mouse should be [x, y]")
        return ("mouse", (value[0], value[1]))
    if kind == "click":
        button = MOUSE_BUTTONS.get(value)
        return ("click", button) if button else _bad(where, "click should be left, right or middle")
    if kind == "mark":
        if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 0xFFFF for v in value)):
            return _bad(where, "mark should be [row, rows]")
        return ("mark", (value[0], value[1]))
    if kind == "delay":
        if not _number(value) or value <= 0:
            return _bad(where, "delay should be seconds above 0")
        return ("delay", value)
    if kind == "sequence":
        if not isinstance(value, list) or not value:
            return _bad(where, "sequence is empty")
        out = bytearray(2)
        count, ok, last, run = 0, True, None, 0
        for i, step in enumerate(value):
            place = (where, i + 1)
            times = step.get("times", 1) if isinstance(step, dict) else 1
            if not (isinstance(times, int) and not isinstance(times, bool) and 1 <= times <= MAX_TIMES):
                _bad(place, "times should be 1-{}".format(MAX_TIMES))
                ok = False
                continue
            parsed = parse_action(step, place, extra=("times",))
            if not parsed:
                ok = False
                continue
            if parsed[0] == "sequence":
                if times > 1:
                    _bad(place, "a macro inside a macro can't have times")
                    ok = False
                    continue
                _repeat(out, last or b"", run)
                last, run = None, 0
                count += _pack(parsed, out, place)
                continue
            data = bytearray()
            if not _pack(parsed, data, place):
                ok = False
                continue
            if data == last:
                run += times
            else:
                _repeat(out, last or b"", run)
                last, run = data, times
            count += times
        _repeat(out, last or b"", run)
        if count > 0xFFFF:
            return _bad(where, "has too many steps")
        if not ok:
            return None                     # a macro with a broken step is off, not run partly
        out[0] = count & 255
        out[1] = count >> 8
        return ("sequence", out)
    return _bad(where, "unknown action {}".format(kind))


def _flag(data, field, where):
    value = data.get(field, False)
    if not isinstance(value, bool):
        _bad(where, field + " should be true or false")
        return False
    return value


def _text(out, s):
    data = s.encode()[:255]
    out.append(len(data))
    out.extend(data)


def _pic(pic, where, max_w=PIC_W, max_h=PIC_H):
    """A key's picture (or a layer's card picture) -> (w, h, bits) or None."""
    if not isinstance(pic, dict) or not pic.get("bits"):
        return None                         # (no bits yet: the page draws it; the label shows meanwhile)
    try:
        w, h = pic["w"], pic["h"]
        bits = binascii.a2b_base64(pic["bits"])
    except (KeyError, ValueError, TypeError):
        return _bad(where, "picture can't be read")
    if not (isinstance(w, int) and isinstance(h, int) and 0 < w <= max_w and 0 < h <= max_h):
        return _bad(where, "picture should be up to {} x {}".format(max_w, max_h))
    if len(bits) < ((w + 7) >> 3) * h:
        return _bad(where, "picture is cut short")
    return (w, h, bits[:((w + 7) >> 3) * h])


def _pack_key(key, where, out):
    if key is None:
        out.append(0)
        return
    if not isinstance(key, dict):
        _bad(where, "should be {...} or null")
        out.append(1)
        _text(out, "ERR")
        return
    label = key.get("label", "")
    if not isinstance(label, str):
        label = "ERR"
        _bad(where, "label should be text")
    pic = _pic(key.get("pic"), where)
    action = None
    if [k for k in key if k not in KEY_EXTRAS]:
        action = parse_action(key, where, extra=KEY_EXTRAS)
        if action is None:
            label, pic = "ERR", None
    flags = 1 | (2 if action else 0) | (16 if pic else 0)
    speed = key.get("speed")
    if speed is not None:
        if speed in SPEEDS:
            flags |= (SPEEDS.index(speed) + 1) << 5
        else:
            _bad(where, "speed should be normal, careful or slow")
    if action and _flag(key, "confirm", where):
        flags |= 8
    elif action and _flag(key, "repeat", where):
        if action[0] in REPEATABLE:
            flags |= 4
        elif action[0] not in ("key", "combo", "click"):     # (those repeat when held anyway)
            _bad(where, "{} can't repeat".format(action[0]))
    out.append(flags)
    _text(out, label)
    if pic:
        out.append(pic[0])
        out.append(pic[1])
        out.extend(pic[2])
    if action:
        _pack_action(action, out)


def _pack_layer(data, name):
    out = bytearray(1)
    flags = 0
    keys = data.get("keys") or []
    if not isinstance(keys, list):
        _bad(name, "keys should be a list")
        keys = []
    for k in range(NUM_KEYS):
        _pack_key(keys[k] if k < len(keys) else None, "{} key {}".format(name, k + 1), out)
    enc = data.get("encoder") or {}
    if not isinstance(enc, dict):
        _bad(name + " encoder", "should be {...}")
        enc = {}
    _text(out, enc.get("label", "") if isinstance(enc.get("label", ""), str) else "ERR")
    for turn in ("cw", "ccw"):
        a = parse_action(enc[turn], "{} encoder {}".format(name, turn)) if enc.get(turn) is not None else None
        if a:
            out.append(1)
            _pack_action(a, out)
        else:
            out.append(0)
    if _flag(enc, "accel", name + " encoder"):
        flags |= 1
    if _flag(data, "jiggle", name):
        flags |= 4
    if _flag(data, "num_lock", name):
        flags |= 8
    view = data.get("module_view", "status")
    if view in MODULE_VIEWS:
        flags |= MODULE_VIEWS.index(view) << 5
    else:
        _bad(name, "module_view should be status, half, full or off")
    lights = data.get("lights")
    if lights is not None:
        parsed = _parse_lights(lights, name + " lights")
        if parsed:
            flags |= 2
            scene, c1, c2, level, speed = parsed
            _text(out, scene)
            for c in (c1, c2):
                if c is None:
                    out.append(0)
                else:
                    out.append(1)
                    out.extend(bytes(c))
            out.append(level)
            out.append(speed)
    card = _pic(data.get("pic"), name + " picture", CARD_W, CARD_H)
    if card:
        flags |= 16
        out.append(card[0])
        out.append(card[1])
        out.extend(card[2])
    out[0] = flags
    return out


def _parse_lights(data, where):
    """A layer's own lights -> (scene, color 1, color 2, brightness 1-10, speed 0-10) or None."""
    from ember.lights import SCENES, color
    if not isinstance(data, dict):
        return _bad(where, "should be {...}")
    scene = data.get("scene", "static")
    if scene not in SCENES:
        return _bad(where, "unknown scene {}".format(scene))
    colors = []
    for field in ("color1", "color2"):
        value = data.get(field)
        rgb = None if value is None else color(value)
        if value is not None and rgb is None:
            _bad(where, "unknown color {}".format(value))
        colors.append(rgb)
    level = data.get("brightness", 4)
    if not (isinstance(level, int) and not isinstance(level, bool) and 1 <= level <= 10):
        _bad(where, "brightness should be 1-10")
        level = 4
    speed = data.get("speed", 0)
    if not (isinstance(speed, int) and not isinstance(speed, bool) and 0 <= speed <= 10):
        _bad(where, "speed should be 1-10")
        speed = 0
    return (scene, colors[0], colors[1], level, speed)


# secret.json: the secret pages (up to MAX_SECRET), encrypted (AES, CTR mode) with a key made from this pad's chip ID (as
# FIRMWARE_04), so the file is unreadable copied off the drive or on another pad. {"mp1_secret": 1, "iv": hex,
# "data": base64}; the plain text is a JSON list of the pages (Ember layers; a null is skipped), padded with
# spaces. The page gets the key over the Link (linkfiles "skey") to read and write it. A FIRMWARE_04 file (old
# layers inside) is converted by the page ("Convert it"), not here.
SECRET_FILE = "secret.json"
SECRET_SALT = b"MP1 secret layer"           # 16 bytes
MAX_SECRET = 4


def secret_key():
    import microcontroller
    uid = bytes(microcontroller.cpu.uid)
    return bytes(SECRET_SALT[i] ^ uid[i % len(uid)] for i in range(16))


def pin_key(pin):
    """The key for secret pages with a PIN ("pin": true in secret.json): the chip's key and the PIN together (one AES
    block, "MP1 PIN " + the digits, encrypted with the chip's key), so neither alone opens them. The page does the same."""
    import aesio
    block = ("MP1 PIN " + pin + " " * 8)[:16].encode()
    out = bytearray(16)
    aesio.AES(secret_key(), aesio.MODE_ECB).encrypt_into(block, out)
    return bytes(out)


SECRET_NOTE = [""]                          # why the secret pages are (not) loaded, for the pad / page / console


def _read_secrets(root, pin=None, again=True):
    """The secret pages (a list), or "pin" when they have a PIN and it isn't given or is wrong. SECRET_NOTE says why."""
    SECRET_NOTE[0] = ""
    try:
        with open(root + SECRET_FILE) as f:
            data = json.load(f)
    except OSError as e:
        SECRET_NOTE[0] = "no secret.json" if getattr(e, "errno", 0) == 2 else "secret.json: can't open it ({})".format(e)
        return []                           # no secret layers
    except ValueError:
        SECRET_NOTE[0] = "secret.json isn't valid JSON"
        _bad(SECRET_FILE, "isn't valid JSON; secret layers not loaded")
        return []
    except MemoryError:
        import gc
        data = None
        gc.collect()
        if again:                           # (a brief squeeze: once more with the memory tidied)
            return _read_secrets(root, pin, False)
        SECRET_NOTE[0] = "not enough memory to read secret.json"
        _bad(SECRET_FILE, "not enough memory to read it; secret pages not loaded (unplug and plug the pad back in)")
        return []
    has_pin = isinstance(data, dict) and data.get("pin") is True
    if has_pin and not pin:
        SECRET_NOTE[0] = "locked with a PIN"
        return "pin"
    try:
        import binascii
        import aesio
        iv = binascii.unhexlify(data["iv"])
        box = binascii.a2b_base64(data["data"])
        data = None
        plain = bytearray(len(box))
        aesio.AES(pin_key(pin) if has_pin else secret_key(), aesio.MODE_CTR, iv).decrypt_into(box, plain)
        box = None
        layers = json.loads(plain)
        plain = None
        if not isinstance(layers, list):
            raise ValueError
    except MemoryError:
        import gc
        box = plain = data = None
        gc.collect()
        if again:
            return _read_secrets(root, pin, False)
        SECRET_NOTE[0] = "not enough memory to read secret.json"
        _bad(SECRET_FILE, "not enough memory to read it; secret pages not loaded (unplug and plug the pad back in)")
        return []
    except (KeyError, ValueError, TypeError):
        if has_pin:
            SECRET_NOTE[0] = "locked with a PIN"
            return "pin"                    # (the wrong PIN: what it opens isn't JSON)
        SECRET_NOTE[0] = "secret.json can't be read on this pad"
        _bad(SECRET_FILE, "can't be read on this pad (made for another one?); secret layers not loaded")
        return []
    return layers


def _read(path):
    with open(path) as f:
        return json.load(f)


def load(root="/", pin=None):
    """Read keymap.json and its layer files: a layers.Keymap (problems in ERRORS). pin: the secret pages' PIN, if they
    have one (without it, or with a wrong one, they aren't loaded: Keymap.PIN is True)."""
    del ERRORS[:]
    try:
        index = _read(root + "keymap.json")
    except (OSError, ValueError) as e:
        _bad("keymap.json", "can't be read ({})".format(e))
        index = {}
    if index and index.get("ember") != "keymap":
        _bad("keymap.json", "isn't an Ember keymap (convert it in the Ember page)")
        index = {}
    names, packed, files = [], [], []
    for file in (index.get("layers") or [])[:MAX_LAYERS]:
        try:
            data = _read(root + "layers/" + file)
        except (OSError, ValueError) as e:
            _bad(file, "can't be read ({})".format(e))
            continue
        if not isinstance(data, dict) or data.get("ember") != "layer":
            _bad(file, "isn't an Ember layer")
            continue
        name = data.get("name")
        if not isinstance(name, str) or not name or name in names:
            _bad(file, "needs a name of its own")
            continue
        names.append(name)
        files.append(file)
        packed.append(_pack_layer(data, name))
        data = None
    if not names:                           # nothing usable: one empty layer, so the pad still starts
        names.append("EMPTY")
        packed.append(_pack_layer({}, "EMPTY"))
    hold = None
    if isinstance(index.get("hold_keys"), list):
        hold = len(packed)
        packed.append(_pack_layer({"keys": index["hold_keys"]}, "HOLD+KEY"))
    secret, secret_names = [], []
    pages = _read_secrets(root, pin)
    locked = pages == "pin"
    for data in ([] if locked else pages):
        if data is None:
            continue
        if not isinstance(data, dict) or data.get("ember") != "layer":
            _bad(SECRET_FILE, "is from the old firmware: open the Ember page and convert it")
            break
        if len(secret) >= MAX_SECRET:
            break
        name = data.get("name") if isinstance(data.get("name"), str) and data.get("name") else "SECRET"
        secret.append(len(packed))
        secret_names.append(name)
        packed.append(_pack_layer(data, name))
        data = None
    offsets, blob = [0], bytearray()
    for p in packed:
        blob.extend(p)
        offsets.append(len(blob))
    home = names.index(index["home"]) if index.get("home") in names else 0
    km = Keymap(tuple(names), bytes(blob), tuple(offsets), home, hold, tuple(files), tuple(secret), tuple(secret_names))
    km.PIN = locked                         # (secret pages with a PIN, not opened yet)
    km.SECRET_NOTE = SECRET_NOTE[0] or "{} page{}".format(len(secret), "" if len(secret) == 1 else "s")
    print("secret pages:", km.SECRET_NOTE)  # (on the console: a log shows when and why they went)
    return km
