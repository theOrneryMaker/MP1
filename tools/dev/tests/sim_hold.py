"""The HOLD+KEY screen on the PC (real screen.py / app.py code, strict screen stand-ins): it shows inverted (black on
white), a key flash still shows the other way round, the normal layer view goes back to white on black, and its keys
are made once and kept until the keymap changes.   py tools/dev/tests/sim_hold.py
"""
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "EMBER_01", "lib")))
import sim_display  # noqa: E402,F401
for m in ("keypad", "usb_cdc"):
    sys.modules[m] = types.SimpleNamespace()
sys.modules["adafruit_hid"] = types.SimpleNamespace()
sys.modules["adafruit_hid.keycode"] = types.SimpleNamespace(Keycode=types.SimpleNamespace())

from ember import keymap, layers, screen, app as APP  # noqa: E402

ok = True


def check(name, cond, info=""):
    global ok
    print(("ok   " if cond else "FAIL ") + name, info)
    ok &= bool(cond)


WHITE, BLACK = 0xFFFFFF, 0x000000
scr = screen.Screen(types.SimpleNamespace(auto_refresh=True, root_group=None, refresh=lambda: None))
keys = [("SNIP", None), ("XCEL", None)] + [None] * 6
scr.show_layer("HOLD+KEY", "", keys, True)
check("HOLD+KEY: background white", scr.back_pal[0] == WHITE and scr.back_pal[1] == BLACK)
check("HOLD+KEY: keys black on white", all(p[0] == WHITE and p[1] == BLACK for p in scr.palettes))
scr.press(0, True)
check("a press there flashes the other way (white on black)", scr.palettes[0][0] == BLACK and scr.palettes[0][1] == WHITE)
scr.press(0, False)
check("and back", scr.palettes[0][0] == WHITE)
scr.show_layer("EXCEL", "Vol", keys)
check("the layer view: white on black again", scr.back_pal[0] == BLACK and all(p[0] == BLACK for p in scr.palettes))
scr.press(1, True)
check("a normal press: inverted cell", scr.palettes[1][0] == WHITE)

hold = bytes(keymap._pack_layer({"keys": [{"label": "SNIP", "text": "x"}, {"label": "XCEL", "text": "y"}]}, "HOLD+KEY"))
main = bytes(keymap._pack_layer({"ember": "layer", "name": "EXCEL"}, "EXCEL"))
km = layers.Keymap(("EXCEL",), main + hold, (0, len(main), len(main) + len(hold)), 0, 1)
unpacks = []
real = layers.unpack
layers.unpack = lambda n, d: (unpacks.append(n), real(n, d))[1]
app = types.SimpleNamespace(km=km, index=0, hold_view=None, layer=None)
app.hold_keys = APP.App.hold_keys.__get__(app)
k1 = app.hold_keys()
k2 = app.hold_keys()
check("the keys are made once", k1 is k2 and unpacks.count("HOLD+KEY") == 1, unpacks)
check("they're the HOLD+KEY keys", k1[0][0] == "SNIP" and k1[1][0] == "XCEL" and k1[2] is None)
check("the layer showing is unpacked again after", app.layer is not None and app.layer.name == "EXCEL")
km.replace(1, bytes(keymap._pack_layer({"keys": [{"label": "NEW", "text": "z"}]}, "HOLD+KEY")))
app.hold_view = None                    # (link.change does this)
check("a changed HOLD+KEY is made again", app.hold_keys()[0][0] == "NEW")
check("HOLD_SCREEN is sooner (150 ms)", APP.HOLD_SCREEN == 150)
# hold-to-confirm keys: the corner mark, the bar filling as it's held, the key going at CONFIRM, letting go early
scr.show_layer("EXCEL", "Vol", [("Submit", None, True), ("Copy", None, False)] + [None] * 6)
cell = scr.cells[0]
check("a hold-to-confirm key: the corner mark", cell[26, 1] and cell[29, 1] and cell[29, 4] and not cell[28, 4] and not scr.cells[1][29, 1])
taps = []
from ember import clock
t0 = clock.now()
layer = types.SimpleNamespace(keys=[("text", "x")] + [None] * 7, confirm=[True] + [False] * 7, repeat=[False] * 8, speed=[None] * 8)
happ = types.SimpleNamespace(layer=layer, down_at=[t0] + [None] * 7, mode=APP.NORMAL, confirmed=[False] * 8, bar_w=[0] * 8, screen=scr,
                             dirty=False, actions=types.SimpleNamespace(tap=lambda a, s=None: taps.append(a)), next_repeat=[0] * 8, cfg={"repeat_speed": "normal"})
kh = APP.App.keys_held.__get__(happ)
kh(clock.add(t0, 300))
check("held 0.3 s: the bar half full, not sent yet", 13 <= happ.bar_w[0] <= 15 and not taps and cell[1, 24] and not cell[20, 24], happ.bar_w[0])
kh(clock.add(t0, 610))
check("held 0.6 s: sent once, the bar gone", taps == [("text", "x")] and happ.bar_w[0] == 0 and not cell[5, 24])
kh(clock.add(t0, 900))
check("still held: not sent again", len(taps) == 1)
happ.down_at[0], happ.confirmed[0] = t0, False
kh(clock.add(t0, 200))
key = APP.App.key.__get__(types.SimpleNamespace(mode=APP.NORMAL, b_down=False, screen=scr, layer=layer, down_at=happ.down_at, held=[None] * 8,
                                                bar_w=happ.bar_w, dirty=False, actions=None))
key(0, False, clock.add(t0, 250))
check("let go early: the bar gone, nothing sent", happ.bar_w[0] == 0 and not cell[3, 24] and len(taps) == 1)
print("all passed" if ok else "FAILED")
