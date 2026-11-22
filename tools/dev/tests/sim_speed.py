"""Typing speed (the "type_speed" setting and a key's own "speed"), with the real keymap.py / layers.py / actions.py and
stand-ins for the keyboard and the clock: packed and unpacked, a text typed a character at a time with pauses
(careful / slow), the gap between macro steps, a key's own speed over the setting, a bad speed refused, stopping part
way.   py tools/dev/tests/sim_speed.py
"""
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "EMBER_01", "lib")))
import sim_display  # noqa: E402,F401
sys.modules["adafruit_hid"] = types.SimpleNamespace()
sys.modules["adafruit_hid.keycode"] = types.SimpleNamespace(Keycode=types.SimpleNamespace(TAB=43, C=6, CONTROL=224, RIGHT_CONTROL=228,
                                                                                         WINDOWS=227, R=21, ENTER=40))
from ember import keymap, layers, actions as A  # noqa: E402

ok = True


def check(name, cond, info=""):
    global ok
    print(("ok   " if cond else "FAIL ") + name, info)
    ok &= bool(cond)


# packing
keys = [{"label": "Order", "text": "abc", "speed": "slow"}, {"label": "Fast", "text": "x"}, {"label": "Careful", "text": "y", "speed": "careful"}]
L = layers.unpack("T", memoryview(bytes(keymap._pack_layer({"ember": "layer", "name": "T", "keys": keys}, "T"))))
check("a key's own speed packs and unpacks", L.speed[:3] == ["slow", None, "careful"] and L.labels[0] == "Order", L.speed[:3])
keymap.ERRORS[:] = []
keymap._pack_layer({"ember": "layer", "name": "B", "keys": [{"label": "X", "text": "x", "speed": "warp"}]}, "B")
check("an unknown speed is refused", keymap.ERRORS and "speed" in keymap.ERRORS[-1], keymap.ERRORS[-1:])

# typing, with a fake keyboard layout and sleep
sleeps, typed = [], []
real_sleep = time.sleep
A.time = types.SimpleNamespace(sleep=lambda s: sleeps.append(s))
kbd = types.SimpleNamespace(press=lambda *k: typed.append(("press", k)), release=lambda *k: typed.append(("release", k)), send=lambda *k: None,
                            release_all=lambda: None)
mouse = types.SimpleNamespace(release_all=lambda: None)
layout = types.SimpleNamespace(write=lambda t: typed.append(t))
act = A.Actions(kbd, layout, types.SimpleNamespace(send=lambda c: None), mouse)
cfg = {"type_speed": "normal"}
act.cfg = cfg
act.press(("text", "hello world"))
check("normal: typed in one piece, no pauses", typed == ["hello world"] and not sleeps, typed)
typed.clear()
cfg["type_speed"] = "careful"
act.press(("text", "hello"))
check("careful (the setting): one character at a time, 15 ms after each", typed == list("hello") and sleeps == [0.015] * 5, sleeps)
typed.clear(); sleeps.clear()
act.press(("text", "ab"), "slow")
check("a key's own slow beats the setting", typed == ["a", "b"] and sleeps == [0.04, 0.04], sleeps)
typed.clear(); sleeps.clear()
cfg["type_speed"] = "normal"
seq = keymap.parse_action({"sequence": [{"text": "PN-1"}, {"key": "TAB"}, {"text": "12"}]}, "m")
act.press(seq, "careful")
check("a macro, careful: its text a character at a time", "".join(t for t in typed if isinstance(t, str)) == "PN-112" and typed[0] == "P")
check("... and 60 ms between the steps", sleeps.count(0.06) == 3, sleeps)
typed.clear(); sleeps.clear()
act.press(seq)
check("the same macro at normal: 10 ms gaps, text in one piece", sleeps.count(0.01) >= 3 and "PN-1" in typed, sleeps)
# stopping part way through a slow text
typed.clear(); sleeps.clear()
n = [0]
act.stop_wanted = lambda: (n.__setitem__(0, n[0] + 1), n[0] > 3)[1]
stopped = []
act.stopped = lambda: stopped.append(1)
act.press(("text", "abcdefghij"), "slow")
check("stopped part way: only a few characters typed", 1 <= len(typed) <= 4 and stopped, typed)
A.time = time
print("all passed" if ok else "FAILED")
