# /lib/macropad/timer.py
# Countdown timer plus the key layout used by the TIMER screen.

from macropad import clock

IDLE, RUNNING, PAUSED = 0, 1, 2

# Keys 0-3: presets.  4: clear  5: play (start/resume)  6: pause at current time  7: unused
PRESETS = (60 * 60, 30 * 60, 15 * 60, 5 * 60)
ICONS = ("1HR", "30M", "15M", "5M", "CLR", "PLAY", "PAUS", "---")
ENCODER_STEP = 30  # seconds per encoder click while idle


class Timer:
    def __init__(self):
        self.state = IDLE
        self.duration = 0   # seconds (what the screen shows when idle)
        self._start = 0     # tick when the current run started (RUNNING)
        self._run_ms = 0    # ms to count down from that start
        self._left_ms = 0   # ms left when paused (PAUSED)

    def remaining_ms(self):
        if self.state == RUNNING:
            return max(0, self._run_ms - clock.since(self._start, clock.now()))
        if self.state == PAUSED:
            return self._left_ms
        return self.duration * 1000

    def remaining(self):
        """Seconds left (float)."""
        return self.remaining_ms() / 1000

    def set(self, seconds):
        self.duration = max(0, seconds)
        self.state = IDLE

    def adjust(self, seconds):
        """Change the duration (idle only). Returns True if it changed."""
        if self.state != IDLE:
            return False
        self.duration = max(0, self.duration + seconds)
        return True

    def play(self):
        """Start (from the set time) or resume (from where it was paused)."""
        if self.state == PAUSED:
            self._start, self._run_ms = clock.now(), self._left_ms
            self.state = RUNNING
        elif self.state == IDLE and self.duration > 0:
            self._start, self._run_ms = clock.now(), self.duration * 1000
            self.state = RUNNING

    def pause(self):
        """Freeze the countdown at its current time (PLAY resumes)."""
        if self.state == RUNNING:
            self._left_ms = self.remaining_ms()
            self.state = PAUSED

    def clear(self):
        self.state = IDLE
        self.duration = 0

    def poll(self):
        """Returns True exactly once, when a running countdown reaches zero."""
        if self.state == RUNNING and clock.since(self._start, clock.now()) >= self._run_ms:
            self.state = IDLE
            return True
        return False

    def handle_key(self, key):
        if key < len(PRESETS):
            self.set(PRESETS[key])
        elif key == 4:
            self.clear()
        elif key == 5:
            self.play()
        elif key == 6:
            self.pause()

    def status_icon(self):
        return ("+/-", "RUN", "PAUS")[self.state]

    def display_text(self):
        """Short countdown for the top bar, or "" when no timer is set."""
        if self.state == IDLE and not self.duration:
            return ""
        mins, secs = divmod(int(self.remaining()), 60)
        if mins >= 100:
            return "{}m".format(mins)
        if mins >= 10:
            return "{:02d}:{:02d}".format(mins, secs)
        return "{}:{:02d}".format(mins, secs)
