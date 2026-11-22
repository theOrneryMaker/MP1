# ember/layers.py - the keymap while the pad runs.
# keymap.py checks the Ember files at start-up and packs every layer into one bytes object (blob);
# then it's let go. Only the layer showing is unpacked into a Layer (a few hundred bytes).
#
# Packed layer: flags (1 = encoder accel, 2 = has lights, 4 = jiggle, 8 = keep Num Lock on,
# 16 = has a card picture, 32 + 64 = module view 0-3); 8 keys, each a flags byte (1 = a key is there, 2 = has an action,
# 4 = repeat, 8 = confirm, 16 = has a picture, 32-128 = its own typing speed: 0 = the pad's, then SPEEDS), then if there: its label, its picture (w, h, then
# the bits: (w + 7) // 8 bytes a row) and its action; the encoder label; cw and ccw, each a 0/1 byte
# and the action; then (if it has lights) the scene, color 1 and color 2 (a 0/1 byte and r, g, b),
# the brightness and the speed; then (if it has one) the card picture (w, h, bits). Texts are a length byte and UTF-8. Actions are packed like macro
# steps (keymap.OP; actions.read_step unpacks them).

from ember.actions import read_step

NUM_KEYS = 8
SPEEDS = ("normal", "careful", "slow")      # typing speeds (actions.SPEED): the "type_speed" setting, or a key's own


class Layer:
    def __init__(self, name):
        self.name = name
        self.labels = [""] * NUM_KEYS
        self.pics = [None] * NUM_KEYS       # (w, h, bits) or None
        self.present = [False] * NUM_KEYS   # a key is there (even one with no action: a label)
        self.keys = [None] * NUM_KEYS       # (kind, value) actions
        self.repeat = [False] * NUM_KEYS
        self.confirm = [False] * NUM_KEYS
        self.speed = [None] * NUM_KEYS      # a key's own typing speed (None: the pad's setting)
        self.enc_label = ""
        self.cw = None
        self.ccw = None
        self.accel = False
        self.lights = None                  # (scene, color 1, color 2, brightness, speed)
        self.jiggle = False
        self.num_lock = False
        self.module_view = 0
        self.card = None                    # its layer card's picture (w, h, bits) or None


def _text(data, i):
    n = data[i]
    return str(data[i + 1:i + 1 + n], "utf-8"), i + 1 + n


def _action(data, i):
    if data[i]:
        return read_step(data, i + 1)
    return None, i + 1


def unpack(name, data):
    layer = Layer(name)
    flags = data[0]
    layer.accel = bool(flags & 1)
    layer.jiggle = bool(flags & 4)
    layer.num_lock = bool(flags & 8)
    layer.module_view = (flags >> 5) & 3
    i = 1
    for k in range(NUM_KEYS):
        f = data[i]
        i += 1
        if not f & 1:
            continue
        layer.present[k] = True
        layer.repeat[k] = bool(f & 4)
        layer.confirm[k] = bool(f & 8)
        if f >> 5:
            layer.speed[k] = SPEEDS[(f >> 5) - 1]
        layer.labels[k], i = _text(data, i)
        if f & 16:
            w, h = data[i], data[i + 1]
            n = ((w + 7) >> 3) * h
            layer.pics[k] = (w, h, data[i + 2:i + 2 + n])
            i += 2 + n
        if f & 2:
            layer.keys[k], i = read_step(data, i)
    layer.enc_label, i = _text(data, i)
    layer.cw, i = _action(data, i)
    layer.ccw, i = _action(data, i)
    if flags & 2:
        scene, i = _text(data, i)
        colors = []
        for _ in range(2):
            if data[i]:
                colors.append((data[i + 1], data[i + 2], data[i + 3]))
                i += 4
            else:
                colors.append(None)
                i += 1
        layer.lights = (scene, colors[0], colors[1], data[i], data[i + 1])
        i += 2
    if flags & 16:
        w, h = data[i], data[i + 1]
        layer.card = (w, h, data[i + 2:i + 2 + ((w + 7) >> 3) * h])
    return layer


class Keymap:
    def __init__(self, names, blob, offsets, home, hold, files=(), secret=(), secret_names=()):
        self.NAMES = names                  # layer names, in picker order (never the secret pages)
        self.SECRET = secret                # the secret pages' indexes in the blob, in page order
        self.SECRET_NAMES = secret_names
        self.FILES = files                  # each layer's file in layers/ (live remapping saves it)
        self.blob = blob                    # every packed layer, one after another
        self.offsets = offsets              # layer i is blob[offsets[i]:offsets[i + 1]]
        self.HOME = home                    # the home layer's index
        self.HOLD = hold                    # the HOLD+KEY keys' index (packed like a layer), or None
        self._index = None
        self._layer = None
        self.PIN = False                    # the secret pages have a PIN and aren't open yet (keymap.load)
        self.SECRET_NOTE = ""               # why the secret pages are (not) loaded (keymap.load)

    def layer(self, index):
        """The unpacked layer `index` (the last one asked for is kept)."""
        if index != self._index:
            self._layer = None
            o = self.offsets
            self._layer = unpack(self.name_of(index), memoryview(self.blob)[o[index]:o[index + 1]])
            self._index = index
        return self._layer

    def replace(self, index, packed):
        """A layer packed again (live remapping): swapped into the blob, the offsets after it moved."""
        o = self.offsets
        old = o[index + 1] - o[index]
        self.blob = self.blob[:o[index]] + bytes(packed) + self.blob[o[index + 1]:]
        shift = len(packed) - old
        self.offsets = tuple(v if n <= index else v + shift for n, v in enumerate(o))
        self._index = self._layer = None

    def name_of(self, index):
        if index < len(self.NAMES):
            return self.NAMES[index]
        if index in self.SECRET:
            return self.SECRET_NAMES[self.SECRET.index(index)]
        return "HOLD+KEY"

    def is_secret(self, index):
        return index is not None and index in self.SECRET

    def find(self, name):
        for i, n in enumerate(self.NAMES):
            if n == name:
                return i
        return None
