# /lib/macropad/jsfile.py
# The keymap and settings files can be plain JSON (keymap.json) or the same JSON wrapped
# as a small script (keymap.js):
#
#     // MP1 macropad keymap ...
#     var MP1_KEYMAP = { ...exactly the same JSON... };
#
# The .js form lets the web pages beside it on the drive load it automatically (browsers
# let a page load a script from its folder, but not read a .json file there). Either way
# the reader takes the text between the first "{" and the last "}" and parses it as JSON.

import json
import os


def exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def pick(*paths):
    """The first of these files that exists (or the first name, if none do)."""
    for path in paths:
        if exists(path):
            return path
    return paths[0]


def load(path):
    """Parsed contents. OSError if the file is missing, ValueError if it isn't valid."""
    with open(path, "r") as f:
        text = f.read()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no {...} in " + path)
    return json.loads(text[start:end + 1])


def wrap(name, json_text, note):
    """JSON text as a .js file that defines `var name = {...};`."""
    return "// {}\nvar {} = {};\n".format(note, name, json_text.rstrip())
