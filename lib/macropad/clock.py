# /lib/macropad/clock.py
# Millisecond clock that stays exact no matter how long the macropad is powered.
#
# time.monotonic() returns a float, and CircuitPython floats only have ~22 bits of
# precision: it's accurate to 1 ms for about an hour, ~30 ms after a day and ~250 ms
# after a week. That slowly breaks debounce, double-tap, encoder speed and animations.
#
# supervisor.ticks_ms() is a whole number of milliseconds (no precision loss and no
# memory allocation). It wraps around every 2**29 ms (~6.2 days), so never compare two
# tick values directly; use since() / diff() / add(), which handle the wrap.

try:
    from supervisor import ticks_ms as _ticks_ms
except ImportError:                     # not CircuitPython (e.g. testing on a PC)
    import time

    def _ticks_ms():
        return int(time.monotonic() * 1000) & MASK

PERIOD = 1 << 29
MASK = PERIOD - 1
HALF = PERIOD >> 1


def now():
    """Current time in ms (wraps every ~6.2 days)."""
    return _ticks_ms()


def since(then, now_ms):
    """Milliseconds from `then` to `now_ms` (0 to ~6.2 days, never negative)."""
    return (now_ms - then) & MASK


def diff(a, b):
    """a - b in ms, negative if a is earlier (valid within ~3.1 days)."""
    d = (a - b) & MASK
    return d - PERIOD if d >= HALF else d


def add(t, ms):
    """The tick value `ms` milliseconds after t."""
    return (t + ms) & MASK


def ms(seconds):
    """Seconds (as used in settings.js) to whole milliseconds."""
    return int(seconds * 1000)
