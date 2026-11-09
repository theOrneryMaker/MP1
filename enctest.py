# enctest.py - standalone encoder test (nothing else running).
# From the serial console: press Ctrl+C to stop code.py, any key for the >>> prompt, then:
#
#   import enctest          rotaryio test: prints the position and the button state
#   enctest.counted(2)      the same, counting 2 pin steps per click instead of 4
#   enctest.raw()           raw pin test: prints the A / B pin levels on every change
#
# Turn the knob a few clicks each way, first without pressing it, then while holding it
# pressed. Ctrl+C ends a test. Press Ctrl+D afterwards to restart the macropad normally.

import time
import digitalio
import rotaryio
import wiring

_button = digitalio.DigitalInOut(wiring.ENC_SW)
_button.switch_to_input(pull=digitalio.Pull.UP)


def counted(divisor=4):
    enc = rotaryio.IncrementalEncoder(wiring.ENC_A, wiring.ENC_B, divisor=divisor)
    print("rotaryio test (divisor {}): turn each way, with and without the button pressed."
          " Ctrl+C to stop.".format(divisor))
    print("Each click should change the position by exactly 1.")
    last_pos, last_pressed = enc.position, None
    try:
        while True:
            pos, pressed = enc.position, not _button.value
            if pressed != last_pressed:
                print("button", "PRESSED" if pressed else "released")
                last_pressed = pressed
            if pos != last_pos:
                print("  position {:4d}  {}  {}".format(
                    pos, "clockwise        " if pos > last_pos else "counter-clockwise",
                    "(held)" if pressed else ""))
                last_pos = pos
            time.sleep(0.002)
    except KeyboardInterrupt:
        pass
    finally:
        enc.deinit()


def raw():
    """Pin levels straight from the encoder (1 = high/idle, 0 = pulled low)."""
    a = digitalio.DigitalInOut(wiring.ENC_A)
    b = digitalio.DigitalInOut(wiring.ENC_B)
    a.switch_to_input(pull=digitalio.Pull.UP)
    b.switch_to_input(pull=digitalio.Pull.UP)
    print("raw pin test: one click clockwise should step A/B through 4 states, the reverse")
    print("of one click counter-clockwise. Ctrl+C to stop.")
    last = None
    try:
        while True:
            state = (a.value, b.value, not _button.value)
            if state != last:
                print("  A {:d}  B {:d}  {}".format(state[0], state[1], "(held)" if state[2] else ""))
                last = state
    except KeyboardInterrupt:
        pass
    finally:
        a.deinit()
        b.deinit()


counted()
