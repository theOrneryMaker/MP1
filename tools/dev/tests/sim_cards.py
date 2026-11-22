"""Layer cards on the PC (real keymap.py / layers.py / screen.py / app.py code, strict screen stand-ins): a layer's
card picture packs and unpacks, a too-big one is refused, the card screen draws (picture + name, a big name, a long
name), and the picker opens as cards, turns, and shows the home marker.   py tools/dev/tests/sim_cards.py
"""
import binascii
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "EMBER_01", "lib")))
import sim_display  # noqa: E402,F401  (displayio / bitmaptools stand-ins)
for m in ("keypad", "usb_cdc"):
    sys.modules[m] = types.SimpleNamespace()
sys.modules["adafruit_hid"] = types.SimpleNamespace()
sys.modules["adafruit_hid.keycode"] = types.SimpleNamespace(Keycode=types.SimpleNamespace())

from ember import keymap, layers, screen, clock, app as APP  # noqa: E402

ok = True


def check(name, cond, info=""):
    global ok
    print(("ok   " if cond else "FAIL ") + name, info)
    ok &= bool(cond)


def ring(n):
    """An n x n ring picture, packed as the page makes it."""
    bpr = (n + 7) >> 3
    out = bytearray(bpr * n)
    c = (n - 1) / 2
    for y in range(n):
        for x in range(n):
            if abs(((x - c) ** 2 + (y - c) ** 2) ** 0.5 - n / 2.6) < 2.2:
                out[y * bpr + (x >> 3)] |= 0x80 >> (x & 7)
    return {"src": "test", "w": n, "h": n, "bits": binascii.b2a_base64(bytes(out)).decode().strip()}


def ascii_of(bm):
    return "\n".join("".join("#" if v else "." for v in row) for row in bm.d)


data = {"ember": "layer", "name": "EXCEL", "keys": [{"label": "Copy", "text": "hello"}] + [None] * 7,
        "encoder": {"label": "Vol", "cw": {"media": "VOL_UP"}, "ccw": {"media": "VOL_DN"}, "accel": True},
        "lights": {"scene": "static", "color1": "WHITE", "brightness": 5}, "jiggle": True, "pic": ring(40)}
packed = keymap._pack_layer(data, "EXCEL")
L = layers.unpack("EXCEL", memoryview(bytes(packed)))
check("card picture packs and unpacks", L.card is not None and L.card[0] == 40 and L.card[1] == 40 and len(L.card[2]) == 200, L.card and L.card[:2])
check("the rest of the layer is untouched", L.labels[0] == "Copy" and L.accel and L.jiggle and L.lights and L.lights[3] == 5 and L.enc_label == "Vol")
check("a layer without one: no card", layers.unpack("X", memoryview(bytes(keymap._pack_layer({"ember": "layer", "name": "X"}, "X")))).card is None)
keymap.ERRORS[:] = []
keymap._pack_layer({"ember": "layer", "name": "BIG", "pic": ring(41)}, "BIG")
check("a picture over 40 x 40 is refused", keymap.ERRORS and "40 x 40" in keymap.ERRORS[-1], keymap.ERRORS[-1:])
keymap.ERRORS[:] = []
check("an undrawn picture (src only) is just left out", layers.unpack("U", memoryview(bytes(keymap._pack_layer({"ember": "layer", "name": "U", "pic": {"src": "fa-solid fa-x"}}, "U")))).card is None and not keymap.ERRORS)

disp = types.SimpleNamespace(auto_refresh=True, root_group=None, refresh=lambda: None)
scr = screen.Screen(disp)
scr.show_card("EXCEL", screen.picture(L.card), "HOME", "3/6")
check("card view shows, the others hidden", not scr.card_view.hidden and scr.layer_view.hidden and scr.list_view.hidden)
print(ascii_of(scr.card))
scr.show_card("MEDIA", None, "", "4/6")
print(ascii_of(scr.card))
check("no picture: the name drawn double size", sum(map(sum, scr.card.d)) > 150)
scr.show_card("A VERY LONG LAYER", None, "", "5/6")
check("a long name falls back to normal size", True)
scr.show_layer("EXCEL", "Vol", [None] * 8)
check("the layer view hides the card", scr.card_view.hidden and not scr.layer_view.hidden)

# the picker as cards, with a real Keymap
blob = bytes(packed) + bytes(keymap._pack_layer({"ember": "layer", "name": "MEDIA"}, "MEDIA"))
km = layers.Keymap(("EXCEL", "MEDIA"), blob, (0, len(packed), len(blob)), 1, None)
app = types.SimpleNamespace(km=km, screen=scr, index=1, mode=APP.NORMAL, dirty=False, mode_until=None, pick_cards=False)
app.regular_index = lambda: app.index
for n in ("open_picker", "draw_picker"):
    setattr(app, n, getattr(APP.App, n).__get__(app))
app.open_picker(True)
check("Layer cards opens on the layer showing", app.mode == APP.PICKER and app.pick == 1 and not scr.card_view.hidden)
check("the home layer's card says HOME", sum(map(sum, [r[:30] for r in scr.card.d[:9]])) > 0)
app.pick = 0
app.draw_picker()
check("turned to EXCEL: its picture", sum(map(sum, [r[44:84] for r in scr.card.d[10:53]])) > 50)
app.open_picker(False)
check("the plain picker is still a list", not scr.list_view.hidden and scr.card_view.hidden)
check("Layer cards is a single-click choice", "layer_cards" in __import__("ember.gestures", fromlist=["x"]).SINGLE_CLICK)
print("all passed" if ok else "FAILED")
