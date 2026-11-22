# ember/pins.py (from FIRMWARE_04; Ember adds the hardware facts: led_count, buzzer_type,
# buzzer_active_low, encoder_divisor - they were settings in FIRMWARE_04)
# Which pins the macropad uses: wiring.json on the drive (edit it with Toolkit/mp1_workbench.html),
# so hand-wired pads can use other pins without changing the firmware. Without wiring.json,
# an old-style wiring.py is used if there is one, otherwise the standard MP1 pins.
#
# Every pin is checked before anything is started: it must exist on this board, be used
# only once, not be the onboard LED, the screen's SDA / SCL must be a pair on one I2C bus
# and the encoder's A / B pins must be next to each other (the RP2040's encoder hardware
# needs that). If the keys, encoder or screen pins are wrong, the standard MP1 pins are
# used instead and the problem is reported; a bad LED strip or buzzer pin just turns that
# add-on off.
#
#   {"board": "YD-RP2040", "rows": ["GP20", "GP21"], "cols": ["GP22", "GP26", "GP27", "GP28"],
#    "encoder_a": "GP8", "encoder_b": "GP9", "encoder_button": "GP10",
#    "i2c_sda": "GP14", "i2c_scl": "GP15", "oled_address": "0x3C", "i2c_frequency": 400000,
#    "led_strip": "GP19", "buzzer": "GP17"}          (led_strip / buzzer may be null = none)

import board
from ember import jsfile

WIRING_FILE = "wiring.json"
STANDARD = {
    # keys on header pins 26, 27, 29, 31, 32, 34 in order (row 1, row 2, col 1-4): these exist
    # on every Pico-footprint board (Pico, Pico 2, YD-RP2040). Pads wired before 2026-11-10
    # used rows GP22/GP21 and cols GP26-GP29: they need those in wiring.json.
    "rows": ("GP20", "GP21"), "cols": ("GP22", "GP26", "GP27", "GP28"),
    "encoder_a": "GP8", "encoder_b": "GP9", "encoder_button": "GP10",
    "i2c_sda": "GP14", "i2c_scl": "GP15", "oled_address": 0x3C, "i2c_frequency": 400000,
    "led_strip": "GP19", "buzzer": "GP17",
}
SINGLE = ("encoder_a", "encoder_b", "encoder_button", "i2c_sda", "i2c_scl")
ADDONS = ("led_strip", "buzzer")
FACTS = {"led_count": 4, "buzzer_type": "passive", "buzzer_active_low": False, "encoder_divisor": 4}
KNOWN = ("board", "rows", "cols", "oled_address", "i2c_frequency") + SINGLE + ADDONS + tuple(FACTS)
# Names in the old wiring.py
OLD_NAMES = {"ROWS": "rows", "COLS": "cols", "ENC_A": "encoder_a", "ENC_B": "encoder_b",
             "ENC_SW": "encoder_button", "I2C_SDA": "i2c_sda", "I2C_SCL": "i2c_scl",
             "OLED_ADDRESS": "oled_address", "I2C_FREQUENCY": "i2c_frequency",
             "LED_STRIP_PIN": "led_strip", "BUZZER_PIN": "buzzer"}


def _number(value):
    """"GP14" (or "gp14", "board.GP14") -> 14; anything else -> None."""
    if not isinstance(value, str):
        return None
    name = value.strip().upper()
    if name.startswith("BOARD."):
        name = name[6:]
    if name.startswith("GP") and name[2:].isdigit():
        return int(name[2:])
    return None


def _exists(n):
    return n is not None and hasattr(board, "GP{}".format(n))


def _onboard_led():
    """GP number of the board's own LED (used for the jiggle light), or None."""
    led = getattr(board, "LED", None)
    if led is None:
        return None
    for n in range(48):
        if getattr(board, "GP{}".format(n), None) is led:
            return n
    return None


def _address(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value, 16) if value.lower().startswith("0x") else int(value)
        except ValueError:
            return None
    return None


