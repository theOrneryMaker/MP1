# ember/screen.py - everything on the 128 x 64 OLED (NOTES/DECISIONS.md, "Pad screen").
#
# Layer view: a 10-pixel status row (layer name left; encoder label, Caps / Num boxes right), then
# 8 key cells of 31 x 26 (rows at y 11 and 38, columns 32 apart). Each cell is its own small bitmap
# with its own two-color palette, so a press flash just swaps the palette's colors (nothing redrawn).
# The status row and the key lines (Grid / Shelves / Boxes / Dotted) are drawn on one full-screen
# bitmap behind the cells. Text comes from ember/font.py (Terminus 12, proportional), copied with
# bitmaptools.blit; pictures are 1-bit, from the layer file (base64).
#
# The screen is sent only when refresh() is called, so it never shows half-drawn.

import displayio
import bitmaptools
from ember import font

W, H = 128, 64
STATUS_H = 10
CELL_W, CELL_H = 31, 26
ROW_Y = (11, 38)
COL_X = (0, 32, 64, 96)
LINE = 10                   # text line pitch
PIC_H_LABEL = 11            # a picture taller than this shows alone (no label line)
KEY_LINES = ("grid", "shelves", "boxes", "dotted")
LIST_Y, ROW_H, LIST_ROWS = 12, 13, 4     # list view: rows under the title
CARD_AREA = (STATUS_H, H - font.ROWS - 1)  # a layer card: the picture centred in these rows, the name below

_atlas = None


def _font():
    """The font strip as a Bitmap (made once: 416 x 10, about 600 bytes)."""
    global _atlas
    if _atlas is None:
        bpr = (font.ATLAS_W + 7) // 8
        b = displayio.Bitmap(font.ATLAS_W, font.ROWS, 2)
        bits = font.BITS
        for y in range(font.ROWS):
            row = y * bpr
            for x in range(font.ATLAS_W):
                if bits[row + (x >> 3)] & (0x80 >> (x & 7)):
                    b[x, y] = 1
        _atlas = b
    return _atlas


def _index(ch):
    i = ord(ch) - font.FIRST
    return i if 0 <= i < len(font.W) else ord("?") - font.FIRST


def text_width(s):
    if not s:
        return 0
    return sum(font.W[_index(c)] + 1 for c in s) - 1


def draw_text(bm, x, y, s, rows=None):
    """Text at (x, y) = the top of its capitals; rows=font.CAPS leaves out the descenders."""
    a = _font()
    rows = rows or font.ROWS
    for c in s:
        i = _index(c)
        w = font.W[i]
        if x + w > bm.width:
            break
        if c != " ":
            bitmaptools.blit(bm, a, x, y, x1=font.X[i], y1=0, x2=font.X[i] + w, y2=rows, skip_source_index=0)
        x += w + 1
    return x


def fit(s, w):
    while s and text_width(s) > w:
        s = s[:-1]
    return s


def wrap2(label, w):
    """Up to two lines that fit in w pixels (words kept whole where they fit)."""
    lines, cur = [], ""
    for word in label.split(" "):
        t = cur + " " + word if cur else word
        if text_width(t) <= w:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return [fit(l, w) for l in lines[:2]]


def draw_big(bm, x, y, s):
    """Text at double size (each pixel 2 x 2): a layer card's name when it has no picture."""
    w = text_width(s)
    t = displayio.Bitmap(max(1, w), font.ROWS, 2)
    draw_text(t, 0, 0, s)
    for yy in range(font.ROWS):
        for xx in range(w):
            if t[xx, yy]:
                bitmaptools.fill_region(bm, x + 2 * xx, y + 2 * yy, x + 2 * xx + 2, y + 2 * yy + 2, 1)


def picture(pic):
    """A packed picture (w, h, bits: (w + 7) // 8 bytes a row, leftmost pixel in the top bit) as a Bitmap."""
    if not pic:
        return None
    w, h, data = pic
    bpr = (w + 7) >> 3
    b = displayio.Bitmap(w, h, 2)
    for y in range(h):
        for x in range(w):
            if data[y * bpr + (x >> 3)] & (0x80 >> (x & 7)):
                b[x, y] = 1
    return b


