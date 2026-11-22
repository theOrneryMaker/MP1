# /lib/mp1/jsfile.py
# The keymap and settings files are plain JSON (keymap.json, settings.json, default.json).
# A file is parsed straight from the file; one with text around the JSON (a byte-order mark...)
# is read whole and the reader takes the text between the first "{" and the last "}".
# (keymap.json, which can be big, is read one layer at a time by keymap.load_array.)

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
    if path.endswith(".json"):
        # Parse straight from the file: the text is never held in memory, so a big keymap
        # needs no more RAM to load than its layers do once loaded.
        with open(path, "rb") as f:
            try:
                return json.load(f)
            except Exception:   # text around the {...}, a byte-order mark, anything odd:
                pass            # the old way below (it raises the real error, if any)
    with open(path, "r") as f:
        text = f.read()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no {...} in " + path)
    if start or text[end + 1:].strip():
        text = text[start:end + 1]          # only copy when there's something to cut off
    return json.loads(text)

