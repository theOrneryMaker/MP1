"""Runs ember/nowplay.py on the PC with strict stand-ins for displayio / bitmaptools (whole numbers only, in
bounds), through songs, ticks, keys and turns, and prints the screen as text. Catches type / bounds mistakes
before they reach a pad.   py tools/dev/tests/sim_nowplay.py
"""
import os
import sys
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "EMBER_01", "lib")))


def need_int(*vals):
    for v in vals:
        if not isinstance(v, int) or isinstance(v, bool):
            raise TypeError("not a whole number: {!r}".format(v))


class Bitmap:
    def __init__(self, w, h, n):
        need_int(w, h, n)
        self.width, self.height = w, h
        self.d = [[0] * w for _ in range(h)]

    def __setitem__(self, xy, v):
        x, y = xy
        need_int(x, y, v)
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise IndexError("pixel {} outside {}x{}".format(xy, self.width, self.height))
        self.d[y][x] = v

    def __getitem__(self, xy):
        x, y = xy
        return self.d[y][x]


class Palette(list):
    def __init__(self, n):
        super().__init__([0] * n)


class Group(list):
    hidden = False


def TileGrid(bm, pixel_shader=None, x=0, y=0):
    need_int(x, y)
    return types.SimpleNamespace(bitmap=bm, x=x, y=y)


def fill_region(bm, x1, y1, x2, y2, v):
    need_int(x1, y1, x2, y2, v)
    for y in range(max(0, y1), min(bm.height, y2)):
        for x in range(max(0, x1), min(bm.width, x2)):
            bm.d[y][x] = v


def blit(dst, src, x, y, x1=0, y1=0, x2=None, y2=None, skip_source_index=None):
    x2 = src.width if x2 is None else x2
    y2 = src.height if y2 is None else y2
    need_int(x, y, x1, y1, x2, y2)
    for yy in range(y1, y2):
        for xx in range(x1, x2):
            v = src.d[yy][xx]
            if v == skip_source_index:
                continue
            dx, dy = x + xx - x1, y + yy - y1
            if not (0 <= dx < dst.width and 0 <= dy < dst.height):
                raise IndexError("blit outside the bitmap at {},{}".format(dx, dy))
            dst.d[dy][dx] = v


sys.modules["displayio"] = types.SimpleNamespace(Bitmap=Bitmap, Palette=Palette, Group=Group, TileGrid=TileGrid)
sys.modules["bitmaptools"] = types.SimpleNamespace(fill_region=fill_region, blit=blit)
sys.modules["supervisor"] = types.SimpleNamespace(ticks_ms=lambda: int(time.monotonic() * 1000) & 0x3FFFFFFF)

from ember import nowplay, clock  # noqa: E402

SENT = []
link = types.SimpleNamespace(live=True, port=types.SimpleNamespace(connected=True), send=lambda m: SENT.append(m))
media = []
app = types.SimpleNamespace(screen=types.SimpleNamespace(root=Group(), overlay=None), link=link, np=None, np_at=0, dirty=False,
                            actions=types.SimpleNamespace(cc=types.SimpleNamespace(send=lambda c: media.append(c))))


def show(v):
    top = ["".join("#" if c else "." for c in row) for row in v.top.d]
    keys = []
    for r in range(2):
        for y in range(nowplay.KEY_H):
            keys.append(" ".join("".join("#" if c else "." for c in v.cells[r * 4 + k].d[y]) for k in range(4)))
        keys.append("")
    print("\n".join(top + [""] + keys))


v = nowplay.View(app)
now = clock.now()
for k in range(8):
    v.key(k, True, now)
    v.key(k, False, now)
v.turn(1, now)
print("no song yet: ok; sent", SENT[:3])
app.np = {"title": "Midnight Drive (Extended Mix) - Remastered 2024", "artist": "The Neon Arcade", "pos": 61, "len": 214, "playing": True,
          "liked": False, "shuffle": True, "repeat": "context", "local": True, "vol": None, "device": "JC-LAPTOP"}
app.np_at = clock.add(now, -1234)             # (a fraction of a second into the song)
v.changed()
for i in range(40):
    v.tick(clock.add(now, i * 400))
for k in range(8):
    v.key(k, True, now)
    v.key(k, False, now)
v.turn(-2, now)
print("local song: ok; media keys sent", media)
app.np = {"title": "Coffee & Keyboards", "artist": "Lo-Fi Desk Club", "pos": 30.7, "len": 167, "playing": False, "liked": True,
          "shuffle": False, "repeat": "track", "local": False, "vol": 40, "device": "Pixel 8"}
v.changed()
v.turn(3, now)
v.turn(-30, now)
for k in range(8):
    v.key(k, True, now)
    v.key(k, False, now)
print("remote song: ok; last sent", SENT[-4:])
app.np = {"title": "X", "artist": "", "pos": 0, "len": 0, "playing": True, "local": False, "vol": None}
v.changed()
v.tick(clock.add(now, 5000))
v.turn(1, now)
app.np = {"none": True, "device": "Pixel 8"}
v.changed()
app.np = {"msg": "Spotify: needs Premium"}
v.changed()
app.np = {"title": "Coffee & Keyboards", "artist": "Lo-Fi Desk Club", "pos": 95, "len": 167, "playing": True, "liked": True,
          "shuffle": True, "repeat": "track", "local": False, "vol": 40, "device": "Pixel 8"}
app.np_at = now
v.changed()
# the song arrives a moment AFTER the loop read `now` (link.tick runs mid-loop): the bar must not jump to the end
app.np_at = clock.add(now, 40)
pos = v.position(now)
assert pos == 95, "position jumped: {}".format(pos)
print("song stamped after now: position", pos, "(ok)")
assert v.lit == [False, True, True, False, False, False, False, False], v.lit
print("shuffle + repeat on -> lit keys", v.lit, "(ok)")
show(v)
v.close()
print("closed: ok; all steps passed")
