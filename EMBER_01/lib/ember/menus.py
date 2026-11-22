# ember/menus.py - the TOOLS menu (long press) and its settings lists. Loaded only while the menu is
# open (App.open_tools / App.close_menu), so it costs no memory the rest of the time.
#
# Turn = move; click a setting = change it in its row (turn, click again when done); on / off
# settings flip with one click. Changes apply at once and are saved when the menu closes.
# The last row, BACK, returns to TOOLS. Holding the encoder closes the menu.

from ember import gestures
from ember.settings import SETTINGS, SOUND_PARTS

GROUPS = (
    ("Encoder", ("click_single", "click_double", "click_triple", "hold_turn_right", "hold_turn_left",
                 "encoder_reverse")),
    ("Keys & screen", ("repeat_speed", "key_lines", "screen_dim_minutes", "screen_off_minutes", "lock_boxes")),
    ("Lights", ("light_scene", "light_color1", "light_color2", "light_level", "lights_asleep")),
    ("Sound", ("sounds", "sound_level")),
    ("Other", ("secret_lock_seconds", "jiggle_at_start")),
)
LABELS = {
    "click_single": "Click", "click_double": "Double click", "click_triple": "Triple click",
    "hold_turn_right": "Hold + turn R", "hold_turn_left": "Hold + turn L", "encoder_reverse": "Reverse",
    "repeat_speed": "Key repeat", "key_lines": "Key lines", "screen_dim_minutes": "Dim after",
    "screen_off_minutes": "Off after", "lock_boxes": "Caps / Num",
    "light_scene": "Scene", "light_color1": "Color 1", "light_color2": "Color 2", "light_level": "Brightness",
    "lights_asleep": "While asleep", "sounds": "Sounds", "sound_level": "Volume",
    "secret_lock_seconds": "Secret lock", "jiggle_at_start": "Jiggle at start",
}
STEP = {"screen_dim_minutes": 1, "screen_off_minutes": 5, "secret_lock_seconds": 5}
FUNCTION_SETTINGS = ("click_single", "click_double", "click_triple", "hold_turn_right", "hold_turn_left")
# TOOLS: (label, what) - a group number, or a function name the app runs
TOP = ("Timer", "Counter", "Busy light", "Settings", "Mouse jiggle", "Lock keys", "Drive", "About", "Exit")


def _choices(name):
    if name == "click_single":
        return gestures.SINGLE_CLICK
    if name in FUNCTION_SETTINGS:
        return gestures.NAMES
    if name == "light_scene":
        from ember.lights import SCENES
        return SCENES
    if name in ("light_color1", "light_color2"):
        from ember.lights import COLOR_NAMES
        return COLOR_NAMES
    return SETTINGS[name][1]


def value_text(name, value):
    if isinstance(value, bool):
        return "On" if value else "Off"
    if name in FUNCTION_SETTINGS:
        return gestures.label(value)
    if name in ("screen_dim_minutes", "screen_off_minutes"):
        return "Never" if not value else "{} min".format(value)
    if name == "secret_lock_seconds":
        return "Never" if not value else "{} s".format(value)
    if isinstance(value, str):
        v = value.replace("_", " ")
        return v[:1].upper() + v[1:].lower()
    return str(value)


class Menu:
    def __init__(self, cfg, has_lights, has_sound):
        self.cfg = cfg
        self.groups = [g for g in GROUPS if (g[0] != "Lights" or has_lights) and (g[0] != "Sound" or has_sound)]
        self.where = None                   # None = TOOLS, "settings" = the group list, or a group number
        self.sel = 0
        self.editing = False
        self.changed = False
        self.bit = 0                        # editing "sounds": which switch (len(SOUND_PARTS) = Done)

    def view(self, state):
        """(title, rows, selected row, right title). state(name): the value shown for a TOOLS row."""
        if self.where is None:
            rows = [(t, state(t)) for t in TOP]
            return "TOOLS", rows, self.sel, ""
        if self.where == "settings":
            return "SETTINGS", [g[0] for g in self.groups] + ["Back"], self.sel, ""
        title, names = self.groups[self.where]
        rows = []
        for i, n in enumerate(names):
            v = value_text(n, self.cfg[n])
            if self.editing and i == self.sel and n == "sounds":     # Boot [1]001 ... Done
                b, k = self.cfg[n], self.bit
                rows.append((SOUND_PARTS[k] if k < len(SOUND_PARTS) else "Done",
                             b[:k] + "[" + b[k] + "]" + b[k + 1:] if k < len(SOUND_PARTS) else "< " + b + " >"))
                continue
            rows.append((LABELS[n], "< " + v + " >" if self.editing and i == self.sel else v))
        return title.upper(), rows + ["Back"], self.sel, ""

    def count(self):
        if self.where is None:
            return len(TOP)
        if self.where == "settings":
            return len(self.groups) + 1
        return len(self.groups[self.where][1]) + 1

    def turn(self, step):
        if self.editing:
            name = self.groups[self.where][1][self.sel]
            if name == "sounds":            # (turning moves between the switches; a click flips one)
                self.bit = (self.bit + step) % (len(SOUND_PARTS) + 1)
                return None
            value = self.cfg[name]
            allowed = _choices(name)
            if isinstance(value, int) and not isinstance(value, bool):
                self.cfg[name] = max(allowed[0], min(allowed[1], value + step * STEP.get(name, 1)))
            else:
                i = allowed.index(value) if value in allowed else 0
                self.cfg[name] = allowed[(i + step) % len(allowed)]
            self.changed = True
            return name
        self.sel = (self.sel + step) % self.count()
        return None

    def click(self):
        """What the click did: None (stays in the menu), a TOOLS row's label, a changed setting's
        name (prefixed "set:"), or "exit"."""
        if self.where is None:
            label = TOP[self.sel]
            if label == "Settings":
                self.where, self.sel = "settings", 0
                return None
            return "exit" if label == "Exit" else label
        if self.where == "settings":
            if self.sel == len(self.groups):
                self.where, self.sel = None, 0
            else:
                self.where, self.sel = self.sel, 0
            return None
        names = self.groups[self.where][1]
        if self.sel == len(names):          # Back
            self.sel = [g for g in self.groups].index(self.groups[self.where])
            self.where = "settings"
            self.editing = False
            return None
        name = names[self.sel]
        if name == "sounds":
            if not self.editing:
                self.editing, self.bit = True, 0
                return None
            if self.bit == len(SOUND_PARTS):  # Done
                self.editing = False
                return None
            b = self.cfg[name]
            self.cfg[name] = b[:self.bit] + ("0" if b[self.bit] == "1" else "1") + b[self.bit + 1:]
            self.changed = True
            return "set:" + name
        if isinstance(self.cfg[name], bool):
            self.cfg[name] = not self.cfg[name]
            self.changed = True
            return "set:" + name
        self.editing = not self.editing
        return None