def check(data):
    """wiring.json contents -> (values to use, problems). Values are GP numbers."""
    errors = []
    bad_core = False
    v = {}
    for key in data:
        if key not in KNOWN:
            errors.append("wiring.json: unknown entry {} (ignored)".format(key))

    def pin(key, value):
        nonlocal bad_core
        n = _number(value)
        if not _exists(n):
            errors.append("wiring.json: {} {} isn't a pin on this board".format(key, value))
            bad_core = True
            return None
        return n

    for key, count in (("rows", 2), ("cols", 4)):
        value = data.get(key, STANDARD[key])
        if not isinstance(value, (list, tuple)) or len(value) != count:
            errors.append("wiring.json: {} needs {} pins".format(key, count))
            bad_core = True
            v[key] = None
        else:
            v[key] = [pin(key, p) for p in value]
    for key in SINGLE:
        v[key] = pin(key, data.get(key, STANDARD[key]))

    addons = {}
    for key in ADDONS:
        value = data.get(key, STANDARD[key])
        if value is None or (isinstance(value, str) and value.strip().lower() in ("", "none")):
            addons[key] = None
            continue
        n = _number(value)
        if not _exists(n):
            errors.append("wiring.json: {} {} isn't a pin on this board; {} turned off".format(
                key, value, key.replace("_", " ")))
            addons[key] = None
        else:
            addons[key] = n

    address = _address(data.get("oled_address", STANDARD["oled_address"]))
    if address is None or not 0x08 <= address <= 0x77:
        errors.append("wiring.json: oled_address should be like \"0x3C\"; using 0x3C")
        address = 0x3C
    freq = data.get("i2c_frequency", STANDARD["i2c_frequency"])
    if not isinstance(freq, int) or isinstance(freq, bool) or not 10000 <= freq <= 1000000:
        errors.append("wiring.json: i2c_frequency should be 100000 or 400000; using 400000")
        freq = 400000

    if not bad_core:
        # each pin once, and not the onboard LED
        used = {}
        led = _onboard_led()
        roles = [("row", n) for n in v["rows"]] + [("column", n) for n in v["cols"]]
        roles += [(key.replace("_", " "), v[key]) for key in SINGLE]
        for role, n in roles:
            if n in used:
                errors.append("wiring.json: GP{} is used for both {} and {}".format(n, used[n], role))
                bad_core = True
            elif n == led:
                errors.append("wiring.json: GP{} ({}) is the onboard LED".format(n, role))
                bad_core = True
            used[n] = role
        sda, scl = v["i2c_sda"], v["i2c_scl"]
        if sda % 2 != 0 or scl % 2 != 1 or (sda >> 1) & 1 != (scl >> 1) & 1:
            errors.append("wiring.json: i2c_sda GP{} and i2c_scl GP{} aren't an SDA / SCL pair on "
                          "one I2C bus".format(sda, scl))
            bad_core = True
        if abs(v["encoder_a"] - v["encoder_b"]) != 1:
            errors.append("wiring.json: encoder_a and encoder_b must be next to each other "
                          "(e.g. GP8 and GP9)")
            bad_core = True
        # add-ons: never on a pin something else uses
        for key in ADDONS:
            n = addons[key]
            if n is None:
                continue
            if n in used or n == led:
                errors.append("wiring.json: {} GP{} is already used ({}); {} turned off".format(
                    key, n, used.get(n, "onboard LED"), key.replace("_", " ")))
                addons[key] = None
            else:
                used[n] = key.replace("_", " ")

    standard_fits = all(_exists(_number(p)) for key in ("rows", "cols") + SINGLE
                        for p in (STANDARD[key] if isinstance(STANDARD[key], tuple) else (STANDARD[key],)))
    if bad_core and not standard_fits:
        # a board without one of the standard pins: they can't stand in
        errors.append("The standard MP1 pins don't all exist on this board, so wiring.json is used "
                      "as it is. Fix it with Toolkit/mp1_workbench.html")
    elif bad_core:
        errors.append("Using the standard MP1 pins for the keys, encoder and screen")
        for key in ("rows", "cols") + SINGLE:
            value = STANDARD[key]
            v[key] = [_number(p) for p in value] if isinstance(value, tuple) else _number(value)
        standard_used = set(v["rows"] + v["cols"] + [v[k] for k in SINGLE])
        for key in ADDONS:
            if addons[key] in standard_used:
                addons[key] = None
    v.update(addons)
    v["oled_address"] = address
    v["i2c_frequency"] = freq
    return v, errors


