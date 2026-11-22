# ember/extras.py - the office tools: the timer / stopwatch (with focus cycles), counters (a tally, and the numbers
# "number" keys type), date / time stamps ("stamp" keys), the busy light and clock reminders.
#
# The app keeps one Extras (app.extras) from start-up: it's small, and the timer, the busy light and the reminders
# keep going while the pad shows its layers. The Timer and Counter screens (TimerView, CounterView) open over the
# layer like the Spotify screen: turn, click, keys; hold the encoder to go back (the timer keeps running).
#
# Files on the drive (written by the pad / the page):
#   counters.json   {"ember": "counters", "TALLY": 0, "LINE": 12}   how far each counter has got (saved a few
#                   seconds after it changes); a "number" key types the next one (LINE -> 13) and moves on to it
#   reminders.json  {"ember": "reminders", "list": [{"at": "09:30", "text": "Standup", "days": "weekdays"}]}
#                   days: "every day", "weekdays" or a list of 0-6 (0 = Monday). Made in the page (Settings).
# The clock comes from the page (link.py "time"); until then stamps and reminders wait (a message says why).

import json
import time
from ember import clock
from ember.clock import since

COUNTERS = "counters.json"
REMINDERS = "reminders.json"
SAVE_AFTER = 3000           # ms after a counter changed before it's saved (fewer flash writes)
PRESETS = (5, 10, 15, 25)   # timer keys 1-4, minutes
FOCUS = (25, 5)             # focus cycles: work, break (minutes)
MAX_MINUTES = 999
ALARM_MS = 60000            # the alarm sound stops after this (the screen stays until dismissed)
TALLY = "TALLY"
STAMP_TOKENS = ("YYYY", "AMPM", "YY", "MM", "DD", "HH", "hh", "mm", "ss", "M", "D", "H", "h")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def stamp_text(fmt, t):
    """A date / time format ("MM/DD/YYYY", "h:mm AMPM", ...) filled in from a time.struct_time."""
    y, mo, d, hh, mi, ss = t[0], t[1], t[2], t[3], t[4], t[5]
    h12 = hh % 12 or 12
    values = {"YYYY": str(y), "YY": "{:02d}".format(y % 100), "MM": "{:02d}".format(mo), "M": str(mo),
              "DD": "{:02d}".format(d), "D": str(d), "HH": "{:02d}".format(hh), "H": str(hh),
              "hh": "{:02d}".format(h12), "h": str(h12), "mm": "{:02d}".format(mi), "ss": "{:02d}".format(ss),
              "AMPM": "AM" if hh < 12 else "PM"}
    out, i = [], 0
    while i < len(fmt):
        for tok in STAMP_TOKENS:
            if fmt.startswith(tok, i):
                out.append(values[tok])
                i += len(tok)
                break
        else:
            out.append(fmt[i])
            i += 1
    return "".join(out)


def split_days(fmt):
    """A format ending in +N / -N (days from today): (the format, N). "MM/DD/YYYY +180" -> ("MM/DD/YYYY", 180)."""
    s = fmt.rstrip()
    i = len(s)
    while i and s[i - 1].isdigit():
        i -= 1
    if i < len(s) and i and s[i - 1] in "+-" and len(s) - i <= 5 and (i == 1 or s[i - 2] == " "):
        days = int(s[i:]) * (-1 if s[i - 1] == "-" else 1)
        return s[:i - 1].rstrip() or "MM/DD/YYYY", days
    return fmt, 0


