"""The office tools on the PC (real extras.py / screen.py / app.py code, strict screen stand-ins, a fake clock and
files): date stamps, counters ("number" keys, the Counter screen), the timer to the end (alert), focus cycles, the
stopwatch and laps, the busy light, reminders (weekdays, once a day), the top row's time left, and the screens drawn.
    py tools/dev/tests/sim_extras.py
"""
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "EMBER_01", "lib")))
import sim_display  # noqa: E402,F401
for m in ("keypad", "usb_cdc"):
    sys.modules[m] = types.SimpleNamespace()
sys.modules["adafruit_hid"] = types.SimpleNamespace()
sys.modules["adafruit_hid.keycode"] = types.SimpleNamespace(Keycode=types.SimpleNamespace())

from ember import extras, screen, clock, app as APP  # noqa: E402

ok = True


def check(name, cond, info=""):
    global ok
    print(("ok   " if cond else "FAIL ") + name, info)
    ok &= bool(cond)


FILES = {"reminders.json": {"ember": "reminders", "list": [{"at": "09:30", "text": "Standup in the big room", "days": "weekdays"},
                                                            {"at": "16:45", "text": "Submit orders", "days": "every day"},
                                                            {"at": "bad"}]}}
extras._read = lambda path, kind: FILES.get(path)
SAVED = []
extras.Extras.save = lambda self: (SAVED.append(dict(self.counters)), setattr(self, "save_at", None))

# date stamps: 2026-11-21 (a Saturday) 14:05:09
T = time.struct_time((2026, 11, 21, 14, 5, 9, 5, 325, -1))
for fmt, want in (("MM/DD/YYYY", "11/21/2026"), ("M/D/YY", "11/21/26"), ("YYYY-MM-DD", "2026-11-21"),
                  ("h:mm AMPM", "2:05 PM"), ("HH:mm:ss", "14:05:09"), ("MM/DD/YYYY hh:mm AMPM", "11/21/2026 02:05 PM"),
                  ("Order date: M/D", "Order date: 11/21")):
    check("stamp " + fmt, extras.stamp_text(fmt, T) == want, extras.stamp_text(fmt, T))
check("midnight is 12 AM", extras.stamp_text("h AMPM", time.struct_time((2026, 1, 2, 0, 0, 0, 4, 2, -1))) == "12 AM")

# a fake app around the real Extras
now = [clock.now()]
clock_now = clock.now
clock.now = lambda: now[0]
typed, alerts, sounds = [], [], []
disp = types.SimpleNamespace(auto_refresh=True, root_group=None, refresh=lambda: None)
scr = screen.Screen(disp)
app = types.SimpleNamespace(clock_set=False, mode=APP.NORMAL, tool_view=None, last_input=now[0], dirty=False, screen=scr,
                            sound=types.SimpleNamespace(stop=lambda: sounds.append("stop")),
                            actions=types.SimpleNamespace(write=typed.append), status=[])
app.alert = lambda title, text: alerts.append((title, text))
app.status_right = lambda text: app.status.append(text)
x = extras.Extras(app)
app.extras = x
check("reminders read (a bad one left out)", len(x.reminders) == 2, x.reminders)
check("stamp before the clock is set: None", x.stamp("MM/DD/YYYY") is None)

# counters
check("a number key: 1, 2, 3", [x.next_number("LINE") for _ in range(3)] == ["1", "2", "3"])
check("saved a few seconds later", not SAVED)
now[0] = clock.add(now[0], 3500)
x.tick(now[0])
check("... and then saved", SAVED and SAVED[-1].get("LINE") == 3, SAVED[-1:])
check("TALLY comes first in the list", x.names()[0] == "TALLY" and "LINE" in x.names())

# the timer
x.t_start(now[0], 10)
check("10 minutes running", x.t_running() and 599000 <= x.t_remaining(now[0]) <= 600000)
check("the top row: 10:00", x.status(now[0]) == "10:00", x.status(now[0]))
now[0] = clock.add(now[0], 61000)
x.tick(now[0])
check("a minute on: 8:59", app.status[-1] == "8:59", app.status[-3:])
x.t_pause(now[0])
now[0] = clock.add(now[0], 300000)
check("paused: it stays", 538000 <= x.t_remaining(now[0]) <= 539000 and not x.t_running())
x.t_start(now[0])
x.t_adjust(-5, now[0])
check("turned 5 minutes off while running", 238000 <= x.t_remaining(now[0]) <= 239000)
now[0] = clock.add(now[0], 240000)
x.tick(now[0])
check("it ends: TIME'S UP", alerts and alerts[-1] == ("TIME'S UP", None) and not x.t_running(), alerts[-1:])
x.t_reset()
x.t_adjust(3, now[0])
check("set by turning (not running): 10 + 3 = 13 min", x.t_set == 13 * 60000)

