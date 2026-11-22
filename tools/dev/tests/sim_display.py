"""Strict stand-ins for displayio / bitmaptools / supervisor (whole numbers only, in bounds) for the pad
simulations: import it before any ember module."""
import sys
import time
import types


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