def hline(bm, x0, x1, y, dotted=False):
    if dotted:
        for x in range(x0, x1 + 1):
            if not x & 1:
                bm[x, y] = 1
    else:
        bitmaptools.fill_region(bm, x0, y, x1 + 1, y + 1, 1)


def vline(bm, x, y0, y1, dotted=False):
    if dotted:
        for y in range(y0, y1 + 1):
            if not y & 1:
                bm[x, y] = 1
    else:
        bitmaptools.fill_region(bm, x, y0, x + 1, y1 + 1, 1)


def frame(bm, x0, y0, x1, y1, dotted=False):
    """A rectangle with its corner pixels left out (rounded)."""
    hline(bm, x0 + 1, x1 - 1, y0, dotted)
    hline(bm, x0 + 1, x1 - 1, y1, dotted)
    vline(bm, x0, y0 + 1, y1 - 1, dotted)
    vline(bm, x1, y0 + 1, y1 - 1, dotted)


def draw_key(bm, label, pic, lines):
    """One key's cell: its decoration for the key-lines style, then picture + label, centred."""
    bitmaptools.fill_region(bm, 0, 0, CELL_W, CELL_H, 0)
    x, y, w, h = 0, 0, CELL_W, CELL_H
    if lines in ("boxes", "dotted"):
        frame(bm, 0, 0, CELL_W - 1, CELL_H - 1, lines == "dotted")
        x, y, w, h = 1, 1, CELL_W - 2, CELL_H - 2
    elif lines == "shelves":
        hline(bm, 3, CELL_W - 4, CELL_H - 1)
        h = CELL_H - 1
    label = label or ""
    if pic is not None:
        alone = pic.height > PIC_H_LABEL or not label
        text = "" if alone else fit(label, w)
        total = pic.height + (LINE if text else 0)
        top = y + (h - total) // 2
        bitmaptools.blit(bm, pic, x + (w - pic.width) // 2, top, skip_source_index=0)
        if text:
            draw_text(bm, x + (w - text_width(text)) // 2, top + pic.height + 1, text)
    else:
        rows = wrap2(label, w)
        total = len(rows) * LINE - 2
        top = y + (h - total) // 2
        for i, t in enumerate(rows):
            draw_text(bm, x + (w - text_width(t)) // 2, top + i * LINE, t)


class Screen:
    def __init__(self, display, key_lines="grid"):
        self.display = display
        display.auto_refresh = False
        self.lines = key_lines if key_lines in KEY_LINES else "grid"
        self.root = displayio.Group()
        self.layer_view = displayio.Group()
        pal = displayio.Palette(2)
        pal[0], pal[1] = 0x000000, 0xFFFFFF
        self.back = displayio.Bitmap(W, H, 2)
        self.back_pal = displayio.Palette(2)     # (its own: the HOLD+KEY screen shows inverted)
        self.back_pal[0], self.back_pal[1] = 0x000000, 0xFFFFFF
        self.inverted = False
        self.layer_view.append(displayio.TileGrid(self.back, pixel_shader=self.back_pal))
        self.cells, self.palettes = [], []
        for k in range(8):
            p = displayio.Palette(2)
            p[0], p[1] = 0x000000, 0xFFFFFF
            b = displayio.Bitmap(CELL_W, CELL_H, 2)
            self.cells.append(b)
            self.palettes.append(p)
            self.layer_view.append(displayio.TileGrid(b, pixel_shader=p, x=COL_X[k % 4], y=ROW_Y[k // 4]))
        self.root.append(self.layer_view)
        # list view (menus, the layer picker, messages): a title row, then 4 rows, each with its own palette
        self.list_view = displayio.Group()
        self.title = displayio.Bitmap(W, STATUS_H + 1, 2)
        self.list_view.append(displayio.TileGrid(self.title, pixel_shader=pal))
        self.rows, self.row_pals = [], []
        for r in range(LIST_ROWS):
            p = displayio.Palette(2)
            p[0], p[1] = 0x000000, 0xFFFFFF
            b = displayio.Bitmap(W, ROW_H, 2)
            self.rows.append(b)
            self.row_pals.append(p)
            self.list_view.append(displayio.TileGrid(b, pixel_shader=p, y=LIST_Y + r * ROW_H))
        self.list_view.hidden = True
        self.root.append(self.list_view)
        # a layer card (the Layer cards picker): one full-screen bitmap
        self.card = displayio.Bitmap(W, H, 2)
        self.card_view = displayio.Group()
        self.card_view.append(displayio.TileGrid(self.card, pixel_shader=pal))
        self.card_view.hidden = True
        self.root.append(self.card_view)
        display.root_group = self.root
        self.name = self.enc = ""
        self.caps = self.num = False
        self.locks_shown = True
        self.overlay = None                 # a screen drawn over these (nowplay.py), hidden by a list / message

    # ── the status row and the lines behind the cells ──
    def _status(self):
        b = self.back
        bitmaptools.fill_region(b, 0, 0, W, STATUS_H, 0)
        draw_text(b, 1, 1, self.name, font.CAPS)
        right = W
        if self.locks_shown:
            cx, nx = W - 9, W - 19                       # C box (lit when on), N box
            if self.caps:
                bitmaptools.fill_region(b, cx, 0, cx + 9, STATUS_H, 1)
                self._punch(cx + 2, 1, "C")
            if self.num:
                frame(b, nx, 0, nx + 8, STATUS_H - 1)
                b[nx, 0] = b[nx + 8, 0] = b[nx, STATUS_H - 1] = b[nx + 8, STATUS_H - 1] = 1
                draw_text(b, nx + 2, 1, "N", font.CAPS)
            right = nx - 4
        enc = fit(self.enc, right - text_width(self.name) - 8)
        draw_text(b, right - text_width(enc), 1, enc, font.CAPS)

    def _punch(self, x, y, ch):
        """A capital letter cut out of a lit box (black on white)."""
        a, i = _font(), _index(ch)
        for r in range(font.CAPS):
            for c in range(font.W[i]):
                if a[font.X[i] + c, r]:
                    self.back[x + c, y + r] = 0

    def _lines(self):
        b = self.back
        bitmaptools.fill_region(b, 0, STATUS_H, W, H, 0)
        if self.lines == "grid":
            hline(b, 0, W - 1, STATUS_H, True)
            for x in (31, 63, 95):
                vline(b, x, STATUS_H + 2, H - 1, True)
            hline(b, 0, W - 1, 37, True)
        elif self.lines == "shelves":
            hline(b, 0, W - 1, STATUS_H)

    # ── what the rest of the program calls ──
    def show_layer(self, name, enc_label, keys, inverted=False):
        """keys: 8 x (label, picture Bitmap or None), or None for an empty key. inverted: black on white (HOLD+KEY)."""
        self.inverted = inverted
        self.back_pal[0], self.back_pal[1] = (0xFFFFFF, 0x000000) if inverted else (0x000000, 0xFFFFFF)
        self.name, self.enc = name, enc_label or ""
        self._status()
        self._lines()
        for k in range(8):
            key = keys[k] if k < len(keys) else None
            label, pic = key if key else ("", None)
            draw_key(self.cells[k], label, pic, self.lines)
            self.press(k, False)
        self.list_view.hidden = self.card_view.hidden = True
        self.layer_view.hidden = False

    def show_list(self, title, rows, sel=None, right_title=""):
        """A title and up to LIST_ROWS of rows: (left text, right text) each; the window scrolls to
        keep row `sel` in view, and that row is lit (sel None: nothing lit, e.g. a message)."""
        t = self.title
        bitmaptools.fill_region(t, 0, 0, W, STATUS_H + 1, 0)
        draw_text(t, 1, 1, title, font.CAPS)
        if right_title:
            draw_text(t, W - 1 - text_width(right_title), 1, right_title, font.CAPS)
        hline(t, 0, W - 1, STATUS_H)
        top = 0 if sel is None else min(max(0, sel - LIST_ROWS + 2), max(0, len(rows) - LIST_ROWS))
        if sel is not None and sel < top:
            top = sel
        for r in range(LIST_ROWS):
            b = self.rows[r]
            bitmaptools.fill_region(b, 0, 0, W, ROW_H, 0)
            i = top + r
            lit = sel is not None and i == sel
            p = self.row_pals[r]
            p[0], p[1] = (0xFFFFFF, 0x000000) if lit else (0x000000, 0xFFFFFF)
            if i < len(rows):
                left, right = rows[i] if isinstance(rows[i], tuple) else (rows[i], "")
                rw = text_width(right)
                draw_text(b, 3, 2, fit(left, W - 8 - (rw + 6 if rw else 0)))
                if right:
                    draw_text(b, W - 3 - rw, 2, right)
        if sel is not None and len(rows) > LIST_ROWS:         # where in the list: a short bar on the right
            h = max(3, LIST_ROWS * ROW_H * LIST_ROWS // len(rows))
            y = (LIST_ROWS * ROW_H - h) * top // max(1, len(rows) - LIST_ROWS)
            for r in range(LIST_ROWS):
                for yy in range(ROW_H):
                    if y <= r * ROW_H + yy < y + h:
                        self.rows[r][W - 1, yy] = 0 if (sel is not None and top + r == sel) else 1
        self.layer_view.hidden = self.card_view.hidden = True
        self.list_view.hidden = False
        if self.overlay is not None:
            self.overlay.hidden = True

    def show_canvas(self):
        """The full-screen bitmap, cleared and showing, for a screen that draws itself (extras.py's Timer and Counter)."""
        bitmaptools.fill_region(self.card, 0, 0, W, H, 0)
        self.layer_view.hidden = self.list_view.hidden = True
        self.card_view.hidden = False
        if self.overlay is not None:
            self.overlay.hidden = True
        return self.card

    def set_right(self, text):
        """The right of the top row (the encoder label, or the timer's time left), redrawn."""
        self.enc = text or ""
        self._status()

    def show_card(self, name, pic, left="", right=""):
        """A layer card: its picture (a Bitmap, up to 40 x 40) big in the middle, the name below; with no
        picture, the name in double-size letters. left / right: small text on the top row (HOME, 3/6)."""
        b = self.card
        bitmaptools.fill_region(b, 0, 0, W, H, 0)
        if left:
            draw_text(b, 1, 1, left, font.CAPS)
        if right:
            draw_text(b, W - 1 - text_width(right), 1, right, font.CAPS)
        if pic is not None:
            y0, y1 = CARD_AREA
            bitmaptools.blit(b, pic, (W - pic.width) // 2, y0 + (y1 - y0 - pic.height) // 2, skip_source_index=0)
            t = fit(name, W - 2)
            draw_text(b, (W - text_width(t)) // 2, H - font.ROWS, t)
        elif 2 * text_width(name) <= W - 4:
            draw_big(b, (W - 2 * text_width(name)) // 2, (H - 2 * font.ROWS) // 2 + 2, name)
        else:
            t = fit(name, W - 2)
            draw_text(b, (W - text_width(t)) // 2, (H - font.ROWS) // 2 + 2, t)
        self.layer_view.hidden = self.list_view.hidden = True
        self.card_view.hidden = False
        if self.overlay is not None:
            self.overlay.hidden = True

    def set_locks(self, caps, num):
        if (caps, num) != (self.caps, self.num):
            self.caps, self.num = caps, num
            self._status()

    def press(self, k, down):
        p = self.palettes[k]
        p[0], p[1] = (0xFFFFFF, 0x000000) if down != self.inverted else (0x000000, 0xFFFFFF)

    def set_key_lines(self, lines):
        self.lines = lines if lines in KEY_LINES else "grid"

    def refresh(self):
        try:
            self.display.refresh()
        except Exception:               # (the OLED missed a beat: the next refresh catches up)
            pass
