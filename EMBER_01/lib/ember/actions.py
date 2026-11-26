# ember/actions.py (from FIRMWARE_04; "open" replaces "url" and "app", "layer" is new)
# Sends HID output for key actions, sequences, encoder turns, and mouse jiggle.
# Actions are the (kind, value) tuples produced by keymap.py; a macro's value is packed bytes.

import time
import random
from adafruit_hid.keycode import Keycode
from ember import clock
try:
    import supervisor
except ImportError:                         # (the tests on a computer)
    supervisor = None

HID_RETRY_MS = 5000     # while the computer isn't listening, a report is tried at most this often


def computer_listening():
    """False while the computer is asleep, off or still starting (USB not ready)."""
    return supervisor is None or supervisor.runtime.usb_connected


class Hid:
    """A USB keyboard / mouse / media device that never holds the pad up. adafruit_hid would wait for the
    computer at start-up (forever, if it's asleep or off); this isn't a usb_hid.Device, so it doesn't, and Ember
    starts without one. While the computer isn't listening a report is tried at most every few seconds (that try
    can wake a sleeping computer; it takes up to 2 s) and the rest are dropped; a failed one is dropped too."""

    def __init__(self, dev):
        self.dev = dev
        self.usage_page = dev.usage_page
        self.usage = dev.usage
        self.tried = None

    def send_report(self, *args):
        if not computer_listening():
            now = clock.now()
            if self.tried is not None and clock.since(self.tried, now) < HID_RETRY_MS:
                return
            self.tried = now
        try:
            self.dev.send_report(*args)
        except OSError:
            pass

    def get_last_received_report(self, *args):
        return self.dev.get_last_received_report(*args)

CAPS_LOCK_LED = 0x02        # Keyboard.LED_CAPS_LOCK
NUM_LOCK_LED = 0x01         # Keyboard.LED_NUM_LOCK
NUM_LOCK_KEY = ("key", 0x53)    # Keycode.KEYPAD_NUMLOCK


TEXT_CHUNK = 32         # characters typed between watchdog feeds
# typing speeds (the "type_speed" setting, or a key's own): (seconds after each character, seconds between macro steps).
# normal = as fast as the computer takes it; careful / slow for websites that drop characters or need a moment.
SPEED = {"normal": (0, 0.01), "careful": (0.015, 0.06), "slow": (0.04, 0.2)}

# PANIC!: only actions that can't undo themselves when pressed twice
MEDIA_PAUSE = 0xB1      # dedicated Pause (Play/Pause would start playback if nothing was playing)
VOLUME_DOWN = 0xEA
PANIC_VOLUME_STEPS = 50 # Windows steps 2 % per press: 50 reaches 0 from any level (mute would toggle)


def _nothing():
    pass


class Stopped(Exception):
    """A running macro (or a long text, a wait) was stopped: the encoder held (App.stop_wanted / macro_pause)."""


class GoTo(Exception):
    """Paused, a row was picked (App.macro_pause): the macro goes on from that CSV row's start."""

    def __init__(self, row):
        self.row = row


TEXT_OPS = {8: "text", 9: "open", 13: "tool", 14: "layer", 15: "number", 16: "stamp", 18: "pause"}


def _int16(data, i):
    value = data[i] | data[i + 1] << 8
    return value - 0x10000 if value & 0x8000 else value


def _int32(data, i):
    return data[i] | data[i + 1] << 8 | data[i + 2] << 16 | data[i + 3] << 24


def read_step(data, i):
    """One packed action at data[i] (see keymap.OP): ((kind, value), index after it).
    Used for macro steps and for the actions in a packed layer (layers.py)."""
    op = data[i]
    i += 1
    if op == 1:
        return ("key", data[i]), i + 1
    if op == 2:
        n = data[i]
        return ("combo", tuple(data[i + 1:i + 1 + n])), i + 1 + n
    if op == 3:
        return ("click", data[i]), i + 1
    if op == 4:
        return ("media", data[i] | data[i + 1] << 8), i + 2
    if op == 5:
        return ("scroll", _int16(data, i)), i + 2
    if op == 6:
        return ("mouse", (_int16(data, i), _int16(data, i + 2))), i + 4
    if op == 7:
        return ("delay", _int32(data, i) / 1000), i + 4
    if op == 17:                            # a CSV row mark: (row, rows)
        return ("mark", (data[i] | data[i + 1] << 8, data[i + 2] | data[i + 3] << 8)), i + 4
    if op == 11:                            # a whole macro (only in packed layers)
        n = _int32(data, i)
        i += 4
        return ("sequence", bytes(data[i:i + n])), i + n
    n = data[i] | data[i + 1] << 8
    i += 2
    return (TEXT_OPS[op], str(data[i:i + n], "utf-8")), i + n


