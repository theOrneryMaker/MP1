# /lib/macropad/stopwatch.py
# Count-up stopwatch plus the key layout used by the STOPWATCH screen.
# Keeps running in the background when you leave the screen (shown in the top bar).

from macropad import clock

STOPPED, RUNNING, PAUSED = 0, 1, 2

# Keys 4-7 (bottom row), matching the timer screen: 4 reset, 5 start/resume, 6 pause
ICONS = ("", "", "", "", "RST", "PLAY", "PAUS", "")


class Stopwatch:
    def __init__(self):
        self.state = STOPPED
        self._total = 0         # ms counted before _start
        self._start = 0         # tick when the current run (or last fold) started

    def elapsed_ms(self, now=None):
        if self.state == RUNNING:
            return self._total + clock.since(self._start, clock.now() if now is None else now)
        return self._total

    def update(self, now):
        """Fold running time into the total now and then, so ticks never wrap mid-run
        (stays exact for runs of any length)."""
        if self.state == RUNNING:
            gap = clock.since(self._start, now)
            if gap >= 60000:
                self._total += gap
                self._start = now

    def play(self):
        if self.state != RUNNING:
            self._start = clock.now()
            self.state = RUNNING

    def pause(self):
        if self.state == RUNNING:
            self._total = self.elapsed_ms()
            self.state = PAUSED

    def toggle(self):
        if self.state == RUNNING:
            self.pause()
        else:
            self.play()

    def reset(self):
        self.state = STOPPED
        self._total = 0

    @property
    def active(self):
        """Running, or paused with time on it."""
        return self.state != STOPPED or self._total > 0

    def handle_key(self, key):
        if key == 4:
            self.reset()
        elif key == 5:
            self.play()
        elif key == 6:
            self.pause()

    def tenths(self, now=None):
        return self.elapsed_ms(now) // 100


def big_text(tenths):
    """Screen text: 12:34.5 under an hour, 1:02:03 after."""
    secs, tenth = divmod(tenths, 10)
    mins, secs = divmod(secs, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return "{}:{:02d}:{:02d}".format(hours, mins, secs)
    return "{:02d}:{:02d}.{}".format(mins, secs, tenth)


def bar_text(seconds):
    """Short top-bar text: SW 12:34, SW 1:02h."""
    mins, secs = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    if hours:
        return "SW {}:{:02d}h".format(hours, mins)
    return "SW {}:{:02d}".format(mins, secs)
