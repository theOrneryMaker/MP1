# /lib/macropad/sound.py
# Optional buzzer. "buzzer" in settings.js: "none", "passive" (tones via PWM) or
# "active" (on/off only; patterns still differ by rhythm).
#
# Patterns play in the background: play() starts one and update() (called every loop)
# moves to the next note when it's time, so sounds never freeze the macropad.

import time
from macropad import clock

# (frequency Hz, seconds); frequency 0 = silence
STARTUP = ((1500, 0.1), (0, 0.08), (1800, 0.1), (0, 0.08), (2100, 0.1), (0, 0.08), (2400, 0.1))
ALARM = ((2000, 0.2), (0, 0.1), (2000, 0.2), (0, 0.1), (2000, 0.2), (0, 0.8))      # repeats until dismissed
LAYER = ((1200, 0.04), (0, 0.03), (1800, 0.06))                                    # two rising notes
CLICK = (3500, 0.012)                                                              # one short high tick


class Sound:
    def __init__(self, cfg, pin):
        self.cfg = cfg
        self.pin = pin
        self.kind = "none"
        self.out = None
        self.error = None
        self.notes = ()
        self.index = 0
        self.note_at = None
        self.note_ms = 0
        self.loop = False
        self.restart()

    def restart(self):
        """(Re)start with the current "buzzer" setting. Never raises: a failure is kept
        in self.error and the buzzer is treated as not fitted."""
        self.notes = ()
        if self.out is not None:
            try:
                self._tone(0)
                self.out.deinit()
            except Exception:
                pass
        self.out = None
        self.error = None
        self.kind = self.cfg["buzzer"]
        try:
            if self.kind == "passive":
                import pwmio
                self.out = pwmio.PWMOut(self.pin, frequency=2000, duty_cycle=0, variable_frequency=True)
            elif self.kind == "active":
                import digitalio
                self.out = digitalio.DigitalInOut(self.pin)
                self.out.switch_to_output(value=self._level(False))
        except Exception as e:
            self.out = None
            self.kind = "none"
            self.error = "Buzzer failed ({}). Check the buzzer setting".format(e)

    @property
    def present(self):
        return self.out is not None

    @property
    def busy(self):
        return bool(self.notes)

    def _level(self, on):
        return on != self.cfg["buzzer_active_low"]

    def _tone(self, freq):
        if self.out is None:
            return
        if self.kind == "passive":
            if freq:
                self.out.frequency = int(freq)
                # 50% duty is the loudest a square wave gets; volume 0-1 scales up to that
                self.out.duty_cycle = int(32767 * max(0.0, min(1.0, self.cfg["buzzer_volume"])))
            else:
                self.out.duty_cycle = 0
        else:
            self.out.value = self._level(freq > 0)

    def play(self, notes, loop=False):
        if self.out is None:
            return
        self.notes = notes
        self.loop = loop
        self.index = -1
        self.note_at = None
        self.update(clock.now())

    def stop(self):
        self.notes = ()
        self._tone(0)

    def update(self, now):
        if not self.notes:
            return
        if self.note_at is not None and clock.since(self.note_at, now) < self.note_ms:
            return
        self.index += 1
        if self.index >= len(self.notes):
            if not self.loop:
                self.stop()
                return
            self.index = 0
        freq, seconds = self.notes[self.index]
        self._tone(freq)
        self.note_at = now
        self.note_ms = clock.ms(seconds)

    def click(self):
        """Key click. Played directly (12 ms) so a long action right after it
        (typing a string) can't stretch it. Skipped while a pattern is playing."""
        if self.out is None or self.notes:
            return
        self._tone(CLICK[0])
        time.sleep(CLICK[1])
        self._tone(0)