def macro_steps(data):
    """The (kind, value) steps of a macro, unpacked one at a time from the bytes keymap.py
    packs them into (see keymap.OP)."""
    i, end = 2, len(data)
    while i < end:
        if data[i] == 12:                   # keymap.REPEAT_OP: a count, then one step
            n = data[i + 1] | data[i + 2] << 8
            step, i = read_step(data, i + 3)
            for _ in range(n):
                yield step
        else:
            step, i = read_step(data, i)
            yield step


class Actions:
    def __init__(self, kbd, layout, cc, mouse):
        self.kbd = kbd
        self.layout = layout
        self.cc = cc
        self.mouse = mouse
        self.wait = time.sleep              # the main loop swaps in a wait that keeps lights/sound running
        self.feed = _nothing                # the main loop swaps in its watchdog feed
        self.log_sends = None               # start-up send log: sendlog.log while it's on
        self.sent_ctrl_c = None             # when the pad last sent Ctrl+C itself (clock ms)
        self.open_url = None                # MP1 Link connected: opens a web address in the browser
                                            # (True if it did; otherwise the Run dialog is used)
        self.run_tool = None                # the app: run_tool(kind, value) for "tool" and "layer" actions
        self.stop_begin = None              # the app: called as an action starts (a fresh look at the stop inputs)
        self.stop_wanted = None             # the app: True when a key / the encoder asks a running macro to stop
        self.stopped = None                 # the app: called after one was stopped (STOPPED on the screen)
        self.depth = 0                      # press() inside press() (a macro's steps): only the outer one stops
        self.paused = None                  # the app: paused(note) waits (the encoder pressed, or a "pause" step); True = stop
        self.progress = None                # the app: progress(step, steps, mark) as a macro runs
        self.finished = None                # the app: called when the outer press is over
        self.mark = None                    # the CSV row the macro is on: (row, rows)
        self.cfg = None                     # the app's settings (type_speed)
        self.speed = SPEED["normal"]        # the speed of the press running now (its key's own, or the setting)

    def check(self):
        """Between macro steps, text chunks and inside waits: stop if asked to, or pause (the encoder pressed)."""
        if self.stop_wanted is None:
            return
        r = self.stop_wanted()
        if r == "pause":
            r = self.paused(None) if self.paused is not None else False
        self._after_pause(r)

    def _after_pause(self, r):
        """stop_wanted / paused said: False (go on), True (stop) or a row number (go on from there)."""
        if r is True:
            raise Stopped()
        if r is not False and r is not None:
            raise GoTo(r)

    def press(self, action, speed=None):
        """Key down. key/combo/click stay held until release(). A macro, a text or a wait can be stopped
        part way (any key, a turn, a press of the encoder): everything held is let go. speed: the key's own
        typing speed (None: the pad's setting)."""
        self.depth += 1
        try:
            if self.depth == 1:
                self.mark = None
                name = speed or (self.cfg["type_speed"] if self.cfg else "normal")
                self.speed = SPEED.get(name, SPEED["normal"])
                if self.stop_begin is not None:
                    self.stop_begin()
            self._press(action)
        except Stopped:
            if self.depth > 1:
                raise
            self.release_all()
            if self.stopped is not None:
                self.stopped()
        finally:
            self.depth -= 1
            if not self.depth and self.finished is not None:
                self.finished()

    def _press(self, action):
        kind, value = action
        if self.log_sends is not None:
            self.log_sends(action)
        if kind == "key":
            self.kbd.press(value)
        elif kind == "combo":
            if Keycode.C in value and (Keycode.CONTROL in value or Keycode.RIGHT_CONTROL in value):
                self.sent_ctrl_c = clock.now()  # may come back as an interrupt: see App.run
            self.kbd.press(*value)
        elif kind == "click":
            self.mouse.press(value)
        elif kind == "text":
            self.write(value)
        elif kind == "media":
            self.cc.send(value)
        elif kind == "scroll":
            self.mouse.move(wheel=value)
        elif kind == "mouse":
            self.mouse.move(x=value[0], y=value[1])
        elif kind == "open":                # a web address or a program (Windows Run dialog)
            if "://" in value:
                if self.open_url is None or not self.open_url(value):
                    self.run('cmd /c start "" "{}"'.format(value))
            else:
                self.run(value)
        elif kind in ("tool", "layer", "number", "stamp"):     # (the app's: extras.py for number / stamp)
            if self.run_tool is not None:
                self.run_tool(kind, value)
        elif kind == "delay":
            self.wait(value)
        elif kind == "mark":                # (a CSV row starts: for the progress screen)
            self.mark = value
        elif kind == "pause":               # wait for a click (a hold stops; a turn picks a row to go on from)
            if self.paused is not None:
                self._after_pause(self.paused(value))
        elif kind == "sequence":
            gap, steps, goto = self.speed[1], value[0] | value[1] << 8, None
            while True:
                n = 0
                try:
                    for step in macro_steps(value):
                        n += 1
                        if goto is not None:    # (going on from a picked row: everything before its mark is skipped)
                            if step[0] != "mark" or step[1][0] != goto:
                                continue
                            goto = None
                        self.check()
                        self.tap(step)
                        self.feed()
                        if self.progress is not None:
                            self.progress(n, steps, self.mark)
                        if step[0] != "mark":
                            time.sleep(max(0.1, gap) if step[0] == "media" else gap)
                    return
                except GoTo as g:
                    self.release_all()
                    goto = g.row

    def release(self, action):
        kind, value = action
        if kind == "key":
            self.kbd.release(value)
        elif kind == "combo":
            if Keycode.C in value and (Keycode.CONTROL in value or Keycode.RIGHT_CONTROL in value):
                self.sent_ctrl_c = clock.now()  # repeats can arrive while it's held: count from letting go
            self.kbd.release(*value)
        elif kind == "click":
            self.mouse.release(value)

    def write(self, text):
        """Type text in short pieces, feeding the watchdog in between: long text can
        take longer to type than the watchdog waits. Careful / slow: a pause after each character."""
        pause = self.speed[0]
        if pause:
            for i, c in enumerate(text):
                if i:
                    self.check()
                self.layout.write(c)
                time.sleep(pause)
                if not i % TEXT_CHUNK:
                    self.feed()
            return
        for i in range(0, len(text), TEXT_CHUNK):
            if i:
                self.check()
            self.layout.write(text[i:i + TEXT_CHUNK])
            self.feed()

    def tap(self, action, speed=None):
        self.press(action, speed)
        if action[0] in ("key", "combo", "click"):
            time.sleep(0.01)
            self.release(action)

    def run(self, command):
        """Open the Windows Run dialog and execute a command."""
        self.kbd.send(Keycode.WINDOWS, Keycode.R)
        self.wait(0.4)
        self.write(command)
        self.kbd.send(Keycode.ENTER)

    def turn(self, layer, clicks, speed):
        """Run a layer's encoder action. clicks > 0 is clockwise; speed is the
        acceleration multiplier (used only when the layer has accel on)."""
        action = layer.cw if clicks > 0 else layer.ccw
        if not action:
            return
        count = abs(clicks) * (speed if layer.accel else 1)
        kind, value = action
        if kind == "scroll":
            self.mouse.move(wheel=value * count)
        elif kind == "mouse":
            self.mouse.move(x=value[0] * count, y=value[1] * count)
        else:
            for _ in range(count):
                self.press(action)
                self.release(action)

    def caps_lock(self):
        """Caps Lock state reported by the computer (it sends it to every keyboard),
        or None if it can't be read."""
        return self._led(CAPS_LOCK_LED)

    def num_lock(self):
        """Num Lock state reported by the computer, or None if it can't be read."""
        return self._led(NUM_LOCK_LED)

    def _led(self, which):
        try:
            return bool(self.kbd.led_on(which))
        except Exception:
            return None

    def panic(self):
        """PANIC!: pause media, minimize every window (Win+M; Win+D would toggle them
        back), then turn the volume all the way down. Safe to press repeatedly."""
        self.release_all()                      # let go of anything held first
        self.cc.send(MEDIA_PAUSE)
        self.kbd.send(Keycode.GUI, Keycode.M)
        for i in range(PANIC_VOLUME_STEPS):
            self.cc.send(VOLUME_DOWN)
            if i % 10 == 9:
                self.feed()

    def release_all(self):
        """Safety net after an unexpected error: let go of every key and mouse button."""
        for release in (self.kbd.release_all, self.mouse.release_all):
            try:
                release()
            except Exception:
                pass

    def jiggle(self, pixels):
        if not computer_listening():        # (asleep: leave it asleep)
            return
        dx, dy = random.choice(((pixels, 0), (-pixels, 0), (0, pixels), (0, -pixels)))
        self.mouse.move(x=dx, y=dy)
        self.mouse.move(x=-dx, y=-dy)