def mmss(ms):
    """Milliseconds -> "M:SS", or "H:MM:SS" from an hour."""
    s = max(0, ms) // 1000
    if s >= 3600:
        return "{}:{:02d}:{:02d}".format(s // 3600, s // 60 % 60, s % 60)
    return "{}:{:02d}".format(s // 60, s % 60)


def _read(path, kind):
    try:
        with open("/" + path) as f:
            data = json.load(f)
        return data if isinstance(data, dict) and data.get("ember") == kind else None
    except (OSError, ValueError):
        return None


class Extras:
    def __init__(self, app):
        self.app = app
        # counters
        self.counters = None                # {name: count}, read the first time one is used
        self.save_at = None                 # when to save counters.json (None: nothing to save)
        # the timer
        self.t_set = PRESETS[0] * 60000     # what the timer is set to (ms)
        self.t_end = None                   # running: when it ends (clock ms)
        self.t_left = None                  # paused: what's left (ms); None = not started
        self.focus = None                   # focus cycles: 0 = working, 1 = a break (None: off)
        # the stopwatch
        self.sw_start = None                # running: when it (last) started
        self.sw_acc = 0                     # what it had before that (ms)
        self.laps = []
        # the busy light, the alarm
        self.busy = False
        self.alarm_at = None                # the alarm is sounding since then
        # reminders
        self.reminders = []
        self.fired = {}                     # reminder index -> the day (yday) it last went off
        self.minute = None
        self.load_reminders()
        self.status_shown = None

    # ── counters ──
    def _counters(self):
        if self.counters is None:
            data = _read(COUNTERS, "counters") or {}
            self.counters = {k: v for k, v in data.items() if k != "ember" and isinstance(v, int)}
        return self.counters

    def count(self, name):
        return self._counters().get(name, 0)

    def set_count(self, name, value):
        self._counters()[name] = max(0, min(999999, value))
        self.save_at = clock.add(clock.now(), SAVE_AFTER)

    def names(self):
        """The counters to step through on the Counter screen: TALLY first, then the others."""
        return [TALLY] + sorted(n for n in self._counters() if n != TALLY)

    def next_number(self, name):
        """A "number" key: the counter's next number (it moves on to it), as text."""
        n = self.count(name) + 1
        self.set_count(name, n)
        return str(n)

    def save(self):
        self.save_at = None
        data = {"ember": "counters"}
        data.update(self.counters or {})
        try:
            with open("/" + COUNTERS + ".new", "w") as f:
                json.dump(data, f)
            import os
            try:
                os.remove("/" + COUNTERS)
            except OSError:
                pass
            os.rename("/" + COUNTERS + ".new", "/" + COUNTERS)
        except OSError:
            pass                            # (the drive is showing on a computer: kept until it can be saved)

    # ── stamps ──
    def stamp(self, fmt):
        """A "stamp" key: the date / time now in that format (+N / -N at the end: that many days from today),
        or None (the clock isn't set yet)."""
        if not self.app.clock_set:
            return None
        fmt, days = split_days(fmt)
        t = time.localtime()
        if days:
            t = time.localtime(time.mktime(t) + days * 86400)
        return stamp_text(fmt, t)

    # ── the timer ──
    def t_running(self):
        return self.t_end is not None

    def t_remaining(self, now):
        if self.t_end is not None:
            return max(0, clock.diff(self.t_end, now))
        return self.t_left if self.t_left is not None else self.t_set

    def t_start(self, now, minutes=None):
        if minutes is not None:
            self.t_set = minutes * 60000
            self.t_left = None
        left = self.t_left if self.t_left is not None else self.t_set
        self.t_end = clock.add(now, left)
        self.t_left = left

    def t_pause(self, now):
        if self.t_end is not None:
            self.t_left = self.t_remaining(now)
            self.t_end = None

    def t_reset(self):
        self.t_end = self.t_left = None
        self.focus = None

    def t_adjust(self, minutes, now):
        """Turning on the Timer screen: a minute more or less (running or not)."""
        if self.t_end is not None:
            left = self.t_remaining(now) + minutes * 60000
            self.t_end = clock.add(now, max(1000, min(left, MAX_MINUTES * 60000)))
        else:
            base = self.t_left if self.t_left is not None else self.t_set
            base = max(60000, min(MAX_MINUTES * 60000, (base // 60000 + minutes) * 60000))
            self.t_set, self.t_left = base, None

    def focus_toggle(self, now):
        if self.focus is None:
            self.focus = 0
            self.t_start(now, FOCUS[0])
            self.busy = True
        else:
            self.t_reset()
            self.busy = False

    # ── the stopwatch ──
    def sw_running(self):
        return self.sw_start is not None

    def sw_elapsed(self, now):
        return self.sw_acc + (since(self.sw_start, now) if self.sw_start is not None else 0)

    def sw_toggle(self, now):
        if self.sw_start is None:
            self.sw_start = now
        else:
            self.sw_acc = self.sw_elapsed(now)
            self.sw_start = None

    def sw_reset(self):
        self.sw_start, self.sw_acc, self.laps = None, 0, []

    def sw_lap(self, now):
        if self.sw_start is not None:
            self.laps = ([self.sw_elapsed(now)] + self.laps)[:3]

    # ── reminders ──
    def load_reminders(self):
        data = _read(REMINDERS, "reminders") or {}
        out = []
        for r in data.get("list") or []:
            try:
                h, m = r["at"].split(":")
                out.append((int(h), int(m), str(r.get("text") or "Reminder"), r.get("days", "every day")))
            except (KeyError, ValueError, AttributeError, TypeError):
                pass
        self.reminders = out
        self.fired = {}

    def _due(self):
        """Reminders due this minute (once each a day)."""
        if not self.reminders or not self.app.clock_set:
            return None
        t = time.localtime()
        key = (t[7], t[3], t[4])
        if key == self.minute:
            return None
        self.minute = key
        for i, (h, m, text, days) in enumerate(self.reminders):
            if (h, m) != (t[3], t[4]) or self.fired.get(i) == t[7]:
                continue
            if days == "weekdays" and t[6] > 4:
                continue
            if isinstance(days, list) and t[6] not in days:
                continue
            self.fired[i] = t[7]
            return text
        return None

    # ── every pass of the main loop ──
    def tick(self, now):
        app = self.app
        if self.save_at is not None and clock.diff(now, self.save_at) >= 0:
            self.save()
        if self.t_end is not None and clock.diff(now, self.t_end) >= 0:
            self.t_end = self.t_left = None
            if self.focus is None:
                app.alert("TIME'S UP", None)
            else:                           # focus cycles: the next part starts by itself
                self.focus = 1 - self.focus
                self.busy = self.focus == 0
                self.t_start(now, FOCUS[self.focus])
                app.alert("BREAK" if self.focus else "BACK TO IT", None)
        if self.alarm_at is not None and since(self.alarm_at, now) >= ALARM_MS:
            self.alarm_at = None
            app.sound.stop()
        due = self._due()
        if due:
            app.alert("REMINDER", due)
        if app.tool_view is not None:
            app.tool_view.tick(now)
        elif app.mode == 0:                 # (app.NORMAL: the time left on the top row, each second)
            s = self.status(now)
            if s != self.status_shown:
                self.status_shown = s
                app.status_right(s)

    def status(self, now):
        """What the top row shows in place of the encoder label (None: the label)."""
        if self.t_end is not None:
            return ("F " if self.focus is not None else "") + mmss(self.t_remaining(now) + 999)
        if self.sw_start is not None:
            return mmss(self.sw_elapsed(now))
        if self.busy:
            return "BUSY"
        return None

    def lights(self):
        """The lights while the alarm sounds or busy is on: (scene, color name), or None (the usual lights)."""
        if self.alarm_at is not None:
            return ("strobe", "RED")
        if self.busy:
            return ("static", "RED")
        return None


# ── the Timer and Counter screens: drawn on the screen's card bitmap (screen.show_canvas) ──
def _labels(b, labels):
    from ember.screen import draw_text, text_width, fit, hline, W
    hline(b, 0, W - 1, 38, True)
    for k, t in enumerate(labels):
        if t:
            t = fit(t, 30)
            draw_text(b, (k % 4) * 32 + (31 - text_width(t)) // 2, 41 + (k // 4) * 12, t)


def _big(b, text, y=14):
    from ember.screen import draw_big, draw_text, text_width, fit, W
    from ember import font
    if 2 * text_width(text) <= W - 4:
        draw_big(b, (W - 2 * text_width(text)) // 2, y, text)
    else:
        t = fit(text, W - 2)
        draw_text(b, (W - text_width(t)) // 2, y + 5, t, font.ROWS)


class TimerView:
    """Timer: turn = a minute more / less, click = start / pause, keys 1-4 = 5 / 10 / 15 / 25 minutes (and go),
    5 = start / pause, 6 = reset, 7 = the stopwatch, 8 = focus cycles. Stopwatch: click / 5 = start / stop,
    6 = reset, 7 = the timer, 8 = lap."""

    def __init__(self, app):
        self.app = app
        self.x = app.extras
        self.watch = False                  # showing the stopwatch
        self.shown = None
        self.draw(clock.now())

    def draw(self, now):
        from ember.screen import draw_text, text_width, W
        from ember import font
        x, b = self.x, self.app.screen.show_canvas()
        if self.watch:
            title, t = "STOPWATCH", mmss(x.sw_elapsed(now))
            right = "RUNNING" if x.sw_running() else ("STOPPED" if x.sw_acc else "")
            labels = ("", "", "", "", "Stop" if x.sw_running() else "Start", "Reset", "Timer", "Lap")
        else:
            title, t = "TIMER", mmss(x.t_remaining(now) + (999 if x.t_running() else 0))
            right = ("WORK" if x.focus == 0 else "BREAK") if x.focus is not None else \
                "RUNNING" if x.t_running() else "PAUSED" if x.t_left is not None else ""
            labels = tuple("{}m".format(p) for p in PRESETS) + ("Pause" if x.t_running() else "Start", "Reset", "Watch",
                                                                "Focus" if x.focus is None else "No focus")
        draw_text(b, 1, 1, title, font.CAPS)
        if right:
            draw_text(b, W - 1 - text_width(right), 1, right, font.CAPS)
        _big(b, t)
        if self.watch and x.laps:
            lap = "lap " + mmss(x.laps[0])
            draw_text(b, W - 1 - text_width(lap), 25, lap)
        _labels(b, labels)
        self.shown = t
        self.app.dirty = True

    def tick(self, now):
        x = self.x
        t = mmss(x.sw_elapsed(now)) if self.watch else mmss(x.t_remaining(now) + (999 if x.t_running() else 0))
        if t != self.shown:                 # (each second; a key / click / turn redraws at once)
            self.draw(now)

    def key(self, k, pressed, now):
        if not pressed:
            return
        x = self.x
        if self.watch:
            if k == 4:
                x.sw_toggle(now)
            elif k == 5:
                x.sw_reset()
            elif k == 6:
                self.watch = False
            elif k == 7:
                x.sw_lap(now)
        else:
            if k < 4:
                x.focus = None
                x.t_start(now, PRESETS[k])
            elif k == 4:
                self.click(now)
                return
            elif k == 5:
                x.t_reset()
            elif k == 6:
                self.watch = True
            elif k == 7:
                x.focus_toggle(now)
        self.draw(now)

    def click(self, now):
        x = self.x
        if self.watch:
            x.sw_toggle(now)
        elif x.t_running():
            x.t_pause(now)
        else:
            x.t_start(now)
        self.draw(now)

    def turn(self, step, now):
        if not self.watch:
            self.x.t_adjust(step, now)
            self.draw(now)


class CounterView:
    """Counter: turn = one more / less, keys: 1 = +1, 2 = -1, 3 = +10, 4 = reset to 0, 5 = type it, 6 = the previous
    counter, 7 = the next counter. Counters are TALLY and the ones "number" keys use."""

    def __init__(self, app):
        self.app = app
        self.x = app.extras
        self.i = 0
        self.draw()

    def name(self):
        names = self.x.names()
        self.i %= len(names)
        return names[self.i]

    def draw(self):
        from ember.screen import draw_text, text_width, W
        from ember import font
        b = self.app.screen.show_canvas()
        n = self.name()
        draw_text(b, 1, 1, "COUNTER", font.CAPS)
        draw_text(b, W - 1 - text_width(n), 1, n, font.CAPS)
        _big(b, str(self.x.count(n)))
        _labels(b, ("+1", "-1", "+10", "Reset", "Type it", "Prev", "Next", ""))
        self.app.dirty = True

    def tick(self, now):
        pass

    def key(self, k, pressed, now):
        if not pressed:
            return
        x, n = self.x, self.name()
        if k in (0, 1, 2):
            x.set_count(n, x.count(n) + (1, -1, 10)[k])
        elif k == 3:
            x.set_count(n, 0)
        elif k == 4:
            self.app.actions.write(str(x.count(n)))
        elif k in (5, 6):
            self.i += -1 if k == 5 else 1
        self.draw()

    def click(self, now):
        x, n = self.x, self.name()
        x.set_count(n, x.count(n) + 1)
        self.draw()

    def turn(self, step, now):
        x, n = self.x, self.name()
        x.set_count(n, x.count(n) + step)
        self.draw()

