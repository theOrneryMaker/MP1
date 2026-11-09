# /lib/macropad/gestures.py
# Device functions that encoder gestures (double-click, triple-click, hold+turn) can run.
# Chosen globally in Settings -> GESTURES; stored in settings.js as the first value.

FUNCTIONS = (
    ("none", "NONE"),
    ("home_layer", "HOME LAYER"),       # the default layer
    ("layer_keys", "LAYER KEYS"),       # pick a layer by pressing its key
    ("settings", "SETTINGS"),
    ("timer", "TIMER"),                 # open the timer screen
    ("timer_toggle", "START/PAUS"),     # start / pause the timer without opening it
    ("stopwatch", "STOPWATCH"),         # open the stopwatch screen
    ("sw_toggle", "SW ST/PAUS"),        # start / pause the stopwatch without opening it
    ("mute", "MUTE"),                   # media key: mute / unmute the computer
    ("play_pause", "PLAY/PAUSE"),       # media key: play / pause
    ("panic", "PANIC!"),                # pause media, minimize all windows, volume to zero
    ("jiggle", "TOG JIGGLE"),
    ("secret", "TOG SEC 1"),            # Secret 1 (or Secret 2 if there's no Secret 1)
    ("secret2", "TOG SEC 2"),           # Secret 2 (or Secret 1 if there's no Secret 2)
    ("lock", "LOCK KEYS"),              # lock / unlock keys and knob (full-screen lock page)
    ("lights", "TOG LIGHTS"),           # LED strip on/off until restart
    ("sound", "TOG SOUND"),             # key click / layer tone on/off until restart
    ("show_layer", "SHOW LAYER"),       # flash the current layer name
)
NAMES = tuple(f[0] for f in FUNCTIONS)
REMOVED = ("last_layer", "next_layer", "prev_layer")    # older choices: read as "none"

MEDIA = {"mute": 0xE2, "play_pause": 0xCD}     # consumer-control codes (same as keymap MUTE / PLAYPAUSE)
