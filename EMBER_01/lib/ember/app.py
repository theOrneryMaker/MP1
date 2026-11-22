# ember/app.py - the main loop: keys, the encoder and its button, layers, the pad's own functions.
#
# Encoder button: click / double / triple click run the click settings; hold + turn (5 clicks) runs
# hold_turn_right / left; hold + a key runs that HOLD+KEY key (its screen shows while the button is
# held); a long press (1.5 s, nothing else done) opens the TOOLS menu when released. Timings are fixed (NOTES/PAD_CORE.md).

import gc
import time
import random
from ember import clock
from ember.clock import since
from ember.screen import picture, KEY_LINES
from ember import gestures

DEBOUNCE = 30               # ms the button must be steady
MULTI_CLICK = 250           # ms between the clicks of a double / triple click
HOLD_SCREEN = 150           # ms held before the HOLD+KEY screen shows (user, 2026-11-21: sooner)
LONG_PRESS = 1500           # ms held (nothing else done), then released = TOOLS menu (on the release:
                            # the HOLD+KEY screen stays up as long as the button is held)
HOLD_TURN = 5               # encoder clicks while held = hold + turn
UNLOCK = 3000               # ms held to unlock the keys
FAST, MEDIUM = 30, 80       # ms between encoder clicks: x4 / x2 (layers with accel)
CONFIRM = 600               # ms a confirm key must be held
REPEAT = {"slow": (700, 160), "normal": (500, 100), "fast": (350, 60)}   # (delay, every) ms
MENU_TIMEOUT = 6000         # ms without input: a picker / menu closes
MESSAGE_TIME = 1500         # ms a message shows
LOCKS_EVERY = 300           # ms between Caps / Num Lock checks
JIGGLE_EVERY = (25000, 40000)
NUM_LOCK_TRIES = 3          # a "keep Num Lock on" layer presses Num Lock at most this often in a row,
NUM_LOCK_RETRY_MS = 1000    # this far apart (the computer may not report it, or something keeps turning it off)

NORMAL, HOLD, PICKER, LAYER_KEYS, MESSAGE, LOCKED, MENU, SYNC, NOWPLAY, TOOLVIEW = range(10)
SOUND_BOOT, SOUND_LAYERS, SOUND_KEYS, SOUND_ALARMS = range(4)     # the "sounds" setting's switches ("1001")
ALERT_MS = 600000
PROGRESS_AFTER = 800        # ms a macro runs before its progress screen shows (short ones never flash it)
PROGRESS_EVERY = 300        # ms between progress screen redraws (each costs a screen refresh)           # a timer / reminder alert stays this long (or until a key, a turn or a click)
MENU_IDLE = 15000          # ms without input: the TOOLS menu closes (and saves)
DRIVE_SLOT = 8             # boot.py: b"MP1D" this many bytes from the end of the NVM = show the drive next start


def drive_shown():
    """Is the drive showing on the computer (so this program can't write its files)?"""
    try:
        import storage
        return storage.getmount("/").readonly
    except Exception:
        return False


class NoAddon:
    """Stands in for lights / sound when they aren't fitted: everything does nothing."""
    pixels = None
    error = None
    STARTUP = LAYER = WARNING = ALARM = ()

    def __getattr__(self, name):
        return lambda *a, **k: None


