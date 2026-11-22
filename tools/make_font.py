"""Make EMBER_01/lib/ember/font.py from Terminus 12 (tools/keyfont/ter-u12n.bdf, OFL).

    py tools/make_font.py

ASCII 32-126, trimmed to proportional widths (the same trimming as the screen mock-ups), rows 2-11
of each 12-row glyph (capitals on rows 0-7 of what's kept, descenders on 8-9). All glyphs side by side
in one strip ATLAS_W pixels wide and ROWS high, packed 1 bit a pixel, rows top to bottom, leftmost pixel
in the top bit of each byte (each row starts on a new byte).
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BDF = os.path.join(HERE, "keyfont", "ter-u12n.bdf")
OUT = os.path.join(HERE, "..", "EMBER_01", "lib", "ember", "font.py")
FIRST, LAST, TOP, ROWS, SPACE_W = 32, 126, 2, 10, 2


def glyphs():
    out, cur, rows = {}, None, None
    for line in open(BDF, encoding="latin-1"):
        w = line.split()
        if not w:
            continue
        if w[0] == "ENCODING":
            cur = int(w[1])
        elif w[0] == "BITMAP":
            rows = []
        elif w[0] == "ENDCHAR":
            if cur is not None and FIRST <= cur <= LAST:
                out[cur] = rows
            rows = None
        elif rows is not None:
            rows.append(int(w[0], 16))
    return out


def main():
    g = glyphs()
    widths, offsets, columns = [], [], []          # columns: list of (code, column index in the glyph)
    for code in range(FIRST, LAST + 1):
        rows = g.get(code, g[ord("?")])[TOP:TOP + ROWS]
        mask = 0
        for r in rows:
            mask |= r
        cols = [c for c in range(8) if mask & (0x80 >> c)]
        if not cols:                                # space
            offsets.append(len(columns))
            widths.append(SPACE_W)
            columns += [(None, 0)] * SPACE_W
            continue
        l, r = cols[0], cols[-1]
        offsets.append(len(columns))
        widths.append(r - l + 1)
        columns += [(rows, c) for c in range(l, r + 1)]
    atlas_w = len(columns)
    bpr = (atlas_w + 7) // 8
    bits = bytearray(bpr * ROWS)
    for x, (rows, c) in enumerate(columns):
        if rows is None:
            continue
        for y in range(ROWS):
            if rows[y] & (0x80 >> c):
                bits[y * bpr + (x >> 3)] |= 0x80 >> (x & 7)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write("# ember/font.py - made by tools/make_font.py from Terminus 12 (SIL Open Font License 1.1,\n")
        f.write("# Copyright (C) 2020 Dimitar Toshkov Zhekov). Don't edit: run the tool again.\n")
        f.write("# Characters 32-126; W = widths, X = where each starts in the strip; capitals on rows 0-7.\n")
        f.write("FIRST = {}\nROWS = {}\nCAPS = 8\nATLAS_W = {}\n".format(FIRST, ROWS, atlas_w))
        f.write("W = {!r}\n".format(bytes(widths)))
        f.write("X = {!r}\n".format(tuple(offsets)))
        f.write("BITS = {!r}\n".format(bytes(bits)))
    print("font.py: {} characters, strip {} x {}, {} bytes of pixels".format(len(widths), atlas_w, ROWS, len(bits)))


if __name__ == "__main__":
    main()
