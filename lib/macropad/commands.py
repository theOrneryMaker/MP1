# /lib/macropad/commands.py
# What gestures and menu selections do: device functions (gestures.py), Settings menu
# items, layer switching, jiggle and the secret layer. Part of the App class (see app.py).

from macropad import timer, stopwatch, clock
from macropad.gestures import MEDIA
from macropad.menus import (ConfigMenu, CONFIG_ITEMS, GESTURE_ITEMS, SOUND_ITEMS,
                            LIGHT_ITEMS, SCREEN_ITEMS)
from macropad.modes import *    # noqa: F401,F403


class Commands:
    def run_gesture(self, name, now):
        """Run a device function chosen in GESTURES (see gestures.py)."""
        if self.locked and name != "lock":
            return                          # locked: only the unlock gesture works
        if name == "lock":
            if self.locked:
                self.locked = False
                self.close()                # back to the layer (flashes its name)
            else:
                self.lock_keys()
        elif name == "jiggle":
            self.toggle_jiggle(now)
        elif name == "secret":
            self.toggle_secret(1)
        elif name == "secret2":
            self.toggle_secret(2)
        elif name == "home_layer":
            self.set_layer(self.km.DEFAULT_LAYER)
        elif name == "layer_keys":
            self.open_layer_keys()
        elif name == "settings":
            self.open_settings()
        elif name == "timer":
            self.open_timer()
        elif name == "timer_toggle":
            if self.timer.state == timer.RUNNING:
                self.timer.pause()
                self.notice("Paused")
            elif self.timer.state == timer.PAUSED or self.timer.duration > 0:
                self.timer.play()
                self.notice("Timer on")
            else:
                self.notice("No timer")
        elif name == "stopwatch":
            self.open_stopwatch()
        elif name == "sw_toggle":
            self.stopwatch.toggle()
            self.notice("SW on" if self.stopwatch.state == stopwatch.RUNNING else "SW paused")
        elif name in MEDIA:
            self.actions.press(("media", MEDIA[name]))
        elif name == "panic":
            self.held.clear()
            self.repeating.clear()
            self.actions.panic()
            self.notice("Panic!")
        elif name == "lights":
            if self.lights.pixels is None:
                self.notice("No LEDs")
            else:
                self.lights_off = not self.lights_off
                self.notice("Lights off" if self.lights_off else "Lights on")
        elif name == "sound":
            if not self.sound.present:
                self.notice("No buzzer")
            else:
                self.muted = not self.muted
                self.notice("Sound off" if self.muted else "Sound on")
        elif name == "show_layer":
            self.close()

    def notice(self, text):
        """Flash a short message, then show the current layer."""
        self.screen.flash(text, self.cfg["display_layer_flash_delay"])
        self.show_layer()

    def set_layer(self, new, flash=True):
        """Switch to a regular layer."""
        self.layer = self.prev_layer = new
        self.show_layer(flash=flash)
        self.last_activity = clock.now()

    def select(self):
        index = self.menu.selection
        if self.mode == LAYERS:
            self.set_layer(self.km.REGULAR_LAYERS[index], flash=False)
            return
        target = self.settings_menu[index][1]
        if target == "timer":
            self.open_timer()
        elif target == "stopwatch":
            self.open_stopwatch()
        elif target == "config":
            self.open_menu(CONFIG, ConfigMenu(self.cfg, CONFIG_ITEMS))
        elif target == "gestures":
            self.open_menu(CONFIG, ConfigMenu(self.cfg, GESTURE_ITEMS))
        elif target == "lights":
            self.open_menu(CONFIG, ConfigMenu(self.cfg, LIGHT_ITEMS, live=True, on_saved=self.hardware_changed))
        elif target == "screen":
            self.open_menu(CONFIG, ConfigMenu(self.cfg, SCREEN_ITEMS))
        elif target == "sound":
            self.open_menu(CONFIG, ConfigMenu(self.cfg, SOUND_ITEMS, live=True, on_saved=self.hardware_changed))
        else:
            if target and self.cfg.get(target):
                self.actions.press(("url", self.cfg[target]))
            self.close()

    def hardware_changed(self, keys):
        """LED COUNT or BUZZER was saved: restart that add-on now (no reboot needed)."""
        for key, part in (("led_count", self.lights), ("buzzer", self.sound)):
            if key in keys:
                part.restart()
                if part.error:
                    self.errors = (self.errors + [part.error])[-MAX_ERRORS:]
                    self.error_index = len(self.errors) - 1
                    self.menu = None
                    self.show_errors()

    def toggle_jiggle(self, now):
        self.jiggle_on = not self.jiggle_on
        self.led.value = self.jiggle_on
        self.schedule_jiggle(now)
        self.screen.flash("Jiggle", self.cfg["jiggle_display_flash_duration"])
        self.close()

    def toggle_secret(self, which=1):
        """Open Secret 1 or 2, or go back if it's already showing. A missing one falls
        back to the other secret layer; with no secret layers it does nothing."""
        secrets = self.km.SECRET_LAYERS
        target = secrets[which - 1]
        if target is None:
            target = secrets[2 - which]
        if target is None:
            return
        if self.layer == target:
            self.layer = self.prev_layer
        else:
            if self.layer not in secrets:       # hopping secret -> secret keeps the way back
                self.prev_layer = self.layer
            self.layer = target
        self.close()