class App:
    NORMAL, HOLD, SYNC, TOOLVIEW = NORMAL, HOLD, SYNC, TOOLVIEW     # (for link.py)

    def __init__(self, keymap, cfg, screen, actions, keys, encoder, button, display, errors=(), lights=None, sound=None, hw=None,
                 port=None):
        self.km = keymap
        self.cfg = cfg
        self.screen = screen
        self.actions = actions
        self.keys = keys
        self.encoder = encoder
        self.button = button
        self.display = display
        self.errors = list(errors)
        self.lights = lights or NoAddon()
        self.sound = sound or NoAddon()
        self.hw = hw or {}
        self.lights_on = self.sound_on = True     # Lights / Sound on-off functions (until restart)
        self.color_names = (None, None)
        self.colors = (None, None)
        actions.run_tool = self.run_tool
        actions.wait = self.wait
        actions.cfg = cfg
        actions.stop_begin = self.stop_begin
        actions.stop_wanted = self.stop_wanted
        actions.stopped = self.macro_stopped
        actions.paused = self.macro_pause
        actions.progress = self.macro_progress
        actions.finished = self.macro_finished
        self.prog_start = None              # a macro running: when it started; its progress screen shows after PROGRESS_AFTER
        self.prog_at = None                 # when the progress screen was last drawn (None: not showing)
        self.stop_seen = 0                  # when the stop inputs were last looked at (a running macro)
        self.stop_button = False            # the encoder was down at the last look (HOLD+KEY starts with it down)
        self.swallow_button = False         # the press that stopped a macro: it does nothing else
        self.stop_event = None
        self.index = keymap.HOME
        self.layer = None
        self.mode = NORMAL
        self.dirty = False
        self.prev_index = keymap.HOME       # the layer a secret layer goes back to
        self.np = None                      # the song the Ember page last sent ({"c": "np"}: link.py), or None
        self.np_at = 0                      # when it came (the position moves on from there while playing)
        self.np_view = None                 # the Spotify screen (nowplay.py) while it's open
        self.held = [None] * 8              # the action each pressed key is holding down
        self.down_at = [None] * 8           # when each key went down (repeat / confirm)
        self.next_repeat = [0] * 8
        self.confirmed = [False] * 8
        self.pick = 0
        self.lk_page = 0
        self.menu = None
        self.port = port                    # usb_cdc.data: MP1 Link (None if boot.py didn't turn it on)
        self.link = None                    # link.py, once the page has connected
        self.clock_set = False
        self.mode_until = None              # a picker / message closes at this time
        self.pick_cards = False             # the picker shows layer cards (not a list)
        self.hold_view = None               # (keymap stamp, the HOLD+KEY screen's 8 keys): drawn once, shown at once
        from ember.extras import Extras
        self.extras = Extras(self)          # the timer, counters, stamps, busy light, reminders (extras.py)
        self.tool_view = None               # the Timer / Counter screen while it's open
        self.saver = None                   # the bouncing clock while the pad is idle (extras.Saver)
        self.secret_pin = None              # the secret pages' PIN, once entered (until the pad is unplugged)
        self.pin_fails = 0
        self.pin_until = None               # three wrong PINs: no more tries until then
        self.jiggle_on = cfg["jiggle_at_start"]
        self.jiggle_at = clock.add(clock.now(), JIGGLE_EVERY[0])
        self.opts = None                    # (layer, jiggle, num_lock) the layer's own options were applied for
        self.layer_jiggle = False           # the jiggle is on because the layer asked for it
        self.num_tries = self.num_try_at = 0
        self.last_input = clock.now()
        self.sleep_state = 0                # 0 awake, 1 dimmed, 2 off
        # the encoder button
        self.b_raw = self.b_down = False
        self.b_changed = clock.now()
        self.b_at = 0
        self.b_used = False                 # something happened while held (a key, a turn, the menu)
        self.spin = self.spin_net = 0
        self.clicks = 0
        self.click_at = 0
        self.enc_pos = encoder.position
        self.last_turn = 0

    # ── what shows ──
    def show(self, index=None):
        """The layer view of layer `index` (default: the one we're on)."""
        if self.np_view is not None:        # (the Spotify screen closes)
            v, self.np_view = self.np_view, None
            v.close()
            from ember import forget
            forget("nowplay")
            gc.collect()
        if self.tool_view is not None and hasattr(self.tool_view, "closed"):
            v, self.tool_view = self.tool_view, None
            v.closed()                      # (the page's PIN entry: the page hears it was cancelled)
        self.tool_view = None               # (the Timer / Counter screen closes; the timer keeps going)
        x = self.extras
        if x.alarm_at is not None:          # (an alert closing: the alarm stops)
            x.alarm_at = None
            self.sound.stop()
        self.release_all()
        if index is not None:
            if index != self.index and self.sounds(SOUND_LAYERS):
                self.sound.play(self.sound.LAYER)
            self.index = index
        self.mode = NORMAL
        layer = self.layer = self.km.layer(self.index)
        s = self.km.SECRET
        enc = "{}/{}".format(s.index(self.index) + 1, len(s)) if self.index in s else layer.enc_label    # (a secret page: which)
        st = x.status(clock.now())
        x.status_shown = st
        if st and self.index not in s:      # (the timer's time left / BUSY in place of the encoder label)
            enc = st
        self._cells(layer.name, enc, layer)
        self.layer = self.km.layer(self.index)

    def _cells(self, title, enc_label, layer, labels=None):
        keys = []
        for k in range(8):
            if labels is not None:
                keys.append((labels[k], None) if labels[k] else None)
            else:
                keys.append((layer.labels[k], picture(layer.pics[k])) if layer.present[k] else None)
        self.screen.show_layer(title, enc_label, keys)
        keys = None
        gc.collect()
        self.dirty = True

    def sounds(self, part):
        """Is this kind of sound on (the "sounds" setting's switch, and Sound not turned off)?"""
        s = self.cfg["sounds"]
        return self.sound_on and part < len(s) and s[part] == "1"

    def status_right(self, text):
        """extras.py: the top row's right side changed (the time left each second, BUSY, or back to the label)."""
        if self.mode == NORMAL and self.layer is not None and not self.km.is_secret(self.index):
            self.screen.set_right(text or self.layer.enc_label)
            self.dirty = True

    def alert(self, title, text):
        """The timer ended / a reminder: the screen wakes and says so (big), the alarm sounds and the lights flash
        until a key, a turn or a click (the alarm stops by itself after a minute)."""
        now = clock.now()
        self.wake(now)
        self.show()
        if text:
            from ember.screen import text_width, fit
            lines, cur = [], ""
            for word in text.split(" "):
                t = cur + " " + word if cur else word
                if text_width(t) <= 120:
                    cur = t
                else:
                    if cur:
                        lines.append(cur)
                    cur = fit(word, 120)
            lines.append(cur)
            self.screen.show_list(title, lines[:4])
        else:
            self.screen.show_card(title, None)
        self.mode = MESSAGE
        self.mode_until = clock.add(now, ALERT_MS)
        self.dirty = True
        self.extras.alarm_at = now
        if self.sounds(SOUND_ALARMS):
            self.sound.play(self.sound.ALARM, loop=True)

    def open_view(self, which):
        """The Timer or the Counter screen (extras.py), over the layer; hold the encoder to go back."""
        self.show()
        from ember import extras
        self.mode = TOOLVIEW
        self.tool_view = (extras.TimerView if which == "timer" else extras.CounterView)(self)

    def message(self, title, lines, ms=MESSAGE_TIME):
        self.screen.show_list(title, lines)
        self.mode = MESSAGE
        self.mode_until = clock.add(clock.now(), ms)
        self.dirty = True

    def release_all(self):
        for k in range(8):
            if self.held[k]:
                self.actions.release(self.held[k])
                self.held[k] = None
            self.down_at[k] = None
            self.screen.press(k, False)

    # ── the pad's own functions (encoder gestures, "tool" and "layer" actions) ──
    def run_tool(self, kind, value):
        if kind == "number":                # a counter's next number, typed
            self.actions.write(self.extras.next_number(value))
            return
        if kind == "stamp":                 # the date / time, typed
            s = self.extras.stamp(value)
            if s is None:
                self.message("CLOCK NOT SET", ["Open the MP1 Ember", "page once after the", "pad is plugged in."], 3000)
            else:
                self.actions.write(s)
            return
        if kind == "layer":
            i = self.km.find(value)
            if i is None:
                self.message("NO LAYER", [value])
            else:
                self.show(i)
            return
        f = value
        if f == "none" or not f:
            return
        if f == "home_layer":
            self.show(self.km.HOME)
        elif f == "layer_picker":
            self.open_picker()
        elif f == "layer_keys":
            self.open_layer_keys()
        elif f == "layer_cards":
            self.open_picker(True)
        elif f == "show_layer":
            self.message(self.layer.name, ["", "   " + self.layer.name])
        elif f in gestures.MEDIA:
            self.actions.cc.send(gestures.MEDIA[f])
        elif f == "panic":
            self.actions.panic()
            self.message("PANIC!", ["Media paused", "Windows minimized", "Volume down"])
        elif f == "spotify":
            self.open_np()
        elif f in ("timer", "counter"):
            self.open_view(f)
        elif f == "busy":
            x = self.extras
            x.busy = not x.busy
            self.message("BUSY LIGHT", ["On: the lights are red" if self.lights.pixels is not None else "On",
                                        "and BUSY shows on top."] if x.busy else ["Off"])
        elif f == "jiggle":
            self.jiggle_on = not self.jiggle_on
            self.message("MOUSE JIGGLE", ["On" if self.jiggle_on else "Off"])
        elif f == "lock":
            self.release_all()
            self.mode = LOCKED
            self.screen.show_list("LOCKED", ["Keys and encoder", "are locked.", "Hold the encoder", "3 s to unlock."])
            self.dirty = True
        elif f == "tools_menu":
            self.open_tools()
        elif f in ("secret", "secret2"):
            self.toggle_secret(2 if f == "secret2" else 1)      # (Secret pages / Secret page 2)
        elif f == "lights":
            self.lights_on = not self.lights_on
            self.message("LIGHTS", ["On" if self.lights_on else "Off (until restart)"])
        elif f == "sound":
            self.sound_on = not self.sound_on
            self.message("SOUND", ["On" if self.sound_on else "Off (until restart)"])
        else:
            self.message("UNKNOWN", [f])

    # ── the TOOLS menu (menus.py, loaded only while it's open) ──
    def open_tools(self):
        self.release_all()
        from ember.menus import Menu
        self.menu = Menu(self.cfg, self.lights.pixels is not None, self.hw.get("buzzer", "none") != "none")
        self.mode = MENU
        self.draw_menu()

    def draw_menu(self):
        title, rows, sel, right = self.menu.view(self.menu_state)
        self.screen.show_list(title, rows, sel, right)
        self.mode_until = clock.add(clock.now(), MENU_IDLE)
        self.dirty = True

    def menu_state(self, label):
        if label == "Mouse jiggle":
            return "On" if self.jiggle_on else "Off"
        if label == "Busy light":
            return "On" if self.extras.busy else "Off"
        if label == "Timer" and self.extras.status(clock.now()):
            return self.extras.status(clock.now())
        if label == "Drive":
            return "Shown" if drive_shown() else "Hidden"
        return ""

    def menu_click(self):
        r = self.menu.click()
        if r is None:
            self.draw_menu()
        elif r.startswith("set:"):
            self.apply(r[4:])
            self.draw_menu()
        elif r == "Mouse jiggle":
            self.jiggle_on = not self.jiggle_on
            self.draw_menu()
        elif r == "Busy light":
            self.extras.busy = not self.extras.busy
            self.draw_menu()
        elif r in ("Timer", "Counter"):
            self.close_menu()
            self.open_view(r.lower())
        elif r == "Lock keys":
            self.close_menu()
            self.run_tool("tool", "lock")
        elif r == "Drive":
            self.close_menu()
            self.toggle_drive()
        elif r == "About":
            self.close_menu()
            self.about()
        else:
            self.close_menu()

    def apply(self, name):
        """A setting changed in the menu: put it into effect now."""
        cfg, hw = self.cfg, self.hw
        if name == "key_lines":
            self.screen.set_key_lines(cfg["key_lines"])
        elif name == "lock_boxes":
            self.screen.locks_shown = cfg["lock_boxes"]
        elif name == "light_level":
            hw["led_level"] = cfg["light_level"]
        elif name == "light_scene":
            hw["led_scene"] = cfg["light_scene"]
        elif name == "sound_level":
            hw["buzzer_level"] = cfg["sound_level"]
            self.sound.play(((2000, 0.08),))

    def close_menu(self):
        """Leave the TOOLS menu; save the settings if any changed."""
        menu, self.menu = self.menu, None
        from ember import forget
        forget("menus")
        saved = True
        if menu is not None and menu.changed:
            from ember import settings
            saved = settings.save(self.cfg)
            forget("settings")
        self.show()
        if not saved:
            self.message("NOT SAVED", ["The drive is showing on", "the computer: settings", "last until a restart."], 4000)
        gc.collect()

    def toggle_drive(self):
        """Restart with the drive shown on the computer (or hidden again)."""
        show = not drive_shown()
        try:
            import microcontroller
            nvm = microcontroller.nvm
            at = len(nvm) - DRIVE_SLOT
            nvm[at:at + 4] = b"MP1D" if show else b"MP1R"
        except Exception:
            self.message("DRIVE", ["Not possible"])
            return
        self.actions.release_all()
        self.screen.show_list("DRIVE", ["Restarting with the", "drive " + ("shown." if show else "hidden.")])
        self.screen.refresh()
        time.sleep(1)
        microcontroller.reset()

    def about(self):
        gc.collect()
        self.message("MP1 EMBER 01", [("Free memory", "{} KB".format(gc.mem_free() // 1024)),
                                      ("Layers", str(len(self.km.NAMES))),
                                      ("Problems", str(len(self.errors))),
                                      ("Drive", "Shown" if drive_shown() else "Hidden")], 6000)

    # ── MP1 Link syncing (link.py): nothing else runs ──
    def enter_sync(self, title):
        if self.menu is not None:
            self.close_menu()
        self.release_all()
        self.mode = SYNC
        self.screen.show_list(title, ["MP1 Link is reading or", "saving the pad's files.", "", "The keys wait for it."])
        self.screen.refresh()

    def sync_progress(self, pct):
        try:
            pct = max(0, min(100, int(pct)))
        except (TypeError, ValueError):
            return
        self.screen.show_list("SYNCING", ["MP1 Link is reading or", "saving the pad's files.", "",
                                          ("The keys wait for it.", "{}%".format(pct))])
        self.dirty = True

    def leave_sync(self):
        self.mode = NORMAL
        try:
            self.keys.events.clear()
        except AttributeError:
            pass
        self.enc_pos = self.encoder.position
        self.clicks = 0
        self.last_input = clock.now()
        self.show()

    def gesture(self, setting):
        self.run_tool("tool", self.cfg[setting])

    # ── the layer picker and layer keys ──
    def regular_index(self):
        """The layer we're on, or (on a secret layer) the one it goes back to: for the picker and layer keys."""
        return self.prev_index if self.km.is_secret(self.index) else self.index

    def toggle_secret(self, page=1):
        """The secret pages: open at `page` (1 = the first; the "secret" function), or close them if they're
        showing. The encoder turns the pages (secret_turn)."""
        s = self.km.SECRET
        if not s and self.km.PIN:           # a PIN first (once after the pad is plugged in)
            self.ask_pin(page)
            return
        if not s:
            note = self.km.SECRET_NOTE
            if note in ("no secret.json", "0 pages", ""):
                self.message("SECRET", ["No secret pages yet:", "make one in the page", "(Layers, + Secret page)."])
            else:                           # (they exist but didn't load: say why)
                print("secret pages didn't load:", note)
                self.message("SECRET", ["Secret pages didn't", "load: " + note[:18], note[18:40], "The page: Reload them"], 4000)
            return
        if self.km.is_secret(self.index):
            self.show(self.prev_index)
            return
        self.prev_index = self.index
        self.show(s[min(page, len(s)) - 1])

    def ask_pin(self, page):
        now = clock.now()
        if self.pin_until is not None and clock.diff(now, self.pin_until) < 0:
            self.message("LOCKED", ["A wrong PIN 3 times:", "try again in a minute."], 3000)
            return
        self.pin_until = None
        self.show()
        from ember.extras import PinView
        self.mode = TOOLVIEW
        self.tool_view = PinView(self, page)

    def unlock_secret(self, pin):
        """Open the secret pages with this PIN: the keymap read again with it. True if it was right."""
        from ember import keymap as loader, forget
        km = loader.load("/", pin)
        loader = None
        forget("keymap")
        if km.PIN:
            km = None
            gc.collect()
            return False
        self.km, self.secret_pin, self.pin_fails, self.hold_view = km, pin, 0, None
        self.layer = km.layer(self.index)
        gc.collect()
        return True

    def secret_turn(self, step):
        """On a secret page the encoder turns the pages (and sends nothing)."""
        s = self.km.SECRET
        self.show(s[(s.index(self.index) + step) % len(s)])

    def secret_timeout(self, now):
        secs = self.cfg["secret_lock_seconds"]
        if secs and self.mode == NORMAL and self.km.is_secret(self.index) and since(self.last_input, now) > secs * 1000:
            self.show(self.prev_index)

    def open_picker(self, cards=False):
        """The layer picker: a list, or one big card a layer (Layer cards). Turn, click to pick, hold to close."""
        self.mode = PICKER
        self.pick_cards = cards
        self.pick = self.regular_index()
        self.draw_picker()

    def draw_picker(self):
        names = self.km.NAMES
        where = "{}/{}".format(self.pick + 1, len(names))
        if self.pick_cards:
            card = self.km.layer(self.pick).card
            self.screen.show_card(names[self.pick], picture(card), "HOME" if self.pick == self.km.HOME else "", where)
            card = None
            gc.collect()
        else:
            rows = [(n, "home" if i == self.km.HOME else "") for i, n in enumerate(names)]
            self.screen.show_list("LAYERS", rows, self.pick, where)
        self.mode_until = clock.add(clock.now(), MENU_TIMEOUT)
        self.dirty = True

    def open_layer_keys(self):
        self.mode = LAYER_KEYS
        self.pick = self.regular_index()        # the highlight: turn moves it, click picks it
        self.lk_page = self.pick // 8
        self.draw_layer_keys()

    def draw_layer_keys(self):
        names = self.km.NAMES[self.lk_page * 8:self.lk_page * 8 + 8]
        labels = [names[k] if k < len(names) else "" for k in range(8)]
        pages = (len(self.km.NAMES) + 7) // 8
        self._cells("PICK A LAYER", "{}/{}".format(self.lk_page + 1, pages) if pages > 1 else "", None, labels)
        cur = self.pick - self.lk_page * 8
        if 0 <= cur < 8:
            self.screen.press(cur, True)        # the highlighted layer, lit
        self.mode_until = clock.add(clock.now(), MENU_TIMEOUT)

    # ── keys ──
    def key(self, k, pressed, now):
        if self.mode == LOCKED:
            return
        if self.b_down:                         # HOLD+KEY
            if pressed:
                self.b_used = True
                self.hold_key(k)
            return
        if self.mode == NOWPLAY:
            self.np_view.key(k, pressed, now)
            return
        if self.mode == TOOLVIEW:
            self.tool_view.key(k, pressed, now)
            return
        if self.mode == LAYER_KEYS:
            if pressed:
                i = self.lk_page * 8 + k
                if i < len(self.km.NAMES):
                    self.show(i)
            return
        if self.mode != NORMAL:                 # in a menu / picker / message a key press only closes it: nothing is sent
            if not pressed:
                self.screen.press(k, False)     # (a release still lets go of whatever the key held, below)
            elif self.mode == MENU:
                self.close_menu()
                return
            else:
                self.show()
                return
        layer = self.layer
        self.screen.press(k, pressed)
        self.dirty = True
        action = layer.keys[k]
        if pressed:
            self.lights.react(now)
            if self.sounds(SOUND_KEYS):
                self.sound.click()
            self.down_at[k] = now
            self.confirmed[k] = False
            if not action or layer.confirm[k]:
                return                          # (a confirm key fires once held long enough)
            self.actions.press(action, layer.speed[k])
            if action[0] in ("key", "combo", "click"):
                self.held[k] = action
            elif layer.repeat[k]:
                self.next_repeat[k] = clock.add(now, REPEAT[self.cfg["repeat_speed"]][0])
        else:
            self.down_at[k] = None
            if self.held[k]:
                self.actions.release(self.held[k])
                self.held[k] = None

    def hold_key(self, k):
        hk = self.km.HOLD
        if hk is None:
            return
        layer = self.km.layer(hk)
        action = layer.keys[k]
        self.layer = None
        if action:
            self.actions.press(action, layer.speed[k])
            if action[0] in ("key", "combo", "click"):
                time.sleep(0.01)
                self.actions.release(action)
        self.layer = self.km.layer(self.index)

    def keys_held(self, now):
        """Repeat keys and confirm keys while they're held."""
        layer = self.layer
        for k in range(8):
            t = self.down_at[k]
            if t is None or self.mode != NORMAL:
                continue
            action = layer.keys[k]
            if not action:
                continue
            if layer.confirm[k]:
                if not self.confirmed[k] and since(t, now) >= CONFIRM:
                    self.confirmed[k] = True
                    self.actions.tap(action, layer.speed[k])
                    self.screen.press(k, False)     # the flash ends: it went
                    self.dirty = True
            elif layer.repeat[k] and clock.diff(now, self.next_repeat[k]) >= 0:
                self.actions.press(action, layer.speed[k])
                self.next_repeat[k] = clock.add(now, REPEAT[self.cfg["repeat_speed"]][1])

    # ── the encoder ──
    def turn(self, delta, now):
        if self.cfg["encoder_reverse"]:
            delta = -delta
        step = 1 if delta > 0 else -1
        if self.b_down:
            self.spin += abs(delta)
            self.spin_net += delta
            if not self.b_used and self.spin >= HOLD_TURN and self.mode in (NORMAL, HOLD):
                self.b_used = True
                self.show()
                self.gesture("hold_turn_right" if self.spin_net > 0 else "hold_turn_left")
            return
        if self.mode == LOCKED:
            return
        if self.mode == MENU:
            name = self.menu.turn(step)
            if name:
                self.apply(name)
            self.draw_menu()
            return
        if self.mode == PICKER:
            self.pick = (self.pick + step) % len(self.km.NAMES)
            self.draw_picker()
            return
        if self.mode == LAYER_KEYS:             # the highlight moves layer by layer; the page follows it
            self.pick = (self.pick + step) % len(self.km.NAMES)
            if self.pick // 8 != self.lk_page:
                self.lk_page = self.pick // 8
                self.draw_layer_keys()
            else:
                for k in range(8):
                    self.screen.press(k, k == self.pick - self.lk_page * 8)
                self.mode_until = clock.add(now, MENU_TIMEOUT)
                self.dirty = True
            return
        if self.mode == NOWPLAY:
            self.np_view.turn(delta, now)
            return
        if self.mode == TOOLVIEW:
            self.tool_view.turn(step, now)
            return
        if self.mode == MESSAGE:                # a turn closes a message, and sends nothing
            self.show()
            return
        if self.km.is_secret(self.index):       # a secret page: the encoder turns the pages, and sends nothing
            self.secret_turn(step)
            return
        gap = since(self.last_turn, now)
        self.last_turn = now
        speed = 4 if gap < FAST else 2 if gap < MEDIUM else 1
        self.actions.turn(self.layer, delta, speed)

    def button_changed(self, down, now):
        if down:
            self.b_down = True
            self.b_at = now
            self.b_used = False
            self.spin = self.spin_net = 0
            return
        self.b_down = False
        held = since(self.b_at, now)
        if self.mode == LOCKED:
            return
        was = self.mode
        if self.mode == HOLD:
            self.show()
        if self.b_used:
            return
        if was == NOWPLAY:                  # a click on the Spotify screen: back to the layer
            self.show()
            return
        if was == TOOLVIEW:                 # a click on the Timer / Counter screen: start, pause, count
            self.tool_view.click(now)
            return
        if was in (NORMAL, HOLD) and held >= LONG_PRESS and self.spin < 2:
            self.gesture_tools()            # a long press, nothing else done: the TOOLS menu
            return
        if self.mode == MENU:
            self.menu_click()
        elif self.mode in (PICKER, LAYER_KEYS):
            self.show(self.pick)
        elif self.mode == MESSAGE:
            self.show()
        else:
            self.clicks += 1
            self.click_at = now

    def button_held(self, now):
        """While the button is down: the HOLD+KEY screen, closing a menu / picker, unlocking."""
        held = since(self.b_at, now)
        if self.mode == LOCKED:
            if held >= UNLOCK:
                self.b_used = True
                self.show()
                self.message("UNLOCKED", ["Keys and encoder", "work again."])
            return
        if self.b_used:
            return
        if self.mode in (PICKER, LAYER_KEYS, MENU, TOOLVIEW) and held >= LONG_PRESS:     # hold = close (a menu saves)
            self.b_used = True
            if self.mode == MENU:
                self.close_menu()
            else:
                self.show()
            return
        if held >= HOLD_SCREEN and self.mode == NORMAL and self.km.HOLD is not None and self.spin < 2:
            self.screen.show_layer("HOLD+KEY", "", self.hold_keys(), True)      # (inverted: black on white)
            self.dirty = True
            self.mode = HOLD

    def hold_keys(self):
        """The HOLD+KEY screen's keys (label, picture Bitmap), made once and kept until the keymap changes, so the
        screen shows the moment the button has been held long enough."""
        stamp = (id(self.km), id(self.km.blob))
        if self.hold_view is None or self.hold_view[0] != stamp:
            self.hold_view = None
            gc.collect()
            hold = self.km.layer(self.km.HOLD)
            keys = [(hold.labels[k], picture(hold.pics[k])) if hold.present[k] else None for k in range(8)]
            hold = None
            self.layer = self.km.layer(self.index)      # (the layer showing stays the one unpacked)
            self.hold_view = (stamp, keys)
            gc.collect()
        return self.hold_view[1]

    def open_np(self):
        """The Spotify screen (nowplay.py), over the layer; a click goes back."""
        if self.np_view is not None:
            return
        self.release_all()
        from ember.nowplay import View
        self.mode = NOWPLAY
        self.np_view = View(self)

    def gesture_tools(self):
        self.run_tool("tool", "tools_menu")

    # ── the loop ──
    def wake(self, now):
        """Any input: back from dim / off. True if the pad was off (that input only wakes it)."""
        self.last_input = now
        if self.sleep_state:
            was_off = self.sleep_state == 2 or self.saver is not None     # (the clock showing: that input only wakes it)
            self.sleep_state = 0
            if self.saver is not None:
                self.saver = None
                self.show()
            try:
                self.display.wake()
                self.display.brightness = 1.0
            except Exception:
                pass
            return was_off
        return False

    def idle(self, now):
        quiet = since(self.last_input, now) // 60000
        dim, off = self.cfg["screen_dim_minutes"], self.cfg["screen_off_minutes"]
        try:
            if off and quiet >= off and self.sleep_state < 2:
                self.sleep_state = 2
                self.saver = None
                self.display.sleep()
            elif dim and quiet >= dim and self.sleep_state < 1:
                self.sleep_state = 1
                if self.cfg["idle_screen"] == "clock" and self.mode == NORMAL:
                    from ember.extras import Saver
                    self.display.brightness = 0.3
                    self.saver = Saver(self)
                else:
                    self.display.brightness = 0.05
        except Exception:
            self.sleep_state = max(self.sleep_state, 1)

    def service(self, now):
        """Sound patterns and the light animation."""
        self.sound.update(now)
        lights = self.lights
        if lights.pixels is None:
            return
        own = self.extras.lights()          # (the alarm flashing, or the busy light: red)
        if own is not None:
            lights.update(now, own[0], lights.color(own[1]), None, max(self.cfg["light_level"], 6), 5)
            return
        if not self.lights_on or (self.sleep_state == 2 and not self.cfg["lights_asleep"]):
            lights.update(now, "off", None, None)
            return
        cfg = self.cfg
        n1, n2 = cfg["light_color1"], cfg["light_color2"]
        if (n1, n2) != self.color_names:
            self.color_names = (n1, n2)
            self.colors = (lights.color(n1), lights.color(n2))
        scene, (c1, c2), level, speed = cfg["light_scene"], self.colors, None, 0
        own = self.layer.lights if self.layer else None
        if own:
            scene, c1, c2, level, speed = own[0], own[1] or c1, own[2] or c2, own[3], own[4]
        lights.update(now, scene, c1, c2, level, speed)

    def layer_options(self, now):
        """The showing layer's own "jiggle" and "num_lock", applied when the layer (or they) change."""
        layer = self.layer
        if layer is None:
            return
        opts = (self.index, layer.jiggle, layer.num_lock)
        if opts == self.opts:
            return
        self.opts = opts
        if layer.jiggle and not self.jiggle_on:
            self.jiggle_on = self.layer_jiggle = True
            self.jiggle_at = now
        elif not layer.jiggle and self.layer_jiggle:
            self.layer_jiggle = self.jiggle_on = False
        self.num_tries = NUM_LOCK_TRIES if layer.num_lock else 0
        self.num_try_at = clock.add(now, -NUM_LOCK_RETRY_MS)

    def keep_num_lock(self, now, num):
        layer = self.layer
        if layer is None or not layer.num_lock:
            return
        if num:
            self.num_tries = NUM_LOCK_TRIES     # on again: ready if it's turned off later
        elif num is False and self.num_tries and since(self.num_try_at, now) >= NUM_LOCK_RETRY_MS:
            self.num_tries -= 1
            self.num_try_at = now
            from ember.actions import NUM_LOCK_KEY
            self.actions.tap(NUM_LOCK_KEY)

    def wait(self, seconds):
        """Pause (a macro's delay) without freezing the lights and sound; a stop ends it (actions.Stopped)."""
        end = clock.add(clock.now(), clock.ms(seconds))
        while clock.diff(clock.now(), end) < 0:
            self.service(clock.now())
            self.actions.check()
            time.sleep(0.01)

    # ── stopping a running macro: a fresh key press, a turn, or a fresh press of the encoder ──
    def stop_begin(self):
        self.stop_seen = 0
        self.stop_button = not self.button.value
        self.prog_start, self.prog_at = clock.now(), None

    def stop_wanted(self):
        now = clock.now()
        if since(self.stop_seen, now) < 30:     # (looked at most every 30 ms)
            return False
        self.stop_seen = now
        if self.stop_event is None:
            import keypad
            self.stop_event = keypad.Event()
        e, ev = self.stop_event, self.keys.events
        while ev.get_into(e):
            k = e.key_number
            if k >= 8:
                continue
            if e.pressed:                       # (this press only stops it; its release comes later as usual)
                return True
            self.down_at[k] = None              # a release while it runs (the key that started it): handled now
            if self.held[k]:
                self.actions.release(self.held[k])
                self.held[k] = None
            self.screen.press(k, False)
            self.dirty = True
        pos = self.encoder.position
        if pos != self.enc_pos:
            self.enc_pos = pos                  # (the turn only stops it)
            return True
        down = not self.button.value
        if down and not self.stop_button:   # the encoder pressed: pause (macro_pause), not stop
            self.stop_button = True
            return "pause"
        self.stop_button = down
        return False

    def _prog_text(self, step, steps, mark):
        if mark:
            return "Row {} of {}".format(mark[0], mark[1])
        return "{}%".format(step * 100 // max(1, steps)) if steps else ""

    def macro_progress(self, step, steps, mark):
        """A step of a macro done: its progress screen (after it's run a moment), redrawn now and then."""
        now = clock.now()
        if self.prog_start is None or since(self.prog_start, now) < PROGRESS_AFTER:
            return
        if self.prog_at is not None and since(self.prog_at, now) < PROGRESS_EVERY:
            return
        self.prog_at = now
        self.screen.show_list("RUNNING", [self._prog_text(step, steps, mark), "", "Click: pause", "Key or turn: stop"])
        self.screen.refresh()

    def macro_pause(self, note):
        """A running macro paused (the encoder pressed, or a {PAUSE} step): the screen says so until a click (go on);
        any key or a turn stops it (True). The press that paused it, and the click that goes on, do nothing else."""
        self.actions.release_all()
        lines = [note or "Paused.", self._prog_text(0, 0, self.actions.mark) if self.actions.mark else "",
                 "Click: go on", "Key or turn: stop"]
        self.screen.show_list("PAUSED", lines)
        self.screen.refresh()
        import keypad
        e, ev = self.stop_event or keypad.Event(), self.keys.events
        self.stop_event = e
        letting_go = not self.button.value      # (the press that paused it: first it's let go)
        clicking = False
        while True:
            self.service(clock.now())
            while ev.get_into(e):
                if e.key_number < 8 and e.pressed:
                    return True
            pos = self.encoder.position
            if pos != self.enc_pos:
                self.enc_pos = pos
                return True
            down = not self.button.value
            if letting_go:
                letting_go = down
            elif down:
                clicking = True
            elif clicking:
                break                           # pressed and let go: a click, go on
            time.sleep(0.02)
        self.stop_button = False
        self.b_raw = self.b_down = False        # (that click: nothing more)
        self.b_changed = clock.now()
        self.prog_at = None
        self.screen.show_list("RUNNING", [self._prog_text(0, 0, self.actions.mark) if self.actions.mark else "Going on…", "",
                                          "Click: pause", "Key or turn: stop"])
        self.screen.refresh()
        return False

    def macro_finished(self):
        """The outer key press is over: the progress screen (if it showed) gives way to the layer."""
        if self.prog_at is not None and self.mode == NORMAL:
            self.prog_at = None
            self.show()
            self.screen.refresh()
        self.prog_start = None

    def macro_stopped(self):
        if self.swallow_button:
            self.b_down = self.b_raw = True     # (the press that stopped it: its click does nothing)
            self.b_used = True
            self.b_at = clock.now()
            self.b_changed = clock.now()
            self.swallow_button = False
        self.message("STOPPED", ["", "The macro stopped.", "Nothing more is typed."])
        self.screen.refresh()

    def run(self):
        if self.sounds(SOUND_BOOT):
            self.sound.play(self.sound.STARTUP)
        self.screen.set_key_lines(self.cfg["key_lines"])
        self.screen.locks_shown = self.cfg["lock_boxes"]
        self.show()
        if self.errors:
            for e in self.errors:
                print("PROBLEM:", e)
            self.message("PROBLEMS", self.errors[:4] + ["(more on the console)"] * (len(self.errors) > 4), 6000)
        print("Ember running, free", gc.mem_free())
        import keypad
        event = keypad.Event()
        ev = self.keys.events
        locks_at = clock.now()
        while True:
            now = clock.now()
            if self.link is None and self.port is not None and self.port.connected:
                from ember.link import Link
                self.link = Link(self, self.port)
            if self.link is not None:
                if self.mode == SYNC:
                    self.link.sync_tick(now)
                    if self.dirty:
                        self.screen.refresh()
                        self.dirty = False
                    continue
                self.link.tick(now)
            while ev.get_into(event):
                if event.key_number < 8:
                    if self.wake(now):
                        continue
                    self.key(event.key_number, event.pressed, now)
            pos = self.encoder.position
            if pos != self.enc_pos:
                delta = pos - self.enc_pos
                self.enc_pos = pos
                if not self.wake(now):
                    self.turn(delta, now)
            raw = not self.button.value
            if raw != self.b_raw:
                self.b_raw = raw
                self.b_changed = now
            elif raw != self.b_down and since(self.b_changed, now) >= DEBOUNCE:
                if not self.wake(now) or not raw:
                    self.button_changed(raw, now)
            if self.b_down:
                self.button_held(now)
            if self.clicks and not self.b_down and since(self.click_at, now) > MULTI_CLICK:
                n, self.clicks = self.clicks, 0
                self.gesture(("click_single", "click_double", "click_triple")[min(n, 3) - 1])
            if self.mode in (PICKER, LAYER_KEYS, MESSAGE, MENU) and self.mode_until is not None \
                    and clock.diff(now, self.mode_until) >= 0:
                self.mode_until = None
                if self.mode == MENU:
                    self.close_menu()
                else:
                    self.show()
            self.keys_held(now)
            self.secret_timeout(now)
            if self.np_view is not None:
                self.np_view.tick(now)
            self.extras.tick(now)
            if self.saver is not None:
                self.saver.tick(now)
            self.service(now)
            self.layer_options(now)
            if self.jiggle_on and clock.diff(now, self.jiggle_at) >= 0:
                self.actions.jiggle(1)
                self.jiggle_at = clock.add(now, random.randint(*JIGGLE_EVERY))
            if since(locks_at, now) >= LOCKS_EVERY:
                locks_at = now
                caps, num = self.actions.caps_lock(), self.actions.num_lock()
                self.keep_num_lock(now, num)
                if (bool(caps), bool(num)) != (self.screen.caps, self.screen.num):
                    self.screen.set_locks(bool(caps), bool(num))
                    self.dirty = self.mode == NORMAL or self.dirty
                self.idle(now)
            if self.dirty:
                self.screen.refresh()
                self.dirty = False
            time.sleep(0.002)