def _from_old(module):
    """An old wiring.py module -> wiring.json style dict (pin names)."""
    names = {}
    for n in range(48):
        p = getattr(board, "GP{}".format(n), None)
        if p is not None:
            names[id(p)] = "GP{}".format(n)
    data = {}
    for old, key in OLD_NAMES.items():
        if not hasattr(module, old):
            continue
        value = getattr(module, old)
        if isinstance(value, (list, tuple)):
            data[key] = [names.get(id(p), str(p)) for p in value]
        elif key in ("oled_address", "i2c_frequency"):
            data[key] = value
        elif value is None:
            data[key] = None
        else:
            data[key] = names.get(id(value), str(value))
    return data


class Wiring:
    """The pins to use, with the names the old wiring.py had."""

    def __init__(self, values, errors, source):
        gp = lambda n: None if n is None else getattr(board, "GP{}".format(n))
        self.ROWS = tuple(gp(n) for n in values["rows"])
        self.COLS = tuple(gp(n) for n in values["cols"])
        self.ENC_A = gp(values["encoder_a"])
        self.ENC_B = gp(values["encoder_b"])
        self.ENC_SW = gp(values["encoder_button"])
        self.I2C_SDA = gp(values["i2c_sda"])
        self.I2C_SCL = gp(values["i2c_scl"])
        self.OLED_ADDRESS = values["oled_address"]
        self.I2C_FREQUENCY = values["i2c_frequency"]
        self.LED_STRIP_PIN = gp(values["led_strip"])
        self.BUZZER_PIN = gp(values["buzzer"])
        self.values = values
        self.errors = errors
        self.source = source
        self.LED_COUNT, self.BUZZER_TYPE = FACTS["led_count"], FACTS["buzzer_type"]
        self.BUZZER_ACTIVE_LOW, self.ENCODER_DIVISOR = FACTS["buzzer_active_low"], FACTS["encoder_divisor"]
        if self.LED_STRIP_PIN is None:
            self.LED_COUNT = 0
        if self.BUZZER_PIN is None:
            self.BUZZER_TYPE = "none"

    def facts(self, data):
        """The hardware facts from wiring.json (FACTS are the standard MP1 rev 1's)."""
        n = data.get("led_count", FACTS["led_count"])
        if isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 60:
            self.LED_COUNT = n
        else:
            self.errors.append("wiring.json: led_count should be 0-60")
        t = data.get("buzzer_type", FACTS["buzzer_type"])
        if t in ("none", "passive", "active"):
            self.BUZZER_TYPE = t
        else:
            self.errors.append("wiring.json: buzzer_type should be none, passive or active")
        self.BUZZER_ACTIVE_LOW = data.get("buzzer_active_low") is True
        d = data.get("encoder_divisor", FACTS["encoder_divisor"])
        if d in (1, 2, 4):
            self.ENCODER_DIVISOR = d
        else:
            self.errors.append("wiring.json: encoder_divisor should be 1, 2 or 4")
        if self.LED_STRIP_PIN is None:
            self.LED_COUNT = 0
        if self.BUZZER_PIN is None:
            self.BUZZER_TYPE = "none"


def standard():
    values, errors = check({})
    return Wiring(values, errors, "the standard MP1 pins")


def load():
    """Read wiring.json (or an old wiring.py). Never raises: problems are in .errors."""
    if jsfile.exists(WIRING_FILE):
        try:
            data = jsfile.load(WIRING_FILE)
            if not isinstance(data, dict):
                raise ValueError("should be {...}")
        except (OSError, ValueError) as e:
            w = standard()
            w.errors = ["wiring.json is not valid JSON ({}); using the standard MP1 pins".format(e)]
            return w
        values, errors = check(data)
        w = Wiring(values, errors, WIRING_FILE)
        w.facts(data)
        return w
    try:
        import wiring as old            # older firmware: pins in wiring.py
    except ImportError:
        return standard()
    except Exception as e:
        w = standard()
        w.errors = ["wiring.py could not be read ({}); using the standard MP1 pins".format(e)]
        return w
    values, errors = check(_from_old(old))
    return Wiring(values, errors, "wiring.py (old format: convert it with Toolkit/mp1_workbench.html)")