# focus cycles
x.focus_toggle(now[0])
check("focus: 25 minutes, busy on", x.focus == 0 and x.busy and 1499000 <= x.t_remaining(now[0]) <= 1500000)
check("the top row says F", x.status(now[0]).startswith("F 25"), x.status(now[0]))
now[0] = clock.add(now[0], 1500000)
x.tick(now[0])
check("then a break: BREAK, busy off, 5 minutes", alerts[-1][0] == "BREAK" and x.focus == 1 and not x.busy and x.t_running())
now[0] = clock.add(now[0], 300000)
x.tick(now[0])
check("then back to work", alerts[-1][0] == "BACK TO IT" and x.focus == 0 and x.busy)
x.focus_toggle(now[0])
check("focus off: busy off, the timer reset", x.focus is None and not x.busy and not x.t_running())

# the stopwatch
x.sw_toggle(now[0])
now[0] = clock.add(now[0], 65000)
x.sw_lap(now[0])
now[0] = clock.add(now[0], 5000)
x.sw_toggle(now[0])
now[0] = clock.add(now[0], 99000)
check("stopwatch: 1:10, stopped", extras.mmss(x.sw_elapsed(now[0])) == "1:10" and not x.sw_running())
check("a lap at 1:05", x.laps and extras.mmss(x.laps[0]) == "1:05")
check("an hour shows H:MM:SS", extras.mmss(3725000) == "1:02:05")
x.sw_reset()

# busy, the alarm
x.busy = True
check("busy: red lights, BUSY on top", x.lights() == ("static", "RED") and x.status(now[0]) == "BUSY")
x.alarm_at = now[0]
check("the alarm: flashing red", x.lights() == ("strobe", "RED"))
now[0] = clock.add(now[0], 61000)
x.tick(now[0])
check("the alarm sound stops after a minute", x.alarm_at is None and sounds[-1] == "stop")
x.busy = False

# reminders: the clock set, 09:30 on a Monday, then a Saturday
app.clock_set = True
real_localtime = time.localtime
time.localtime = lambda: time.struct_time((2026, 11, 23, 9, 30, 0, 0, 327, -1))
n = len(alerts)
x.tick(now[0])
check("09:30 on a weekday: the reminder", alerts[-1] == ("REMINDER", "Standup in the big room"), alerts[-1:])
x.minute = None
x.tick(now[0])
check("only once that day", len(alerts) == n + 1)
time.localtime = lambda: time.struct_time((2026, 11, 28, 9, 30, 0, 5, 332, -1))
x.tick(now[0])
check("not on a Saturday", len(alerts) == n + 1)
time.localtime = lambda: time.struct_time((2026, 11, 28, 16, 45, 0, 5, 332, -1))
x.tick(now[0])
check("16:45 every day: yes on Saturday", alerts[-1] == ("REMINDER", "Submit orders"))
check("a stamp now the clock is set", x.stamp("MM/DD/YYYY") == "11/28/2026")
time.localtime = real_localtime

# the screens
app.mode = APP.TOOLVIEW
v = extras.TimerView(app)
app.tool_view = v
check("Timer screen shows on the full-screen bitmap", not scr.card_view.hidden and scr.layer_view.hidden)
v.key(1, True, now[0])
check("key 2: 10 minutes, running", x.t_running() and 599000 <= x.t_remaining(now[0]) <= 600000)
v.click(now[0])
check("click: paused", not x.t_running() and x.t_left is not None)
v.turn(2, now[0])
check("turn: 2 more minutes", 719000 <= x.t_remaining(now[0]) <= 720000)
v.key(6, True, now[0])
check("key 7: the stopwatch", v.watch)
v.click(now[0])
now[0] = clock.add(now[0], 3000)
x.tick(now[0])
check("the stopwatch runs and redraws", x.sw_running() and v.shown == "0:03", v.shown)
print("\n".join("".join("#" if c else "." for c in row) for row in scr.card.d))
c = extras.CounterView(app)
app.tool_view = c
c.key(0, True, now[0]); c.key(0, True, now[0]); c.key(2, True, now[0]); c.turn(-1, now[0])
check("Counter: +1 +1 +10 -1 = 11 on TALLY", x.count("TALLY") == 11)
c.key(4, True, now[0])
check("Type it: types 11", typed[-1] == "11")
c.key(6, True, now[0])
check("Next: LINE (3)", c.name() == "LINE" and x.count("LINE") == 3)
c.key(3, True, now[0])
check("Reset: LINE 0, so its next number is 1", x.next_number("LINE") == "1")
print("\n".join("".join("#" if c_ else "." for c_ in row) for row in scr.card.d))
clock.now = clock_now
print("all passed" if ok else "FAILED")
