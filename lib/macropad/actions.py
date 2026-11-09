# /lib/macropad/actions.py
# Sends HID output for key actions, sequences, encoder turns, and mouse jiggle.
# Actions are the (kind, value) tuples produced by keymap.py.

import time
import random
from adafruit_hid.keycode import Keycode

CAPS_LOCK_LED = 0x02        # Keyboard.LED_CAPS_LOCK


TEXT_CHUNK = 32         # characters typed between watchdog feeds

# PANIC!: only actions that can't undo themselves when pressed twice
MEDIA_PAUSE = 0xB1      # dedicated Pause (Play/Pause would start playback if nothing was playing)
VOLUME_DOWN = 0xEA
PANIC_VOLUME_STEPS = 50 # Windows steps 2 % per press: 50 reaches 0 from any level (mute would toggle)


def _nothing():
    pass


class Actions:
    def __init__(self, kbd, layout, cc, mouse):
        self.kbd = kbd
        self.layout = layout
        self.cc = cc
        self.mouse = mouse
        self.wait = time.sleep              # the app swaps in a wait that keeps lights/sound running
        self.feed = _nothing                # the app swaps in its watchdog feed

    def press(self, action):
        """Key down. key/combo/click stay held until release()."""
        kind, value = action
        if kind == "key":
            self.kbd.press(value)
        elif kind == "combo":
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
        elif kind == "url":
            self.run('cmd /c start "" "{}"'.format(value))
        elif kind == "app":
            self.run(value)
        elif kind == "delay":
            self.wait(value)
        elif kind == "sequence":
            for step in value:
                self.tap(step)
                self.feed()
                time.sleep(0.1 if step[0] == "media" else 0.01)

    def release(self, action):
        kind, value = action
        if kind == "key":
            self.kbd.release(value)
        elif kind == "combo":
            self.kbd.release(*value)
        elif kind == "click":
            self.mouse.release(value)

    def write(self, text):
        """Type text in short pieces, feeding the watchdog in between: long text can
        take longer to type than the watchdog waits."""
        for i in range(0, len(text), TEXT_CHUNK):
            self.layout.write(text[i:i + TEXT_CHUNK])
            self.feed()

    def tap(self, action):
        self.press(action)
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
        try:
            return bool(self.kbd.led_on(CAPS_LOCK_LED))
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
        dx, dy = random.choice(((pixels, 0), (-pixels, 0), (0, pixels), (0, -pixels)))
        self.mouse.move(x=dx, y=dy)
        self.mouse.move(x=-dx, y=-dy)
