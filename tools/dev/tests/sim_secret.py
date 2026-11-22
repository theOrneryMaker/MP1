"""Secret layers on the pad side (app.py toggle_secret / secret_timeout / regular_index, link.py view), with the
real code and stand-ins for the screen and keymap.   py tools/dev/tests/sim_secret.py
"""
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "EMBER_01", "lib")))
sys.modules["supervisor"] = types.SimpleNamespace(ticks_ms=lambda: int(time.monotonic() * 1000) & 0x3FFFFFFF)
for m in ("displayio", "bitmaptools", "keypad"):
    sys.modules[m] = types.SimpleNamespace()
sys.modules["ember.screen"] = types.SimpleNamespace(picture=None, KEY_LINES=())
sys.modules["ember.gestures"] = types.SimpleNamespace()
sys.modules["adafruit_hid"] = types.SimpleNamespace()
sys.modules["adafruit_hid.keycode"] = types.SimpleNamespace(Keycode=types.SimpleNamespace())
sys.modules["usb_cdc"] = types.SimpleNamespace()

from ember import app as APP, clock    # noqa: E402
from ember.layers import Keymap        # noqa: E402
from ember import link as LINK         # noqa: E402

names = ("EXCEL", "WEBEX", "MEDIA")
km = Keymap(names, b"", (0,) * 8, 2, 3, ("a", "b", "c"), (4, 5), ("LOGINS", "VAULT"))
shown, msgs = [], []
layer = types.SimpleNamespace(name="", present=[True] * 8, labels=["k"] * 8, pics=[None] * 8, enc_label="e")
km.layer = lambda i: types.SimpleNamespace(**dict(vars(layer), name=km.name_of(i)))
app = types.SimpleNamespace(km=km, index=2, prev_index=2, mode=APP.NORMAL, cfg={"secret_lock_seconds": 1}, last_input=clock.now(), HOLD=APP.HOLD)
app.show = lambda i=None: (shown.append(km.name_of(i if i is not None else app.index)), setattr(app, "index", i if i is not None else app.index), setattr(app, "layer", km.layer(app.index)))
app.message = lambda t, l, ms=0: msgs.append(t)
for n in ("toggle_secret", "secret_turn", "secret_timeout", "regular_index"):
    setattr(app, n, getattr(APP.App, n).__get__(app))
app.layer = km.layer(2)
ok = True


def check(name, cond, info=""):
    global ok
    print(("ok   " if cond else "FAIL ") + name, info)
    ok &= bool(cond)


app.toggle_secret(1)
check("Secret pages opens page 1", app.index == 4 and shown[-1] == "LOGINS", shown[-1])
check("picker / layer keys use the layer before", app.regular_index() == 2)
view = LINK.Link.view(types.SimpleNamespace(app=app))
check("the page sees only SECRET", view[0] == "SECRET" and view[1] == [None] * 8 and view[2] == "", view[:3])
app.secret_turn(1)
check("turn right: page 2", app.index == 5 and shown[-1] == "VAULT", shown[-1])
app.secret_turn(1)
check("turn right again: wraps to page 1", app.index == 4)
app.secret_turn(-1)
check("turn left: page 2", app.index == 5)
check("still goes back to MEDIA", app.prev_index == 2)
app.toggle_secret(1)
check("the function again closes them", app.index == 2 and shown[-1] == "MEDIA", shown[-1])
app.toggle_secret(2)
check("Secret page 2 opens page 2", app.index == 5)
app.toggle_secret(1)
app.toggle_secret(1)
app.last_input = clock.add(clock.now(), -500)
app.secret_timeout(clock.now())
check("still open before the lock time", app.index == 4)
app.last_input = clock.add(clock.now(), -1500)
app.secret_timeout(clock.now())
check("closes after the lock time (1 s)", app.index == 2, shown[-1])
app.cfg["secret_lock_seconds"] = 0
app.toggle_secret(1)
app.last_input = clock.add(clock.now(), -600000)
app.secret_timeout(clock.now())
check("lock time 0 = never closes", app.index == 4)
km.SECRET, km.SECRET_NAMES = (4,), ("LOGINS",)
app.index = 2
app.toggle_secret(2)
check("Secret page 2 with one page: page 1", app.index == 4)
app.secret_turn(1)
check("one page: turning stays", app.index == 4)
km.SECRET = ()
app.index = 2
app.toggle_secret(1)
check("none: a message", msgs[-1] == "SECRET" and app.index == 2)
app.index = 1
view = LINK.Link.view(types.SimpleNamespace(app=app))
check("a regular layer: its name", view[0] == "WEBEX", view[0])
print("all passed" if ok else "FAILED")
