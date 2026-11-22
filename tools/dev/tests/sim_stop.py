"""Stopping a running macro (actions.py + app.py's stop_wanted), on the PC with stand-ins for the keyboard, keypad,
encoder and button.   py tools/dev/tests/sim_stop.py
"""
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "EMBER_01", "lib")))
sys.modules["supervisor"] = types.SimpleNamespace(ticks_ms=lambda: int(time.monotonic() * 1000) & 0x3FFFFFFF)
kc = types.SimpleNamespace(C=6, CONTROL=224, RIGHT_CONTROL=228, WINDOWS=227, GUI=227, R=21, ENTER=40, M=16)
sys.modules["adafruit_hid"] = types.SimpleNamespace()
sys.modules["adafruit_hid.keycode"] = types.SimpleNamespace(Keycode=kc)


class Event:
    def __init__(self):
        self.key_number, self.pressed = 0, False


class Events(list):
    def get_into(self, e):
        if not self:
            return False
        e.key_number, e.pressed = self.pop(0)
        return True


sys.modules["keypad"] = types.SimpleNamespace(Event=Event)
sys.modules["displayio"] = types.SimpleNamespace()
sys.modules["bitmaptools"] = types.SimpleNamespace()
sys.modules["ember.screen"] = types.SimpleNamespace(picture=None, KEY_LINES=())
sys.modules["ember.gestures"] = types.SimpleNamespace()

from ember import actions as A  # noqa: E402
from ember import app as APP    # noqa: E402

typed = []
kbd = types.SimpleNamespace(press=lambda *k: typed.append(("down",) + k), release=lambda *k: typed.append(("up",) + k),
                            release_all=lambda: typed.append("RELEASE ALL"), send=lambda *k: typed.append(("send",) + k))
layout = types.SimpleNamespace(write=lambda t: typed.append(("text", t)))
mouse = types.SimpleNamespace(release_all=lambda: None)
act = A.Actions(kbd, layout, types.SimpleNamespace(send=lambda c: None), mouse)

# a stand-in App with the real stop methods
app = types.SimpleNamespace(keys=types.SimpleNamespace(events=Events()), encoder=types.SimpleNamespace(position=0), enc_pos=0,
                            button=types.SimpleNamespace(value=True), down_at=[None] * 8, held=[None] * 8, actions=act,
                            screen=types.SimpleNamespace(press=lambda k, d: None, refresh=lambda: None, show_list=lambda *a: None),
                            dirty=False, stop_seen=0, stop_button=False, swallow_button=False, stop_event=None,
                            b_down=False, b_raw=False, b_used=False, b_at=0, b_changed=0, mode=0, mode_until=None,
                            service=lambda now: None)
screens = []
app.screen.show_list = lambda title, lines, *a: screens.append((title, lines))
app.prog_start = app.prog_at = None
app.show = lambda *a: screens.append(("LAYER", []))
for name in ("stop_begin", "stop_wanted", "macro_stopped", "wait", "message", "macro_pause", "macro_progress", "macro_finished", "_prog_text"):
    setattr(app, name, getattr(APP.App, name).__get__(app))
act.wait, act.stop_begin, act.stop_wanted, act.stopped = app.wait, app.stop_begin, app.stop_wanted, app.macro_stopped
act.paused, act.progress, act.finished = app.macro_pause, app.macro_progress, app.macro_finished
# the pause screen's loop waits with time.sleep: here each sleep plays the next button state (True = up)
button_script = []
APP.time = types.SimpleNamespace(sleep=lambda s: setattr(app.button, "value", button_script.pop(0)) if button_script else None)
stops = []
real_stopped = app.macro_stopped
act.stopped = lambda: (stops.append(1), real_stopped())


def macro(steps):
    from ember import keymap         # noqa: F401 (needs adafruit_hid.keycode: packed by hand here instead)
    raise SystemExit


def packed(steps):
    """A macro packed as keymap.py does (key / text / delay only)."""
    out = bytearray(2)
    for kind, v in steps:
        if kind == "key":
            out += bytes((1, v))
        elif kind == "text":
            d = v.encode()
            out += bytes((8, len(d) & 255, len(d) >> 8)) + d
        elif kind == "delay":
            ms = int(v * 1000)
            out += bytes((7, ms & 255, ms >> 8 & 255, ms >> 16 & 255, ms >> 24))
    out[0], out[1] = len(steps) & 255, len(steps) >> 8
    return ("sequence", bytes(out))


def run(name, steps, trigger, after_s=0.05):
    """Run a macro; `trigger` (an input change) happens once after_s seconds of running."""
    typed.clear()
    stops.clear()
    t0 = time.monotonic()
    real = act.check

    def check():
        if trigger and time.monotonic() - t0 > after_s and not getattr(check, "done", False):
            check.done = True
            trigger()
        real()
    act.check = check
    act.press(packed(steps))
    act.check = real
    took = time.monotonic() - t0
    keys = sum(1 for t in typed if isinstance(t, tuple) and t[0] == "down")
    print("{:34} stopped={} keys sent={:3} released all={} took {:.2f}s depth={}".format(
        name, bool(stops), keys, "RELEASE ALL" in typed, took, act.depth))
    return bool(stops), keys


many = [("key", 43)] * 300 + [("delay", 0.02)] * 0
ok = True
s, k = run("no stop: all 300 keys", many, None)
ok &= (not s and k == 300)
s, k = run("a key pressed", many, lambda: app.keys.events.append((3, True)))
ok &= (s and k < 300)
app.encoder.position = 0
app.enc_pos = 0
s, k = run("the encoder turned", many, lambda: setattr(app.encoder, "position", 1))
ok &= (s and k < 300)
s, k = run("during a 3 s wait", [("key", 43), ("delay", 3.0), ("key", 43)], lambda: app.keys.events.append((5, True)), 0.2)
ok &= s and k == 1
s, k = run("during long text", [("text", "x" * 400)], lambda: app.keys.events.append((1, True)), 0.0)
ok &= s
app.button.value = False          # HOLD+KEY: the encoder is already down as it starts
s, k = run("HOLD+KEY: held encoder alone", many, None)
ok &= not s and k == 300
app.button.value = True
# the encoder pressed: a pause; let go, then a click: it goes on and finishes
button_script[:] = [True, True, False, False, True]
s, k = run("encoder pressed: pause, click: go on", many, lambda: setattr(app.button, "value", False))
ok &= (not s and k == 300 and any(t == "PAUSED" for t, _ in screens))
# paused, then a key: stops
screens.clear()
button_script[:] = [True] * 5
s, k = run("paused, then a key: stops", many, lambda: (setattr(app.button, "value", False), app.keys.events.append((4, True))))
ok &= (s and k < 300)
app.button.value = True
# a long macro: the progress screen, then the layer again at the end (from the layer view, as a key press starts it)
app.mode = APP.NORMAL
screens.clear()
s, k = run("long macro: progress shows", [("key", 43)] * 120 + [("delay", 1.0)] + [("key", 43)] * 20, None)
ok &= any(t == "RUNNING" for t, _ in screens) and screens[-1][0] == "LAYER"
print("   progress screens:", [l[0] for t, l in screens if t == "RUNNING"][:3], "... then", screens[-1][0])
app.button.value = True
app.keys.events[:] = [(2, False)]  # the release of the key that started it arrives while it runs
app.down_at[2] = 123
s, k = run("its own key let go: not a stop", many, None)
ok &= (not s and app.down_at[2] is None)
print("\nall passed" if ok else "\nFAILED")
