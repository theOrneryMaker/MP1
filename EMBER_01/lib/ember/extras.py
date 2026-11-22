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
    """A format ending in +N / -N (days from today; +Nw = workdays, Monday to Friday): (the format, N, workdays).
    "MM/DD/YYYY +180" -> ("MM/DD/YYYY", 180, False); "+10w" -> ("MM/DD/YYYY", 10, True)."""
    s = fmt.rstrip()
    work = len(s) > 1 and s[-1] == "w" and s[-2].isdigit()
    if work:
        s = s[:-1]
    i = len(s)
    while i and s[i - 1].isdigit():
        i -= 1
    if i < len(s) and i and s[i - 1] in "+-" and len(s) - i <= 5 and (i == 1 or s[i - 2] == " "):
        days = int(s[i:]) * (-1 if s[i - 1] == "-" else 1)
        return s[:i - 1].rstrip() or "MM/DD/YYYY", days, work
    return fmt, 0, False


def add_days(t, days, work):
    """A time.struct_time moved days ahead (or back); workdays skip Saturdays and Sundays."""
    secs = time.mktime(t)
    if not work:
        return time.localtime(secs + days * 86400)
    step = 86400 if days > 0 else -86400
    n = abs(days)
    while n:
        secs += step
        if time.localtime(secs)[6] < 5:
            n -= 1
    return time.localtime(secs)


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
        fmt, days, work = split_days(fmt)
        t = time.localtime()
        if days:
            t = add_days(t, days, work)
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


# ── the PIN for secret pages (keymap.pin_key): asked the first time they're opened after the pad is plugged in ──
class PinView:
    """Keys 1-8 type the digits, turning left takes one back, a click tries it, holding the encoder cancels."""

    def __init__(self, app, page):
        self.app, self.page = app, page
        self.digits, self.note = "", "Keys 1-8, then click"
        self.draw()

    def draw(self):
        self.app.screen.show_list("SECRET PAGES", ["Enter the PIN:", "* " * len(self.digits) + "_", self.note, "Hold: cancel"])
        self.app.dirty = True

    def tick(self, now):
        pass

    def key(self, k, pressed, now):
        if pressed and len(self.digits) < 8:
            self.digits += str(k + 1)
            self.draw()

    def turn(self, step, now):
        if step < 0 and self.digits:
            self.digits = self.digits[:-1]
            self.draw()

    def click(self, now):
        app = self.app
        if not self.digits:
            return
        if app.unlock_secret(self.digits):
            app.toggle_secret(self.page)
            return
        app.pin_fails += 1
        self.digits = ""
        if app.pin_fails >= 3:
            app.pin_fails = 0
            app.pin_until = clock.add(now, 60000)
            app.show()
            app.message("LOCKED", ["A wrong PIN 3 times:", "try again in a minute."], 3000)
            return
        self.note = "Wrong PIN ({} more tries)".format(3 - app.pin_fails)
        self.draw()


# ── the page's PIN entry on the pad's own keys (link "pinpad"): the page asks for a PIN (to set one or to open the
# secret pages there) and the pad's keys send the pattern to the page: nothing is typed. The page counts the presses and
# tells the pad how many to show (dots) and what to say. ──
class PinPadView:
    def __init__(self, app, link):
        self.app, self.link = app, link
        self.dots, self.note = 0, "Press the keys"
        self.draw()

    def draw(self):
        self.app.screen.show_list("PIN FOR THE PAGE", [self.note[:21], "* " * self.dots + "_", "Click: done", "Hold: cancel"])
        self.app.dirty = True

    def show(self, dots, note):
        self.dots, self.note = dots, note or self.note
        self.draw()

    def tick(self, now):
        pass

    def key(self, k, pressed, now):
        if pressed:
            self.link.send({"t": "pinkey", "k": k})

    def turn(self, step, now):
        if step < 0:
            self.link.send({"t": "pinback"})

    def click(self, now):
        self.link.send({"t": "pinenter"})

    def closed(self):
        self.link.send({"t": "pinclose"})


# ── the bouncing clock (the "idle_screen" setting = clock): the time, big, drifting round the screen and bouncing
# off its edges like an old screensaver, so no pixel stays lit for long (no burn-in). "MP1" until the clock is set. ──
class Saver:
    STEP_MS = 150                           # one pixel this often

    def __init__(self, app):
        import random
        self.app = app
        self.x, self.y = random.randint(4, 60), random.randint(4, 30)
        self.dx, self.dy = random.choice((-1, 1)), random.choice((-1, 1))
        self.at = None
        self.tick(clock.now())

    def tick(self, now):
        if self.at is not None and since(self.at, now) < self.STEP_MS:
            return
        self.at = now
        from ember.screen import draw_big, text_width, W, H
        from ember import font
        if self.app.clock_set:
            t = time.localtime()
            text = "{}:{:02d}".format(t[3] % 12 or 12, t[4])
        else:
            text = "MP1"
        w, h = 2 * text_width(text), 2 * font.ROWS
        self.x += self.dx
        self.y += self.dy
        if self.x <= 0 or self.x + w >= W:
            self.dx = -self.dx
            self.x = max(0, min(self.x, W - w))
        if self.y <= 0 or self.y + h >= H:
            self.dy = -self.dy
            self.y = max(0, min(self.y, H - h))
        draw_big(self.app.screen.show_canvas(), self.x, self.y, text)
        self.app.dirty = True


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

