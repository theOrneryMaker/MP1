# /lib/macropad/extras.py
# Layer keys, the menu reel animation, the stopwatch screen, the screen saver and the
# Caps Lock indicator. Part of the App class (see app.py). Also the loop timing readout
# and the text wrapper used by the error screen.

import time
from macropad import stopwatch, clock
from macropad.clock import since, ms
from macropad.modes import *    # noqa: F401,F403


class LoopStats:
    """Optional timing readout ("loop_stats": true in settings.js). Every 5 seconds
    prints how many main-loop passes ran, the average and slowest pass, and free memory
    to the serial console."""
    PERIOD_MS = 5000

    def __init__(self):
        import gc
        self.gc = gc
        self.reset(time.monotonic_ns())

    def reset(self, now_ns):
        self.window_start = now_ns
        self.passes = 0
        self.busy_ns = 0
        self.worst_ns = 0

    def start(self):
        self.pass_start = time.monotonic_ns()

    def stop(self):
        now = time.monotonic_ns()
        took = now - self.pass_start
        self.passes += 1
        self.busy_ns += took
        if took > self.worst_ns:
            self.worst_ns = took
        if (now - self.window_start) // 1000000 >= self.PERIOD_MS:
            print("loop: {} passes/5s, avg {:.2f} ms, slowest {:.1f} ms, free memory {} bytes".format(
                self.passes, self.busy_ns / self.passes / 1e6, self.worst_ns / 1e6, self.gc.mem_free()))
            self.reset(now)


def wrap(text, width=SCREEN_CHARS):
    lines, line = [], ""
    for word in text.split(" "):
        while len(word) > width:                      # break very long words
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:width])
            word = word[width:]
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


