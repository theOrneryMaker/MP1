# /lib/macropad/app.py
# The macropad's main loop: one mode at a time, each input routed by mode.
#
#   ERRORS    boot-time keymap/settings problems (or a runtime error): turn = next, press = continue
#   NORMAL    keys run the current layer, knob runs the layer's encoder action
#   LAYERS    short press: pick a layer          (opens on short press)
#   SETTINGS  TIMER / CONFIG / GESTURES / LIGHTS* / SOUND* / KEYMAPPER / ABOUT / EXIT   (long press)
#             (* only when that add-on is switched on in settings.js)
#   TIMER     keys are timer controls, knob adjusts time, any press exits
#   STOPWATCH keys are stopwatch controls (RST / PLAY / PAUS), any press exits;
#             keeps running in the background (top bar shows SW m:ss)
#   CONFIG    edit settings (CONFIG, GESTURES, LIGHTS and SOUND menus)
#   LAYER_KEYS each key shows a layer name; press a key to jump to that layer,
#             knob = next/previous page of 8 (more than 8 layers), button = exit
#
# Encoder button in NORMAL mode: click = Layers menu, double/triple click, hold+turn and
# click-then-hold+turn
# run the functions chosen in GESTURES (see gestures.py). Clicks are counted until the
# CLICK TIME window passes with no further press.
# Screen saver: after DIM AFTER minutes idle the OLED dims, after OFF AFTER it switches
# off (LEDs too, if LEDS OFF). Any input wakes it; while it's off, that first input only
# wakes it (keys can't be seen, so nothing is sent).
#   ALERT     timer finished: flashing DONE + alarm; tap = dismiss, double tap = back to timer

#
# The App class is split over several files so each one compiles in the RP2040's RAM:
#   app.py       main loop, screens, timeouts, indicators, keys
#   controls.py  encoder turns and button presses (clicks, hold + turn)
#   commands.py  gesture functions, menu selections, layer switching
#   extras.py    layer keys, menu reel animation, stopwatch, screen saver, Caps Lock

import time
import random
from macropad import timer, sound, clock, stopwatch
from macropad.clock import since, ms
from macropad.lights import color
from macropad.menus import ListMenu, ConfigMenu
from macropad.modes import *    # noqa: F401,F403  (mode numbers and other constants)
from macropad.controls import Controls
from macropad.commands import Commands
from macropad.extras import Extras, LoopStats, wrap
from macropad.guard import Guard


