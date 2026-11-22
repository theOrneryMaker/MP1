"""The "sounds" setting as 1 / 0 switches (Boot, Layers, Keys, Alarms): checked, the earlier off / keys / everything
converted, edited in the pad's menu (turn = which switch, click = flip, Done), and the app asking for one kind.
    py tools/dev/tests/sim_sounds.py
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

from ember import settings, menus, app as APP  # noqa: E402

ok = True


def check(name, cond, info=""):
    global ok
    print(("ok   " if cond else "FAIL ") + name, info)
    ok &= bool(cond)


check("default 1001 (start-up and alarms)", settings.SETTINGS["sounds"][0] == "1001")
check("1011 is fine", settings._ok("sounds", "1011"))
check("10011 (5) / 10x1 / 1 are not", not settings._ok("sounds", "10011") and not settings._ok("sounds", "10x1") and not settings._ok("sounds", 1))
for old, new in settings.OLD_SOUNDS.items():
    check("old '{}' -> {}".format(old, new), settings._ok("sounds", new))

cfg = {n: d for n, (d, _) in settings.SETTINGS.items()}
m = menus.Menu(cfg, True, True)
m.where = [g[0] for g in m.groups].index("Sound")
m.sel = 0
view = lambda: m.view(lambda t: "")[1][0]
check("the row: Sounds 1001", view() == ("Sounds", "1001"), view())
m.click()
check("click: editing, on Boot", m.editing and view() == ("Boot", "[1]001"), view())
m.turn(1)
m.turn(1)
check("turn twice: Keys", view() == ("Keys", "10[0]1"), view())
r = m.click()
check("click flips it: 1011, saved later", cfg["sounds"] == "1011" and r == "set:sounds" and m.changed, cfg["sounds"])
m.turn(-2)
m.click()
check("back to Boot and off: 0011", cfg["sounds"] == "0011")
m.turn(-1)
check("turning left from Boot: Done", view()[0] == "Done", view())
m.click()
check("Done: editing ends", not m.editing and view() == ("Sounds", "0011"), view())

app = types.SimpleNamespace(cfg={"sounds": "1001"}, sound_on=True)
s = APP.App.sounds.__get__(app)
check("1001: boot and alarms only", s(APP.SOUND_BOOT) and not s(APP.SOUND_LAYERS) and not s(APP.SOUND_KEYS) and s(APP.SOUND_ALARMS))
app.sound_on = False
check("Sound off (the pad function): none", not s(APP.SOUND_BOOT) and not s(APP.SOUND_ALARMS))
print("all passed" if ok else "FAILED")
