# /lib/macropad/lights.py
# Optional RGB LED strip (NeoPixels). With "led_count": 0 in settings.js every call
# does nothing, so units without the add-on work unchanged.
#
# Frames are computed at most ~60 times a second and only sent to the LEDs when they
# change, so animations never block the main loop. All timing uses whole milliseconds
# from macropad.clock (animation phases are worked out with integer maths first), so
# effects stay smooth however long the macropad has been powered.
#
# Smoothness: scenes work in fractions (0.0-255.0), brightness is applied here in one
# step (the strip itself runs at full brightness, so nothing is rounded twice), and the
# remaining fraction is carried to the next frame ("temporal dithering"): a level of
# 20.25 shows as 20, 20, 20, 21, ... so slow fades glide instead of stepping, even at
# low brightness where a colour only has a few dozen levels.

import math
import random
from macropad import clock

FRAME_MS = 16           # ~60 frames a second at most
OFF = (0, 0, 0)
DITHER_MIN = 1.5        # below this level a channel isn't dithered (0 <-> 1 would shimmer)

COLORS = {
    "RED": (255, 0, 0), "VERMILION": (255, 80, 0), "ORANGE": (255, 140, 0), "AMBER": (255, 200, 0),
    "YELLOW": (255, 255, 0), "LIME": (180, 255, 0), "GREEN": (0, 255, 0), "MINT": (0, 255, 100),
    "CYAN": (0, 255, 255), "SKY": (0, 180, 255), "BLUE": (0, 0, 255), "INDIGO": (100, 0, 255),
    "PURPLE": (180, 0, 255), "MAGENTA": (255, 0, 255), "PINK": (255, 100, 180), "ROSE": (255, 100, 100),
    "WHITE": (255, 255, 255), "WARM_WHITE": (255, 180, 100),
}
COLOR_NAMES = ("RED", "VERMILION", "ORANGE", "AMBER", "YELLOW", "LIME", "GREEN", "MINT", "CYAN",
               "SKY", "BLUE", "INDIGO", "PURPLE", "MAGENTA", "PINK", "ROSE", "WHITE", "WARM_WHITE")

# Scenes, for the LIGHTS settings and for a layer's own lights (which take over on that layer).
SCENES = ("off", "static", "breathing", "reactive", "pulse", "twinkle", "lightning", "strobe",
          "rainbow", "cycle")
SCENE_COLORS = {"off": 0, "static": 1, "breathing": 2, "reactive": 2, "pulse": 1, "twinkle": 1,
                "lightning": 1, "strobe": 1, "rainbow": 0, "cycle": 0}   # colours each scene uses
CYCLE_PALETTE = ((255, 0, 0), (255, 127, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255),
                 (0, 0, 255), (255, 0, 255))

# Scene timings at SPEED 5 (milliseconds); SPEED 1 is 3x slower, SPEED 10 4x faster.
PULSE_MS = 3000         # dark -> bright -> dark
BREATHE_MS = 4000       # one colour in and out (then the other colour)
REACT_MS = 600          # key-press flash fading back
TWINKLE_MS = 90         # a new LED starts changing this often
TWINKLE_FADE_MS = 700   # how long one LED takes to reach its new level
STRIKE_GAP_MS = (1500, 6000)
STRIKE_FADE_MS = 400
STROBE_MS = 250         # one flash (on for 40 ms of it)
RAINBOW_MS = 6000       # once round the colour wheel
CYCLE_MS = 12000        # through all the CYCLE_PALETTE colours


def color(value):
    """A palette name or "#RRGGBB" -> (r, g, b), or None if invalid."""
    if not isinstance(value, str):
        return None
    if len(value) == 7 and value[0] == "#":
        try:
            n = int(value[1:], 16)
            return ((n >> 16) & 255, (n >> 8) & 255, n & 255)
        except ValueError:
            return None
    return COLORS.get(value)


def rate(speed_setting):
    """SPEED 1-10 -> how many times faster than SPEED 5 (1 -> 0.33, 5 -> 1.0, 10 -> 4.0)."""
    return 2 ** ((max(1, min(10, speed_setting)) - 5) / 2.5)


