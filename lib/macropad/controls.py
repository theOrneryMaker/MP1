# /lib/macropad/controls.py
# Encoder turns and encoder-button presses: debouncing, clicks, double/triple click,
# hold + turn and click-then-hold + turn. Part of the App class (see app.py).

from macropad import timer
from macropad.clock import since, ms
from macropad.menus import EXIT, RESET
from macropad.modes import *    # noqa: F401,F403

VOLUME_PREVIEW = ((2000, 0.08),)    # short beep while adjusting BEEP VOL


class Controls:
    def read_encoder(self, now):
        pos = self.encoder.position
        delta = pos - self.enc_pos
        if not delta:
            return
        self.enc_pos = pos
        if since(self.button_changed, now) < ms(self.cfg["encoder_press_guard"]):
            # Pressing or releasing the knob rocks the shaft: not a real turn
            if self.cfg["debug_gestures"]:
                print("encoder: position {} ignored (button just pressed/released)".format(pos))
            return
        if self.wake(now):
            return
        if self.cfg["encoder_reverse"]:
            delta = -delta
        step = 1 if delta > 0 else -1     # +1 = clockwise
        held = self.button_down
        if self.cfg["debug_gestures"]:
            print("encoder: position {} ({:+d}){}".format(pos, delta, " held" if held else ""))
        if held:
            self.spin += abs(delta)
            self.spin_net += delta
            # Direction = the way it turned overall, so a click of jitter as the knob
            # stops can't flip it
            self.spin_dir = (1 if self.spin_net > 0 else -1) if self.spin_net else step

        gap = since(self.last_turn, now)
        self.last_turn = now
        self.last_input = now

        if self.mode == ALERT:
            return
        if self.mode == ERRORS:
            self.error_index = (self.error_index + step) % len(self.errors)
            self.show_errors()
        elif self.mode == TIMER:
            self.timer.adjust(step * timer.ENCODER_STEP)
        elif self.mode == STOPWATCH or self.mode == LOCKED or self.mode == CONFIRM:
            pass
        elif self.mode == LAYER_KEYS:
            pages = (len(self.km.REGULAR_LAYERS) + PAGE_SIZE - 1) // PAGE_SIZE
            if pages > 1:
                self.page = (self.page + step) % pages
                self.draw_layer_keys()
        elif self.mode == CONFIG and self.menu.editing:
            self.menu.adjust(step)
            if self.menu.current_key() == "buzzer_volume":
                self.sound.play(VOLUME_PREVIEW)
            self.draw_menu()
        elif self.mode != NORMAL:
            self.menu.navigate(-step)
            self.roll_menu(-step, now)
        elif not held:
            cfg = self.cfg
            if gap < ms(cfg["encoder_speed_fast"]):
                speed = cfg["encoder_multiplier_fast"]
            elif gap < ms(cfg["encoder_speed_medium"]):
                speed = cfg["encoder_multiplier_medium"]
            else:
                speed = 1
            self.actions.turn(self.current, delta, speed)
            self.last_activity = now

    def read_button(self, now):
        raw = not self.button.value
        if raw != self.button_raw:                     # contact changed: restart the settle timer
            self.button_raw = raw
            self.button_changed = now
            if self.button_down:
                self.glitches += 1
            return
        if raw == self.button_down:
            return
        settle = ms(self.cfg["button_debounce"])
        if not raw and self.spin:
            settle = max(settle, HOLD_RELEASE_MS)       # ride out flickers while turning
        if since(self.button_changed, now) < settle:
            return
        self.button_down = raw
        if raw:
            self.press_start = now
            self.spin = 0
            self.spin_net = 0
            self.spin_dir = 0
            self.glitches = 0
            self.ignore_release = self.wake(now)
        else:
            self.last_input = now
            self.last_wake = now
            if self.ignore_release:     # this press only woke the screen
                self.ignore_release = False
                if self.cfg["debug_gestures"]:
                    print("button: press only woke the screen")
                return
            duration = since(self.press_start, now)
            if self.cfg["debug_gestures"]:
                self.debug_press(duration)
            self.on_release(duration, now)

    def debug_press(self, duration):
        """debug_gestures: one line per press on the serial console."""
        cfg = self.cfg
        hold_turn = (duration > ms(cfg["hold_gesture_min_duration"])
                     and self.spin >= cfg["hold_turn_threshold"])
        if hold_turn:
            after = "click_" if self.clicks else ""
            key = "gesture_{}hold_{}".format(after, "cw" if self.spin_dir > 0 else "ccw")
            result = "{} = {}".format(key, cfg[key])
        elif self.spin:
            result = "not a hold+turn (needs {} clicks and {} s)".format(
                cfg["hold_turn_threshold"], cfg["hold_gesture_min_duration"])
        else:
            result = "press"
        print("button: held {} ms, turned {} clicks (net {:+d}), contact flickers {}, "
              "mode {}, clicks before {} -> {}".format(
                  duration, self.spin, self.spin_net, self.glitches, self.mode, self.clicks, result))

    def on_release(self, duration, now):
        """duration = how long the button was held, in ms."""
        mode = self.mode
        cfg = self.cfg

        if mode == ERRORS:
            self.close()
            return

        if mode == ALERT:
            if self.alert_tap is not None and since(self.alert_tap, now) < ms(cfg["multi_click_time"]):
                self.sound.stop()
                self.open_timer()        # double tap: back to the timer
            else:
                self.alert_tap = now        # wait to see if a second tap follows
            return

        if mode == TIMER or mode == LAYER_KEYS or mode == STOPWATCH:
            self.close()
            return

        if mode == CONFIRM:                 # knob pressed while holding a confirm key: cancel
            self.clicks = 0
            self.cancel_confirm()
            return

        if mode == CONFIG:
            result = self.menu.press()
            if self.mode != CONFIG:         # an add-on failed to start: error screen is showing
                return
            if result == EXIT:
                self.close()
                return
            if result == RESET:
                self.screen.flash("Reset", 0.8)
            if self.menu.save_failed:       # applied, but lost at restart (USB drive is visible)
                self.screen.flash("Not saved", 1.0)
            self.draw_menu()
            return

        if self.locked:
            self.locked_release(duration, now)
            return

        short = duration < ms(cfg["medium_press_duration"])
        if (mode == LAYERS or mode == SETTINGS) and short:
            self.clicks = 0
            self.select()
        elif duration > ms(cfg["hold_gesture_min_duration"]) and self.spin >= cfg["hold_turn_threshold"]:
            # Hold + turn. Started within CLICK TIME of a click = click-hold-turn.
            after_click = self.clicks > 0
            self.clicks = 0
            if after_click:
                key = "gesture_click_hold_cw" if self.spin_dir > 0 else "gesture_click_hold_ccw"
            else:
                key = "gesture_hold_cw" if self.spin_dir > 0 else "gesture_hold_ccw"
            self.run_gesture(cfg[key], now)
        elif duration >= ms(cfg["long_press_duration"]):
            self.clicks = 0
            self.open_settings()
        elif not short:
            self.clicks = 0
            self.close()                    # exit menu, or flash the layer name
        else:
            self.clicks += 1                # a click: wait to see if more follow
            self.click_at = now
            if not self.more_clicks_possible():
                self.finish_clicks(now)

    def locked_release(self, duration, now):
        """LOCK KEYS is on: only the gesture set to LOCK KEYS unlocks (a long press does, if
        no gesture is set to it, so the macropad can't get stuck locked)."""
        cfg = self.cfg
        if duration > ms(cfg["hold_gesture_min_duration"]) and self.spin >= cfg["hold_turn_threshold"]:
            after_click = self.clicks > 0
            self.clicks = 0
            if after_click:
                key = "gesture_click_hold_cw" if self.spin_dir > 0 else "gesture_click_hold_ccw"
            else:
                key = "gesture_hold_cw" if self.spin_dir > 0 else "gesture_hold_ccw"
            if cfg[key] == "lock":
                self.run_gesture("lock", now)
        elif duration < ms(cfg["medium_press_duration"]):
            self.clicks += 1                # double / triple click may be the unlock
            self.click_at = now
            if not self.more_clicks_possible():
                self.finish_clicks(now)
        else:
            self.clicks = 0
            if duration >= ms(cfg["long_press_duration"]) and not self.unlock_gesture_set():
                self.run_gesture("lock", now)

    def more_clicks_possible(self):
        """Is it worth waiting for another click (or a click-hold-turn)?
        No point if nothing is assigned to what could follow."""
        cfg = self.cfg
        if self.clicks >= 3:
            return False
        if cfg["gesture_triple"] != "none":
            return True
        return self.clicks == 1 and (cfg["gesture_double"] != "none"
                                     or cfg["gesture_click_hold_cw"] != "none"
                                     or cfg["gesture_click_hold_ccw"] != "none")

    def check_clicks(self, now):
        if (self.clicks and not self.button_down and (self.mode == NORMAL or self.mode == LOCKED)
                and since(self.click_at, now) >= ms(self.cfg["multi_click_time"])):
            self.finish_clicks(now)

    def finish_clicks(self, now):
        count, self.clicks = self.clicks, 0
        if count == 1:
            if not self.locked:
                self.open_layers()
        elif count == 2:
            self.run_gesture(self.cfg["gesture_double"], now)
        else:
            self.run_gesture(self.cfg["gesture_triple"], now)
