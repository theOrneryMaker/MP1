# /lib/macropad/modes.py
# Constants shared by the app modules (app, controls, commands, extras).

SETTINGS_MENU = (
    ("TIMER", "timer"),
    ("STOPWATCH", "stopwatch"),
    ("VARIABLES", "config"),
    ("GESTURES", "gestures"),
    ("SCREEN", "screen"),
    ("LIGHTS", "lights"),           # only when led_count > 0
    ("SOUND", "sound"),             # only when buzzer isn't "none"
    ("CONFIGURATOR", "keymapper_url"),   # long: shrunk to fit
    ("ABOUT", "about_url"),
    ("EXIT", None),
)

NORMAL, LAYERS, SETTINGS, TIMER, CONFIG, ALERT, ERRORS, LAYER_KEYS, STOPWATCH, LOCKED, CONFIRM = range(11)
MENU_MODES = (LAYERS, SETTINGS, CONFIG)
TOP_BAR_MODES = (NORMAL, TIMER, STOPWATCH, LAYER_KEYS, CONFIRM)    # screens that show the CAPS box
CAPS_POLL_MS = 100
HOLD_RELEASE_MS = 80    # while turning a held knob the switch can open for a moment:
                        # a release must last this long to end a hold + turn
AWAKE, DIM, OFF = range(3)          # screen saver levels
PAGE_SIZE = 8                       # LAYER_KEYS: one layer per key
# LOCKED: what the lock page says, for the first gesture set to LOCK KEYS (max 21 characters)
UNLOCK_HINTS = (
    ("gesture_double", "2x CLICK: UNLOCK"),
    ("gesture_triple", "3x CLICK: UNLOCK"),
    ("gesture_hold_cw", "HOLD+TURN CW: UNLOCK"),
    ("gesture_hold_ccw", "HOLD+TURN CCW: UNLOCK"),
    ("gesture_click_hold_cw", "CLICK+HOLD CW: UNLOCK"),
    ("gesture_click_hold_ccw", "CLICK+HOLD CCW:UNLOCK"),
)
NO_UNLOCK_GESTURE = "LONG PRESS: UNLOCK"

# All times below are whole milliseconds from macropad.clock (exact however long the
# macropad has been on). Settings stay in seconds and are converted with ms().
FIXED_TIMEOUTS = {TIMER: 30.0, CONFIG: 30.0, STOPWATCH: 30.0}     # seconds (stopwatch: only when not running)
ALERT_BLINK_MS = 500
SCREEN_CHARS = 21   # characters per line of small text
MESSAGE_LINES = 4
MAX_ERRORS = 10