class Extras:
    # ─── Hold-to-confirm keys ───
    def start_confirm(self, key, action, now):
        self.confirming = (key, action, now)
        self.mode = CONFIRM
        self.menu = None
        self.last_input = now
        self.screen.show_confirm(self.current.icons[key] or "KEY {}".format(key + 1))

    def update_confirm(self, now):
        """Fill the bar; once it's full, send the key's action (once, as a tap)."""
        if self.mode != CONFIRM or self.confirming is None:
            return
        _, action, start = self.confirming
        total = max(1, ms(self.cfg["confirm_time"]))
        held = since(start, now)
        self.screen.set_confirm(held / total)
        if held >= total:
            self.confirming = None
            self.show_layer()
            self.screen.refresh()
            self.actions.press(action)
            self.actions.release(action)
            self.last_activity = clock.now()

    def cancel_confirm(self):
        self.confirming = None
        if self.mode == CONFIRM:
            self.show_layer()

    # ─── LOCK KEYS ───
    def lock_keys(self):
        self.actions.release_all()
        self.held.clear()
        self.repeating.clear()
        self.clicks = 0
        self.locked = True
        self.show_lock()

    def show_lock(self):
        self.mode = LOCKED
        self.menu = None
        self.draw_lock()

    def draw_lock(self):
        self.shown_lock = self.blink_phase
        self.screen.show_lock("LOCKED", self.unlock_hint(), self.blink_phase)

    def update_lock(self):
        """Flash inverted on the jiggle / CAPS blink clock."""
        if self.mode == LOCKED and self.blink_phase != self.shown_lock:
            self.draw_lock()

    def unlock_gesture_set(self):
        return any(self.cfg[key] == "lock" for key, _ in UNLOCK_HINTS)

    def unlock_hint(self):
        for key, text in UNLOCK_HINTS:
            if self.cfg[key] == "lock":
                return text
        return NO_UNLOCK_GESTURE

    def update_repeat(self, now):
        """Keys with "repeat": true fire again while held (after RPT DELAY, RPT RATE a second)."""
        if not self.repeating:
            return
        if self.mode != NORMAL:             # opened a menu while holding: stop
            self.repeating.clear()
            return
        interval = max(1, 1000 // max(1, int(self.cfg["repeat_rate"])))
        for key in self.repeating:
            due = self.repeating[key]
            if clock.diff(now, due) < 0:
                continue
            action = self.held.get(key)
            if action:
                self.actions.press(action)
                self.last_activity = now
            # Fell behind (e.g. long text)? Carry on from now rather than catching up
            late = clock.diff(now, due) >= interval
            self.repeating[key] = clock.add(now if late else due, interval)

    def open_layer_keys(self):
        """Layer names on the keys, starting on the page with the current layer."""
        regular = self.km.REGULAR_LAYERS
        base = self.layer if self.layer in regular else self.prev_layer
        self.page = regular.index(base) // PAGE_SIZE if base in regular else 0
        self.mode = LAYER_KEYS
        self.last_input = clock.now()
        self.menu = None
        self.draw_layer_keys()

    def draw_layer_keys(self):
        regular = self.km.REGULAR_LAYERS
        pages = (len(regular) + PAGE_SIZE - 1) // PAGE_SIZE
        first = self.page * PAGE_SIZE
        names = self.km.LAYER_NAMES
        current = self.layer if self.layer in regular else self.prev_layer
        icons = []
        for index in regular[first:first + PAGE_SIZE]:
            name = names[index].upper()
            icons.append(">" + name[:3] if index == current else name[:4])
        title = "LAYERS {}/{}".format(self.page + 1, pages) if pages > 1 else "LAYERS"
        self.screen.show_keys(icons, title)

    def roll_menu(self, moved, now):
        """The selection just moved one item (+1 = to the item shown on top). Animate
        the reel turning one slot (update_roll draws the frames), then settle.
        ROLL TIME = how long the turn takes, ROLL STEPS = frames drawn along the way."""
        items = self.menu.items
        n = len(items)
        if ms(self.cfg["menu_roll_time"]) <= 0 or n < 2 or (self.mode == CONFIG and self.menu.editing):
            self.draw_menu()
            return
        new = self.menu.selection
        old = (new - moved) % n
        # (text, from slot, to slot): slot 0 = top, 1 = middle (selected), 2 = bottom,
        # -1 / 3 = just off screen
        if moved > 0:       # the top item comes to the middle: everything moves down
            moves = ((items[new], 0, 1), (items[old], 1, 2),
                     (items[(new + 1) % n], -1, 0), (items[(old - 1) % n], 2, 3))
        else:               # the bottom item comes to the middle: everything moves up
            moves = ((items[new], 2, 1), (items[old], 1, 0),
                     (items[(new - 1) % n], 3, 2), (items[(old + 1) % n], 0, -1))
        self.roll_moves = moves if n > 2 else moves[:2]     # 2 items: no neighbours to show
        self.roll_frame = -1
        self.rolling = True
        self.roll_at = now
        self.update_roll(now)

    def update_roll(self, now):
        if not self.rolling:
            return
        total = ms(self.cfg["menu_roll_time"])
        elapsed = since(self.roll_at, now)
        if elapsed >= total:
            self.rolling = False
            if self.mode in MENU_MODES and self.menu is not None:
                self.draw_menu()
            return
        steps = self.cfg["menu_roll_steps"]
        frame = elapsed * steps // total            # time-based: if the OLED can't keep up,
        if frame != self.roll_frame:                # frames are skipped, the speed stays the same
            self.roll_frame = frame
            self.screen.show_reel(self.roll_moves, (frame + 1) / (steps + 1))

    def open_stopwatch(self):
        self.mode = STOPWATCH
        self.menu = None
        self.last_input = clock.now()
        self.draw_stopwatch()

    def draw_stopwatch(self, now=None):
        self.shown_sw = self.stopwatch.tenths(now)
        self.screen.show_stopwatch(stopwatch.big_text(self.shown_sw), stopwatch.ICONS)

    def update_stopwatch(self, now):
        if self.mode == STOPWATCH and self.stopwatch.tenths(now) != self.shown_sw:
            self.draw_stopwatch(now)

    def update_saver(self, now):
        stopwatch_on = self.mode == STOPWATCH and self.stopwatch.state == stopwatch.RUNNING
        if self.mode == ALERT or stopwatch_on:
            self.last_wake = now                    # never sleep on these screens
        cfg = self.cfg
        dim, off = ms(cfg["screen_dim_minutes"] * 60), ms(cfg["screen_off_minutes"] * 60)
        idle = since(self.last_wake, now)
        level = AWAKE
        if dim and idle >= dim:
            level = DIM
        if off and idle >= off:
            level = OFF
        # Stay down until there's input (the idle count wraps after ~6 days)
        if self.saver == OFF and off:
            level = OFF
        elif self.saver == DIM and dim and level == AWAKE:
            level = DIM
        if level != self.saver:
            self.set_saver(level)

    def set_saver(self, level):
        self.saver = level
        self.screen.set_brightness(self.cfg["screen_dim_level"] if level == DIM else 1.0)
        self.screen.power(level != OFF)

    def wake(self, now):
        """Any input. Returns True if the screen was off: that input only wakes it."""
        self.last_wake = now
        if self.saver == AWAKE:
            return False
        was_off = self.saver == OFF
        self.set_saver(AWAKE)
        return was_off

    def update_caps(self, now):
        if since(self.caps_at, now) < CAPS_POLL_MS:
            return
        self.caps_at = now
        state = self.actions.caps_lock()
        if state is None or state == self.caps:
            return
        first = self.caps is None           # already on at start-up: box only, no flash
        self.caps = state
        if (not first and self.cfg["caps_flash"] and self.mode == NORMAL
                and self.saver != OFF):
            self.screen.set_caps(False)     # box appears once the pop-up has gone
            self.notice("Caps on" if state else "Caps off")
        self.show_caps_box()

    def show_caps_box(self):
        """CAPS box while Caps Lock is on; it swaps black/white in time with the jiggle J."""
        self.screen.set_caps(bool(self.caps) and self.cfg["caps_box"]
                             and self.mode in TOP_BAR_MODES, self.blink_phase)
