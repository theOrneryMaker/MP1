# /lib/macropad/menus.py
# Scrolling list menu (layers / settings) and the settings editor used by the
# CONFIG and LIGHTS menus.

from macropad import settings
from macropad.lights import COLOR_NAMES
from macropad.gestures import FUNCTIONS


class ListMenu:
    def __init__(self, items, selection=0):
        self.items = items
        self.selection = selection % len(items) if items else 0

    def navigate(self, step):
        if self.items:
            self.selection = (self.selection + step) % len(self.items)

    def view(self):
        """(prev, current, next) labels."""
        n = len(self.items)
        if not n:
            return "", "", ""
        i = self.selection
        prev = self.items[(i - 1) % n] if n > 1 else ""
        next_ = self.items[(i + 1) % n] if n > 2 else ""
        return prev, self.items[i], next_


# Item kinds
NUM, CHOICE, BOOL = 0, 1, 2

# (settings key, display name, kind, details)
#   NUM:    (step, min, max) or (step, min, max, text shown for 0)
#   CHOICE: ((value, label), ...)
#   BOOL:   None
CONFIG_ITEMS = (
    ("long_press_duration", "LONG PRESS", NUM, (0.1, 0.5, 3.0)),
    ("medium_press_duration", "MED PRESS", NUM, (0.05, 0.1, 1.0)),
    ("secret_timeout", "SECRET T O", NUM, (1, 5, 60)),
    ("menu1_timeout", "LAYERS T O", NUM, (1, 3, 30)),
    ("menu2_timeout", "SETTINGS T O", NUM, (1, 5, 60)),
    ("encoder_speed_fast", "ENC SP FS", NUM, (0.01, 0.01, 0.1)),
    ("encoder_multiplier_fast", "ENC * FS", NUM, (1, 1, 10)),
    ("encoder_speed_medium", "ENC SP MD", NUM, (0.01, 0.02, 0.2)),
    ("encoder_multiplier_medium", "ENC * MD", NUM, (1, 1, 5)),
    ("repeat_delay", "RPT DELAY", NUM, (0.05, 0.1, 2.0)),       # held keys with "repeat": true
    ("repeat_rate", "RPT RATE", NUM, (1, 1, 30)),               # repeats per second
    ("confirm_time", "CONFIRM T", NUM, (0.1, 0.2, 3.0)),        # keys with "confirm": true
    ("menu_roll_time", "ROLL TIME", NUM, (0.02, 0.0, 0.4)),     # 0 = no rolling animation
    ("menu_roll_steps", "ROLL STEPS", NUM, (1, 1, 8)),
)

GESTURE_ITEMS = (
    ("gesture_double", "DOUBLE CLK", CHOICE, FUNCTIONS),
    ("gesture_triple", "TRIPLE CLK", CHOICE, FUNCTIONS),
    ("gesture_hold_cw", "HOLD CW", CHOICE, FUNCTIONS),
    ("gesture_hold_ccw", "HOLD CCW", CHOICE, FUNCTIONS),
    ("gesture_click_hold_cw", "C+HOLD CW", CHOICE, FUNCTIONS),      # click, then hold + turn
    ("gesture_click_hold_ccw", "C+HOLD CCW", CHOICE, FUNCTIONS),
    ("multi_click_time", "CLICK TIME", NUM, (0.05, 0.15, 0.6)),
    ("hold_turn_threshold", "HOLD TURN", NUM, (1, 1, 10)),
    ("hold_gesture_min_duration", "HOLD MIN", NUM, (0.1, 0.1, 1.0)),
)

SCREEN_ITEMS = (
    ("screen_dim_minutes", "DIM AFTER", NUM, (1, 0, 120, "NEVER")),     # minutes idle
    ("screen_off_minutes", "OFF AFTER", NUM, (1, 0, 240, "NEVER")),
    ("screen_dim_level", "DIM LEVEL", NUM, (0.05, 0.05, 1.0)),
    ("screen_off_leds", "LEDS OFF", BOOL, None),                       # LEDs dark with the screen
    ("caps_box", "CAPS BOX", BOOL, None),                              # Caps Lock indicator
    ("caps_flash", "CAPS FLASH", BOOL, None),
)

