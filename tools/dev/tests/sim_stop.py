"""Stopping and pausing a running macro (actions.py + app.py stop_wanted / macro_pause: hold the encoder to stop, click to
pause, turn while paused to pick a CSV row), on the PC with stand-ins for the keyboard, keypad,
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
app.cfg = {"encoder_reverse": False}
# the pause screen's loop waits with time.sleep: here each sleep plays the next scripted thing: a button state
# (True = up) or a function (e.g. a turn)
script = []


def fake_sleep(sec):
    if script:
        x = script.pop(0)
        x() if callable(x) else setattr(app.button, "value", x)


APP.time = types.SimpleNamespace(sleep=fake_sleep)
stops = []
real_stopped = app.macro_stopped
act.stopped = lambda: (stops.append(1), real_stopped())


def packed(steps):
    """A macro packed as keymap.py does (key / text / delay / mark only)."""
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
        elif kind == "mark":
            out += bytes((17, v[0] & 255, v[0] >> 8, v[1] & 255, v[1] >> 8))
    out[0], out[1] = len(steps) & 255, len(steps) >> 8
    return ("sequence", bytes(out))


def run(name, steps, triggers=()):
    """Run a macro; each trigger (seconds, function) happens once that long after it started."""
    typed.clear()
    stops.clear()
    t0 = time.monotonic()
    real = act.check
    left = list(triggers)

    def check():
        while left and time.monotonic() - t0 > left[0][0]:
            left.pop(0)[1]()
        real()
    act.check = check
    act.press(packed(steps))
    act.check = real
    took = time.monotonic() - t0
    keys = sum(1 for t in typed if isinstance(t, tuple) and t[0] == "down")
    print("{:40} stopped={} keys sent={:3} took {:.2f}s".format(name, bool(stops), keys, took))
    return bool(stops), keys


down = lambda: setattr(app.button, "value", False)
up = lambda: setattr(app.button, "value", True)
many = [("key", 43)] * 300
ok = True
s, k = run("no stop: all 300 keys", many)
ok &= (not s and k == 300)
s, k = run("a key pressed: does nothing now", many, [(0.05, lambda: app.keys.events.append((3, True)))])
ok &= (not s and k == 300)
s, k = run("the encoder turned: does nothing now", many, [(0.05, lambda: setattr(app.encoder, "position", app.encoder.position + 1))])
ok &= (not s and k == 300)
s, k = run("encoder held 1 s: stops", many, [(0.05, down)])
ok &= (s and 30 < k < 300)
up()
s, k = run("held during a 3 s wait: stops", [("key", 43), ("delay", 3.0), ("key", 43)], [(0.2, down)])
ok &= s and k == 1
up()
app.button.value = False          # HOLD+KEY: the encoder is already down as it starts
s, k = run("HOLD+KEY: held encoder alone", many)
ok &= not s and k == 300
up()
# a click: a pause; then a click: it goes on and finishes
script[:] = [True, False, False, True]
screens.clear()
s, k = run("click: pause, click: go on", many, [(0.05, down), (0.12, up)])
ok &= (not s and k == 300 and any(t == "PAUSED" for t, _ in screens))
# paused, then held: stops
script[:] = [True] + [False] * 5
s, k = run("paused, then held: stops", many, [(0.05, down), (0.12, up)])
ok &= (s and k < 300)
up()
# a CSV macro (rows 1-5): paused in row 4, turned back 2 (row 2), click: rows 2-5 again
rows = []
for r in range(1, 6):
    rows += [("mark", (r, 5)), ("text", "r%d" % r)] + [("key", 43)] * 4
turn_left = lambda: setattr(app.encoder, "position", app.encoder.position - 1)
script[:] = [True, turn_left, turn_left, False, True]
screens.clear()
s, k = run("paused in row 4, back 2 rows, go on", rows, [(0.30, down), (0.35, up)])
texts = [t[1] for t in typed if isinstance(t, tuple) and t[0] == "text"]
paused = [l for t, l in screens if t == "PAUSED"]
print("   typed:", " ".join(texts), "| paused screen:", paused[0][1], "->", paused[-1][1])
ok &= (not s and texts[-4:] == ["r2", "r3", "r4", "r5"] and texts.count("r2") == 2 and "From row 2 of 5" in paused[-1][1])
# a long macro: the progress screen, then the layer again at the end (from the layer view, as a key press starts it)
app.mode = APP.NORMAL
screens.clear()
s, k = run("long macro: progress shows", [("key", 43)] * 120 + [("delay", 1.0)] + [("key", 43)] * 20)
ok &= any(t == "RUNNING" for t, _ in screens) and screens[-1][0] == "LAYER"
print("   progress screens:", [l[0] for t, l in screens if t == "RUNNING"][:3], "... then", screens[-1][0], "| says:", [l[3] for t, l in screens if t == "RUNNING"][:1])
app.keys.events[:] = [(2, False)]  # the release of the key that started it arrives while it runs
app.down_at[2] = 123
s, k = run("its own key let go: not a stop", many)
ok &= (not s and app.down_at[2] is None)
print("\nall passed" if ok else "\nFAILED")