class App(Controls, Commands, Extras):
    def __init__(self, keymap, cfg, screen, actions, keys, encoder, button, led, lights, sound_out, errors=()):
        self.km = keymap
        self.cfg = cfg
        self.screen = screen
        self.actions = actions
        self.keys = keys
        self.encoder = encoder
        self.button = button
        self.led = led
        self.lights = lights
        self.sound = sound_out
        self.errors = list(errors)
        self.timer = timer.Timer()
        self.stopwatch = stopwatch.Stopwatch()
        screen.wait = actions.wait = self.wait     # keep lights/sound running during pauses
        actions.feed = self.feed                   # long typing keeps the watchdog fed
        self.guard = None                          # hardware watchdog (started by run())

        now = clock.now()
        self.mode = NORMAL
        self.menu = None
        self.layer = self.prev_layer = keymap.DEFAULT_LAYER
        self.shown_layer = None                    # for the layer-change tone
        self.held = {}                  # key number -> action currently held down
        self.repeating = {}             # key number -> tick when it next repeats
        self.locked = False             # LOCK KEYS: only the unlock gesture works
        self.shown_lock = None          # lock page flash phase last drawn
        self.confirming = None          # hold-to-confirm: (key, action, pressed at)
        self.last_input = now           # for menu timeouts
        self.last_activity = now        # for the secret layer timeout
        self.jiggle_on = False
        self.jiggle_at = now            # last jiggle
        self.jiggle_wait = 0            # ms until the next one
        self.enc_pos = encoder.position
        self.last_turn = now
        self.button_down = False        # debounced state
        self.button_raw = False
        self.button_changed = now
        self.press_start = now
        self.spin = 0                   # encoder clicks while the button is held
        self.spin_net = 0               # clockwise minus counter-clockwise clicks
        self.spin_dir = 0               # direction of the hold + turn (+1 = clockwise)
        self.glitches = 0               # button contact flickers during this press
        self.alert_tap = None           # time of first tap while alert is showing
        self.blink_on = False
        self.blink_at = now
        self.error_index = 0
        self.clicks = 0                 # short clicks counted so far (double/triple click)
        self.click_at = now             # when the last one was released
        self.lights_off = False         # TOG LIGHTS (until restart)
        self.muted = False              # TOG SOUND (until restart)
        self.page = 0                   # LAYER_KEYS page
        self.rolling = False            # menu reel is turning (see roll_menu)
        self.roll_at = now
        self.roll_moves = ()
        self.roll_frame = -1
        self.shown_sw = None            # stopwatch tenths last drawn on its screen
        self.saver = AWAKE              # screen saver level
        self.last_wake = now            # last input of any kind (screen saver)
        self.ignore_release = False     # the button press that woke the screen
        self.caps = None                # Caps Lock state (None until first read)
        self.blink_phase = False        # shared blink clock (jiggle J, CAPS box)
        self.caps_at = now

        self.settings_menu = SETTINGS_MENU

        # Reused every pass so the main loop creates as little new data as possible
        # (fewer garbage-collection pauses)
        try:
            import keypad
            self.event = keypad.Event()
        except (ImportError, AttributeError):
            self.event = None
        self.color_names = (None, None)
        self.colors = (None, None)
        self.shown_timer = None           # (show, seconds, state, duration) last drawn
        self.shown_blink = None

    @property
    def current(self):
        return self.km.LAYERS[self.layer]

    def run(self):
        self.guard = Guard(self.cfg["watchdog"])
        if self.guard.restarted:
            self.errors.append("The watchdog restarted the macropad after it froze. If this "
                               "keeps happening, note what you were doing at the time.")
        if self.cfg["sound_startup"]:
            self.sound.play(sound.STARTUP)
        if self.errors:
            self.show_errors()
        else:
            self.show_layer(flash=True)
        stats = LoopStats() if self.cfg["loop_stats"] else None
        try:
            while True:
                if stats:
                    stats.start()
                try:
                    self.tick(clock.now())
                except Exception as e:      # never let one bad action take the macropad down
                    self.recover(e)
                self.feed()
                if stats:
                    stats.stop()
                time.sleep(self.cfg["main_loop_delay"])
        finally:                            # Ctrl+C: don't let the watchdog reset the console
            self.guard.stop()

    def feed(self):
        if self.guard is not None:
            self.guard.feed()

    def tick(self, now):
        if self.timer.poll():
            self.start_alert(now)
        self.check_timeouts(now)
        self.check_clicks(now)
        self.stopwatch.update(now)
        self.update_roll(now)
        self.update_stopwatch(now)
        self.update_saver(now)
        self.update_caps(now)
        self.update_alert(now)
        self.update_jiggle(now)
        self.update_repeat(now)
        self.update_confirm(now)
        self.update_indicators(now)
        self.update_lock()
        self.service(now)
        if self.event is not None:
            if self.keys.events.get_into(self.event):
                self.on_key(self.event)
        else:
            event = self.keys.events.get()
            if event:
                self.on_key(event)
        self.read_encoder(now)
        self.read_button(now)
        self.screen.refresh()           # one OLED update per pass, only if something changed

    def recover(self, error):
        self.actions.release_all()
        self.held.clear()
        self.repeating.clear()
        try:
            import traceback
            traceback.print_exception(error)
        except Exception:
            print("Runtime error:", error)
        message = "Runtime error: {}".format(error)
        if message not in self.errors:
            self.errors = (self.errors + [message])[-MAX_ERRORS:]
        self.error_index = self.errors.index(message)
        try:
            self.show_errors()
        except Exception:
            pass
        time.sleep(0.1)

    def service(self, now):
        """Background work: sound patterns and LED animation."""
        self.sound.update(now)
        if self.mode == ALERT:
            self.lights.update(now, "alert", None, None)
            return
        if self.lights.pixels is None:
            return
        if self.lights_off or (self.saver == OFF and self.cfg["screen_off_leds"]):
            self.lights.update(now, "off", None, None)
            return
        cfg = self.cfg
        n1, n2 = cfg["led_color1"], cfg["led_color2"]
        if n1 != self.color_names[0] or n2 != self.color_names[1]:
            self.color_names = (n1, n2)
            self.colors = (color(n1), color(n2))
        # The LIGHTS settings, unless this layer has lights of its own (they win)
        scene = cfg["led_scene"]
        c1, c2 = self.colors
        own = self.current.lights
        if own:
            scene, c1, c2 = own[0], own[1] or c1, own[2] or c2
        self.lights.update(now, scene, c1, c2)

    def wait(self, seconds):
        """Pause without freezing lights and sound."""
        start, total = clock.now(), ms(seconds)
        while True:
            now = clock.now()
            left = total - since(start, now)
            if left <= 0:
                return
            self.service(now)
            self.screen.refresh()
            self.feed()
            time.sleep(min(5, left) / 1000)

    def show_layer(self, flash=False):
        self.mode = NORMAL
        self.menu = None
        layer = self.current
        if (self.shown_layer is not None and self.shown_layer != self.layer
                and self.cfg["sound_layers"] and not self.muted):
            self.sound.play(sound.LAYER)
        self.shown_layer = self.layer
        if flash:
            self.screen.flash(layer.name, self.cfg["display_layer_flash_delay"])
        self.screen.show_keys(layer.icons, layer.enc_icon)

    def show_errors(self):
        self.mode = ERRORS
        total = len(self.errors)
        title = "ERROR {}/{} press=OK".format(self.error_index + 1, total)
        lines = wrap(self.errors[self.error_index])
        if len(lines) > MESSAGE_LINES:
            lines = lines[:MESSAGE_LINES]
            lines[-1] = lines[-1][:SCREEN_CHARS - 2] + ".."
        self.screen.show_text([title] + lines)

    def close(self):
        """Leave any menu/mode and go back to the current layer (or the lock page)."""
        if isinstance(self.menu, ConfigMenu):
            self.menu.cancel()
        if self.locked:
            self.show_lock()
            return
        self.show_layer(flash=True)
        self.last_activity = clock.now()

    def open_menu(self, mode, menu):
        self.mode = mode
        self.menu = menu
        self.draw_menu()

    def open_layers(self):
        regular = self.km.REGULAR_LAYERS
        current = regular.index(self.layer) if self.layer in regular else 0
        self.open_menu(LAYERS, ListMenu([self.km.LAYER_NAMES[i] for i in regular], current))

    def open_settings(self):
        hidden = []
        if self.cfg["led_count"] <= 0:
            hidden.append("lights")
        if self.cfg["buzzer"] == "none":
            hidden.append("sound")
        self.settings_menu = [item for item in SETTINGS_MENU if item[1] not in hidden]
        self.open_menu(SETTINGS, ListMenu([item[0] for item in self.settings_menu]))

    def open_timer(self):
        self.mode = TIMER
        self.menu = None
        self.draw_timer()

    def draw_menu(self):
        self.rolling = False
        if self.mode == CONFIG and self.menu.editing:
            text = self.menu.value_text()
            self.screen.show_big(text, scale=3 if len(text) <= 7 else 2,
                                 title=self.menu.items[self.menu.selection])
        else:
            self.screen.show_menu(*self.menu.view())

    def draw_timer(self):
        self.screen.show_keys(timer.ICONS, self.timer.status_icon())

    def start_alert(self, now):
        self.wake(now)
        if isinstance(self.menu, ConfigMenu):
            self.menu.cancel()
        self.mode = ALERT
        self.menu = None
        self.clicks = 0
        self.alert_tap = None
        self.blink_on = True
        self.blink_at = now
        self.screen.show_big("DONE", scale=3)
        self.sound.play(sound.ALARM, loop=True)

    def check_timeouts(self, now):
        if self.mode == NORMAL:
            if self.layer in self.km.SECRET_LAYERS and since(self.last_activity, now) > ms(self.cfg["secret_timeout"]):
                self.layer = self.prev_layer
                self.show_layer(flash=True)
            return
        if self.mode == LAYERS or self.mode == LAYER_KEYS:
            limit = self.cfg["menu1_timeout"]
        elif self.mode == SETTINGS:
            limit = self.cfg["menu2_timeout"]
        elif self.mode == STOPWATCH and self.stopwatch.state == stopwatch.RUNNING:
            limit = None                # stay while it's counting
        else:
            limit = FIXED_TIMEOUTS.get(self.mode)
        if limit and since(self.last_input, now) > ms(limit):
            self.close()

    def update_alert(self, now):
        if self.mode != ALERT:
            return
        if since(self.blink_at, now) >= ALERT_BLINK_MS:
            self.blink_on = not self.blink_on
            self.blink_at = now
            self.screen.show_big("DONE" if self.blink_on else "", scale=3)
        if self.alert_tap is not None and since(self.alert_tap, now) >= ms(self.cfg["multi_click_time"]):
            # Single tap: dismiss and clear the timer
            self.sound.stop()
            self.timer.clear()
            self.close()

    def update_jiggle(self, now):
        if self.jiggle_on and since(self.jiggle_at, now) >= self.jiggle_wait:
            self.actions.jiggle(self.cfg["jiggle_max_pixels"])
            self.schedule_jiggle(now)

    def schedule_jiggle(self, now):
        self.jiggle_at = now
        self.jiggle_wait = random.randint(ms(self.cfg["jiggle_min_interval"]), ms(self.cfg["jiggle_max_interval"]))

    def update_indicators(self, now):
        # Only rebuild the timer text when something it shows has changed
        tmr = self.timer
        show = self.mode == NORMAL or self.mode == TIMER
        seconds = int(tmr.remaining()) if show else -1
        # The stopwatch uses the top bar when no countdown is set
        sw = self.stopwatch
        sw_secs = sw.elapsed_ms(now) // 1000 if (self.mode == NORMAL and sw.active) else -1
        shown = self.shown_timer
        if (shown is None or shown[0] != show or shown[1] != seconds
                or shown[2] != tmr.state or shown[3] != tmr.duration or shown[4] != sw_secs):
            self.shown_timer = (show, seconds, tmr.state, tmr.duration, sw_secs)
            text = tmr.display_text() if show else ""
            if not text and sw_secs >= 0:
                text = stopwatch.bar_text(sw_secs)
            self.screen.set_timer(text)
        # One blink clock for the jiggle J and the CAPS box, so they flash together
        half_period = max(1, int(1000 / max(0.1, self.cfg["display_jiggle_blink_rate"])))
        self.blink_phase = (now // half_period) % 2 == 1
        blink = self.blink_phase and self.jiggle_on and self.mode != ERRORS and self.mode != LOCKED
        self.show_caps_box()
        if blink != self.shown_blink:
            self.shown_blink = blink
            self.screen.set_jiggle("J" if blink else "")

    def on_key(self, event):
        key = event.key_number
        if event.released:
            if self.confirming is not None and self.confirming[0] == key:
                self.cancel_confirm()       # let go before the bar filled: nothing sent
            self.repeating.pop(key, None)
            action = self.held.pop(key, None)
            if action:
                self.actions.release(action)
                self.led.value = self.jiggle_on
            return
        now = clock.now()
        if self.wake(now):
            return                      # screen was off: this press only wakes it
        if self.mode in (ALERT, ERRORS, CONFIRM) or self.locked:
            return
        self.lights.react(now)
        if self.cfg["sound_keys"] and not self.muted:
            self.sound.click()
        if self.mode == TIMER:
            self.timer.handle_key(key)
            self.last_input = now
            self.draw_timer()
            return
        if self.mode == STOPWATCH:
            self.stopwatch.handle_key(key)
            self.last_input = now
            self.draw_stopwatch()
            return
        if self.mode == LAYER_KEYS:
            index = self.page * PAGE_SIZE + key
            self.last_input = now
            if index < len(self.km.REGULAR_LAYERS):
                self.set_layer(self.km.REGULAR_LAYERS[index])
            return
        layer = self.current
        action = layer.keys[key] if key < len(layer.keys) else None
        if action and layer.confirm[key]:
            self.start_confirm(key, action, now)
        elif action:
            self.led.value = True
            self.held[key] = action
            self.actions.press(action)
            self.last_activity = clock.now()
            if layer.repeat[key]:
                self.repeating[key] = clock.add(clock.now(), ms(self.cfg["repeat_delay"]))