SOUND_ITEMS = (
    ("sound_keys", "KEY CLICK", BOOL, None),
    ("sound_layers", "LAYER TONE", BOOL, None),
    ("sound_startup", "START TONE", BOOL, None),
    ("buzzer_volume", "BEEP VOL", NUM, (0.1, 0.1, 1.0)),     # passive buzzers only
    ("buzzer", "BUZZER", CHOICE, (("none", "NONE"), ("passive", "PASSIVE"), ("active", "ACTIVE"))),
)

_COLOR_CHOICES = tuple((name, name.replace("_", " ")) for name in COLOR_NAMES)
LIGHT_ITEMS = (
    ("led_scene", "SCENE", CHOICE, (
        ("off", "OFF"), ("static", "STATIC"), ("breathing", "BREATHING"), ("reactive", "REACTIVE"),
        ("pulse", "PULSE"), ("twinkle", "TWINKLE"), ("lightning", "LIGHTNING"), ("strobe", "STROBE"),
        ("rainbow", "RAINBOW"), ("cycle", "CYCLE"))),
    ("led_color1", "COLOR 1", CHOICE, _COLOR_CHOICES),
    ("led_color2", "COLOR 2", CHOICE, _COLOR_CHOICES),
    ("led_brightness", "BRIGHTNESS", NUM, (0.05, 0.05, 1.0)),
    ("led_speed", "SPEED", NUM, (1, 1, 10)),
    ("led_count", "LED COUNT", NUM, (1, 0, 60)),        # 0 = no strip fitted
)

RESET, EXIT = "RESET", "EXIT"


class ConfigMenu(ListMenu):
    """Turn to pick a setting, press to edit, turn to change, press to save.
    With live=True the change is applied while you turn (e.g. to preview lights)
    and undone if the menu times out before you press."""

    # Settings that restart hardware: applied when saved, never previewed live
    RESTART_KEYS = ("led_count", "buzzer")

    def __init__(self, cfg, entries, live=False, on_saved=None):
        super().__init__([e[1] for e in entries] + ["RESET DFLT", "EXIT"])
        self.cfg = cfg
        self.entries = entries
        self.live = live
        self.on_saved = on_saved or (lambda keys: None)     # told which keys were saved
        self.editing = False
        self.value = None
        self.original = None
        self.save_failed = False        # last save couldn't write settings.js (USB drive visible)

    def _entry(self):
        return self.entries[self.selection] if self.selection < len(self.entries) else None

    def current_key(self):
        entry = self._entry()
        return entry[0] if entry else None

    def adjust(self, direction):
        key, _, kind, details = self._entry()
        if kind == BOOL:
            self.value = not self.value
        elif kind == CHOICE:
            values = [v for v, _ in details]
            i = values.index(self.value) if self.value in values else 0
            self.value = values[(i + direction) % len(values)]
        else:
            step, lo, hi = details[:3]
            value = max(lo, min(hi, self.value + direction * step))
            self.value = int(value) if step >= 1 else round(value, 2)
        if self.live and key not in self.RESTART_KEYS:
            self.cfg[key] = self.value

    def press(self):
        """Returns RESET, EXIT, or None (edit started / value saved)."""
        entry = self._entry()
        if entry is None:
            if self.selection == len(self.entries):
                defaults = settings.defaults()
                for e in self.entries:
                    self.cfg[e[0]] = defaults[e[0]]
                self.save_failed = not settings.save(self.cfg)
                self.on_saved([e[0] for e in self.entries])
                return RESET
            return EXIT
        self.save_failed = False
        if self.editing:
            self.cfg[entry[0]] = self.value
            self.save_failed = not settings.save(self.cfg)
            self.editing = False
            self.on_saved([entry[0]])
        else:
            self.original = self.value = self.cfg[entry[0]]
            self.editing = True
        return None

    def cancel(self):
        """Menu closed mid-edit: undo a live preview."""
        if self.editing and self.live:
            self.cfg[self._entry()[0]] = self.original
        self.editing = False

    def value_text(self):
        _, _, kind, details = self._entry()
        if kind == BOOL:
            return "ON" if self.value else "OFF"
        if kind == CHOICE:
            for value, label in details:
                if value == self.value:
                    return label
            return str(self.value)
        if len(details) > 3 and self.value == 0:
            return details[3]
        if isinstance(self.value, float):
            return "{:.2f}".format(self.value).rstrip("0").rstrip(".")
        return str(self.value)
