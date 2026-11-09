# /lib/macropad/guard.py
# Hardware watchdog: if the main loop ever stops running (a freeze), the RP2040 restarts
# itself after TIMEOUT seconds. The app feeds it every loop pass, during pauses and while
# typing long text, so normal use never trips it. Ctrl+C in the serial console stops it.
# ("watchdog": false in settings.js turns it off.)

TIMEOUT = 8.0       # seconds; the RP2040's hardware maximum is about 8.3


class Guard:
    def __init__(self, enabled):
        self.dog = None
        self.restarted = False      # True if the last restart was the watchdog's
        try:
            import microcontroller
            self.restarted = microcontroller.cpu.reset_reason == microcontroller.ResetReason.WATCHDOG
        except (ImportError, AttributeError):
            pass
        if not enabled:
            print("Watchdog: off (\"watchdog\": false in settings.js)")
            return
        try:
            from microcontroller import watchdog
            from watchdog import WatchDogMode
            watchdog.timeout = TIMEOUT
            watchdog.mode = WatchDogMode.RESET      # starts it
            watchdog.feed()
            self.dog = watchdog
            print("Watchdog: on, restarts the macropad if it freezes for {:.0f} s".format(TIMEOUT))
        except Exception as e:                      # not available on this board / build
            print("Watchdog: not available:", e)

    def feed(self):
        if self.dog is not None:
            self.dog.feed()

    def stop(self):
        """Turn it off (e.g. Ctrl+C to the serial console, so it can't reset the REPL)."""
        if self.dog is not None:
            try:
                self.dog.deinit()
            except Exception:
                pass
            self.dog = None