def _scale(c, k):
    return (c[0] * k, c[1] * k, c[2] * k)


def _blend(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _ease(k):
    """Perceived brightness is far from linear: squaring makes fades look even."""
    return k * k


def _wheel(pos):
    """0-255 -> rainbow colour."""
    pos %= 255
    if pos < 85:
        return (255 - pos * 3, pos * 3, 0)
    if pos < 170:
        pos -= 85
        return (0, 255 - pos * 3, pos * 3)
    pos -= 170
    return (pos * 3, 0, 255 - pos * 3)


def _phase(now, period_ms):
    """Position 0.0-1.0 within a repeating period (integer maths first, so no drift)."""
    period_ms = max(1, int(period_ms))
    return (now % period_ms) / period_ms


class Lights:
    def __init__(self, cfg, pin):
        self.cfg = cfg
        self.pin = pin
        self.pixels = None
        self.count = 0
        self.error = None
        self.frame_at = None        # tick of the last frame
        self.react_at = None        # tick of the last key press (reactive scene)
        self.strike_at = None       # tick of the next lightning strike
        self.strike_flicks = 1
        self.twinkle_at = None
        self.levels = []            # twinkle: each LED's level, start level and target
        self.restart()

    def restart(self):
        """(Re)start the strip with the current led_count. Never raises: a failure is
        kept in self.error and the strip is treated as not fitted."""
        if self.pixels is not None:
            try:
                self.pixels.fill(OFF)
                self.pixels.show()
                self.pixels.deinit()
            except Exception:
                pass
        self.pixels = None
        self.count = 0
        self.error = None
        self.last_frame = None
        self.carry = []             # dithering: the fraction each channel still owes
        self.reported = False
        count = self.cfg["led_count"]
        if count <= 0:
            print("LED strip: off (led_count is 0)")
            return
        try:
            import neopixel     # only needed when a strip is fitted
            # Full brightness in the strip: brightness is applied (once) in update()
            self.pixels = neopixel.NeoPixel(self.pin, count, brightness=1.0,
                                            auto_write=False, pixel_order=neopixel.GRB)
            self.pixels.fill(OFF)
            self.pixels.show()
            self.count = count
            self.carry = [0.0] * (count * 3)
            self.levels = [[0.6, 0.6, 0.6, 0] for _ in range(count)]
            print("LED strip: started, {} LEDs on {}, brightness {}, scene {}".format(
                count, self.pin, self.cfg["led_brightness"], self.cfg["led_scene"]))
        except Exception as e:
            self.pixels = None
            self.error = "LED strip failed ({}). Check led_count and lib/neopixel.mpy".format(e)
            print(self.error)

    def react(self, now):
        """Key pressed (used by the reactive scene)."""
        self.react_at = now

    def update(self, now, scene, c1, c2):
        if self.pixels is None:
            return
        if self.frame_at is not None and clock.since(self.frame_at, now) < FRAME_MS:
            return
        self.frame_at = now
        frame = self.frame(now, scene, c1 or OFF, c2 or OFF, rate(self.cfg["led_speed"]))
        out = self.output(frame, max(0.0, min(1.0, self.cfg["led_brightness"])))
        if out != self.last_frame:
            self.last_frame = out
            if isinstance(out, list):
                for i, c in enumerate(out):
                    self.pixels[i] = c
            else:
                self.pixels.fill(out)
            self.pixels.show()
            if not self.reported:
                self.reported = True
                print("LED strip: first colour sent", out, "scene", scene)

    def output(self, frame, brightness):
        """Fractional colours -> whole numbers for the strip: brightness applied once,
        and each channel's leftover fraction carried into the next frame."""
        carry = self.carry
        if isinstance(frame, list):
            out = []
            for i, c in enumerate(frame[:self.count]):
                out.append(self._dither(c, brightness, carry, i * 3))
            return out
        return self._dither(frame, brightness, carry, 0)

    @staticmethod
    def _dither(c, brightness, carry, at):
        rgb = [0, 0, 0]
        for ch in range(3):
            v = c[ch] * brightness
            if v < DITHER_MIN:              # very dim: plain rounding (no 0/1 shimmer)
                carry[at + ch] = 0.0
                n = int(v + 0.5)
            else:
                v += carry[at + ch]
                n = int(v)
                carry[at + ch] = v - n
            rgb[ch] = 255 if n > 255 else n
        return (rgb[0], rgb[1], rgb[2])

    def frame(self, now, scene, c1, c2, speed):
        """Colour for this moment (now = clock ticks in ms): one (r, g, b) for the whole
        strip, or a list per LED; values may be fractions. speed = rate(): 1.0 at SPEED 5."""
        if scene == "static":
            return c1
        if scene == "alert":                                   # timer finished: red strobe
            return (255, 0, 0) if now % 200 < 100 else OFF
        if scene == "breathing":                               # c1 fades in/out, then c2
            phase = _phase(now, 2 * BREATHE_MS / speed)
            k = (1 - math.cos(2 * math.pi * ((phase * 2) % 1))) / 2
            return _scale(c1 if phase < 0.5 else c2, _ease(k))
        if scene == "reactive":                                # c2 flash on key press, fades to c1
            if self.react_at is None:
                return c1
            fade = REACT_MS / speed
            t = clock.since(self.react_at, now)
            if t < fade:
                return _blend(c2, c1, 1 - (1 - t / fade) ** 2)
            return c1
        if scene == "pulse":                                   # smooth swell and fade
            k = (1 - math.cos(2 * math.pi * _phase(now, PULSE_MS / speed))) / 2
            return _scale(c1, _ease(k))
        if scene == "twinkle":
            return self._twinkle(now, c1, speed)
        if scene == "lightning":
            if self.strike_at is None:
                self.strike_at = now
            t = clock.diff(now, self.strike_at)                # negative while waiting for the strike
            if t < 0:
                return OFF
            flicker = self.strike_flicks * 80
            if t < flicker:
                return c1 if t % 80 < 50 else OFF
            fade = STRIKE_FADE_MS / speed
            if t < flicker + fade:
                return _scale(c1, _ease(1 - (t - flicker) / fade))
            lo, hi = STRIKE_GAP_MS
            self.strike_at = clock.add(now, random.randint(int(lo / speed), int(hi / speed)))
            self.strike_flicks = random.randint(1, 4)
            return OFF
        if scene == "strobe":
            return c1 if now % max(100, int(STROBE_MS / speed)) < 40 else OFF
        if scene == "rainbow":
            base = int(_phase(now, RAINBOW_MS / speed) * 255)
            return [_wheel(base + i * 256 // max(1, self.count)) for i in range(self.count)]
        if scene == "cycle":
            pos = _phase(now, CYCLE_MS / speed) * len(CYCLE_PALETTE)
            i = int(pos)
            return _blend(CYCLE_PALETTE[i % len(CYCLE_PALETTE)], CYCLE_PALETTE[(i + 1) % len(CYCLE_PALETTE)], pos - i)
        return OFF                                             # "off" or unknown

    def _twinkle(self, now, c1, speed):
        """Each LED drifts on its own between dim and bright; a new one starts every
        TWINKLE_MS. levels[i] = [level, from, to, started at]."""
        levels = self.levels
        if len(levels) != self.count:
            self.levels = levels = [[0.6, 0.6, 0.6, now] for _ in range(self.count)]
        if not levels:
            return c1
        if self.twinkle_at is None or clock.since(self.twinkle_at, now) >= TWINKLE_MS / speed:
            self.twinkle_at = now
            led = levels[random.randrange(len(levels))]
            led[1], led[2], led[3] = led[0], 0.15 + random.random() * 0.85, now
        fade = TWINKLE_FADE_MS / speed
        out = []
        for led in levels:
            t = clock.since(led[3], now) / fade
            if t >= 1:
                led[0] = led[2]
            else:
                k = (1 - math.cos(math.pi * t)) / 2           # ease in and out
                led[0] = led[1] + (led[2] - led[1]) * k
            out.append(_scale(c1, _ease(led[0])))
        return out

    def off(self):
        if self.pixels is not None:
            self.pixels.fill(OFF)
            self.pixels.show()
            self.last_frame = OFF
