# ember/gestures.py - the pad's own functions: what an encoder click / hold + turn can run, and what a
# key's "tool" action can name. One shared list (NOTES/DECISIONS.md).

FUNCTIONS = (
    ("none", "Nothing"),
    ("home_layer", "Home layer"),
    ("layer_picker", "Layer picker"),
    ("layer_keys", "Layer keys"),       # pick a layer by pressing its key
    ("layer_cards", "Layer cards"),     # one big card a layer (its picture + name): turn, click to pick
    ("tools_menu", "TOOLS menu"),
    ("show_layer", "Show layer"),       # the layer's name, big, for a moment
    ("mute", "Mute"),
    ("play_pause", "Play / pause"),
    ("panic", "PANIC!"),                # pause media, minimize all windows, volume to zero
    ("jiggle", "Mouse jiggle"),         # on / off
    ("secret", "Secret pages"),         # page 1 (again: closed); the encoder turns the pages
    ("secret2", "Secret page 2"),       # straight to page 2
    ("lock", "Lock keys"),
    ("lights", "Lights on / off"),
    ("sound", "Sound on / off"),
    ("spotify", "Spotify"),             # the Spotify screen (nowplay.py); a click goes back
    ("timer", "Timer / stopwatch"),     # the Timer screen (extras.py); hold the encoder to go back
    ("counter", "Counter"),             # the Counter screen (extras.py)
    ("busy", "Busy light"),             # the lights red, BUSY on the top row: on / off
)
SINGLE_CLICK = ("layer_picker", "layer_keys", "layer_cards")   # a single click can only open a layer list (user, 2026-11-20)
NAMES = tuple(f[0] for f in FUNCTIONS)
MEDIA = {"mute": 0xE2, "play_pause": 0xCD}


def label(name):
    for n, l in FUNCTIONS:
        if n == name:
            return l
    return name
