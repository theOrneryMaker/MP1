# ember/sceneplay.py (from FIRMWARE_04)
# Plays a drop-in scene (scenes/*.mp1scene.json). Only loaded while one is showing:
# lights.py lets it go again when a built-in scene takes over.

from ember import clock
from ember.lights import OFF, _blend, _forget, color


def load(name, path):
    """(loop, steps, on_key steps, total ms, on_key total ms) for a drop-in scene, or None.
    scenes.py (the checks) is only loaded for the moment it takes to read the file."""
    try:
        from ember import scenes
        loop, steps, keys = scenes.read(path, color)
    except Exception as e:                  # changed or removed since start-up
        print("Scene {} not played: {}".format(name.upper(), e))
        return None
    finally:
        scenes = None
        _forget("scenes")
    return (loop, steps, keys, sum(s[1] + s[2] for s in steps), sum(s[1] + s[2] for s in keys))


def frame(lights, now, c1, c2, speed):
    """lights.custom = (loop, steps, on_key steps, total ms, on_key total ms)."""
    loop, steps, keys, total, key_total = lights.custom
    count = lights.count
    out = _play(steps, clock.since(lights.custom_at, now) * speed, loop, total, None, c1, c2, count)
    if keys and lights.react_at is not None:        # on_key: played over the scene, then back
        t = clock.since(lights.react_at, now) * speed
        if t < key_total:
            out = _play(keys, t, False, key_total, out, c1, c2, count)
    return out


def _play(steps, t, loop, total, start, c1, c2, count):
    """The color at time t (ms, already scaled by SPEED): each step fades in from the one
    before (a looping scene's first step from its last; the very first from off, or from
    `start`), then holds."""
    if total <= 0 or (not loop and t >= total):
        return _resolve(steps[-1][0], c1, c2, count)
    if loop:
        t %= total
    prev = start if start is not None else (_resolve(steps[-1][0], c1, c2, count) if loop else OFF)
    for value, hold, fade in steps:
        cur = _resolve(value, c1, c2, count)
        if t < fade:
            return _mix(prev, cur, t / fade, count)
        t -= fade
        if t < hold:
            return cur
        t -= hold
        prev = cur
    return prev


def _resolve(value, c1, c2, count):
    if value == 1:
        return c1
    if value == 2:
        return c2
    if isinstance(value, list):             # a color per LED, repeated along the strip
        n = len(value)
        return [_resolve(value[i % n], c1, c2, count) for i in range(count)]
    return value


def _mix(a, b, k, count):
    if isinstance(a, list) or isinstance(b, list):
        a = a if isinstance(a, list) else [a] * count
        b = b if isinstance(b, list) else [b] * count
        return [_blend(a[i], b[i], k) for i in range(count)]
    return _blend(a, b, k)
