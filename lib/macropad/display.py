# /lib/macropad/display.py
# Owns every label on the 128x64 OLED. Text is only rewritten when it changes, and the
# screen is sent once per batch of changes (refresh()) instead of whenever CircuitPython
# decides to redraw, so the OLED never shows a half-drawn screen and the I2C link is
# only busy when something actually changed.

import time
import displayio
import terminalio
from adafruit_display_text import label

KEY_POS = ((8, 26), (40, 26), (72, 26), (104, 26),
           (8, 50), (40, 50), (72, 50), (104, 50))
# Menu reel: where an item sits in each slot (centre y, scale). Slot 1 is the selected
# item; slots -1 and 3 are just off screen, so items slide in and out at the edges.
REEL_SLOTS = {-1: (-14, 1), 0: (8, 1), 1: (30, 2), 2: (52, 1), 3: (74, 1)}
REEL_ROWS = 4           # items moving at once during a roll
MAX_SCALE = 2
FIT_WIDTH = 120         # pixels a menu item may use (from x = 4)
MENU_CHARS = 10         # characters that fit at 2x
BAR_W, BAR_H, BAR_Y = 100, 8, 46    # hold-to-confirm progress bar

try:
    import bitmaptools  # scales text to any size in C (fast)
except ImportError:
    bitmaptools = None


def _label(x=0, y=0, scale=1, **kwargs):
    return label.Label(terminalio.FONT, text="", color=0xFFFFFF, x=x, y=y, scale=scale, **kwargs)


def show_splash(display, path="boot.bmp"):
    """Start-up image (boot.bmp on the drive, any 1-bit BMP up to 128x64, centred), shown
    instead of the console text while the macropad starts. Falls back to a plain title.
    Read straight from the drive (OnDiskBitmap), so it costs almost no memory."""
    group = displayio.Group()
    try:
        image = displayio.OnDiskBitmap(path)
        group.append(displayio.TileGrid(image, pixel_shader=image.pixel_shader,
                                        x=(128 - image.width) // 2, y=(64 - image.height) // 2))
    except Exception as e:                  # missing / not a BMP / unsupported format
        print("Start-up image not shown ({}): {}".format(path, e))
        title = _label(scale=3, anchor_point=(0.5, 0.5), anchored_position=(64, 30))
        title.text = "MP1"
        group.append(title)
    display.root_group = group
    return group


class ScaledText:
    """One line of text at any size, e.g. 1.37x (labels only scale by whole numbers).
    The text is drawn at 1x into a small bitmap once, then scaled into a full-width
    bitmap for each frame. Bitmaps are made once and reused, so frames allocate nothing."""

    def __init__(self):
        font = terminalio.FONT
        self.font = font
        self.cell_w, self.cell_h = font.get_bounding_box()[:2]
        self.max_chars = 128 // self.cell_w
        self.src = displayio.Bitmap(self.cell_w * self.max_chars, self.cell_h, 2)
        self.half = self.cell_h * MAX_SCALE // 2
        self.dest = displayio.Bitmap(128, self.half * 2, 2)
        palette = displayio.Palette(2)
        palette[0] = 0x000000
        palette[1] = 0xFFFFFF
        palette.make_transparent(0)
        self.grid = displayio.TileGrid(self.dest, pixel_shader=palette, x=0, y=0)
        self.grid.hidden = True
        self.text = ""
        self.scale = 0
        self.sheet = font.bitmap
        self.tiles_per_row = max(1, self.sheet.width // self.cell_w)

    def set(self, text, center_y=0, scale=1.0):
        """Show text left-aligned at x=4 (like the menu rows), or hide when empty.
        Returns True if anything changed."""
        text = text[:self.max_chars]
        if text:                            # long text shrinks to fit the width (x = 4..124)
            scale = min(scale, FIT_WIDTH / (len(text) * self.cell_w))
        y = int(center_y) - self.half
        if text == self.text and scale == self.scale and (not text or y == self.grid.y):
            return False
        if text != self.text:
            self.text = text
            self._draw_source()
        self.grid.hidden = not text
        if not text:
            return True
        self.grid.y = y
        if scale != self.scale:
            self.scale = scale
            w, h = len(text) * self.cell_w, self.cell_h
            self.dest.fill(0)
            bitmaptools.rotozoom(self.dest, self.src,
                                 ox=4 + int(w * scale) // 2, oy=self.half,
                                 px=w // 2, py=h // 2,
                                 source_clip0=(0, 0), source_clip1=(w, h),
                                 scale=scale, skip_index=0)
        return True

    def _draw_source(self):
        self.scale = 0                      # force a re-scale
        if not self.text:
            return
        w, h = self.cell_w, self.cell_h
        self.src.fill(0)
        for i, ch in enumerate(self.text):
            glyph = self.font.get_glyph(ord(ch))
            if glyph is None:
                continue
            tile = glyph.tile_index
            sx = (tile % self.tiles_per_row) * w
            sy = (tile // self.tiles_per_row) * h
            bitmaptools.blit(self.src, self.sheet, i * w, 0, x1=sx, y1=sy, x2=sx + w, y2=sy + h)


class _SmallRoll:
    """Fallback when bitmaptools is missing: rolling items move but stay small."""

    def __init__(self):
        self.label = _label(4, 0)
        self.grid = self.label
        self.text = ""

    def set(self, text, center_y=0, scale=1.0):
        y = int(center_y)
        if text == self.text and (not text or y == self.label.y):
            return False
        self.text = self.label.text = text
        self.label.y = y
        return True


class Screen:
    def __init__(self, display):
        self.display = display
        self.wait = time.sleep              # the app swaps in a wait that keeps lights/sound running
        self.dirty = True
        self.keys = [_label(x, y) for x, y in KEY_POS]
        self.enc = _label(8, 8)             # encoder icon / setting name (top left)
        self.timer = _label(40, 8)          # timer countdown / stopwatch (top bar)
        self.jiggle = _label(120, 8)        # blinking "J" (top right)
        # Caps Lock: black text in a white box, just left of the "J". It blinks to the
        # inverse (white text on black) by swapping to a second, plain label.
        self.caps = label.Label(terminalio.FONT, text="CAPS", color=0x000000,
                                background_color=0xFFFFFF, padding_left=1, padding_right=1,
                                x=93, y=8)
        self.caps_inverse = _label(93, 8)
        self.caps_inverse.text = "CAPS"
        self.caps.hidden = self.caps_inverse.hidden = True
        # Menu rows: next item on top, current item large in the middle, previous at the bottom
        self.menu_rows = (_label(4, 8), _label(4, 30, scale=2), _label(4, 52))
        # Centered big text: layer names, messages, values
        self.big = _label(scale=2, anchor_point=(0.5, 0.5), anchored_position=(64, 32))
        # Multi-line small text (error screen): 5 lines of 21 characters
        self.text = _label(0, 6, line_spacing=1.0)
        # Menu rolling between items, like a slot-machine reel (see show_reel)
        self.roll_rows = self._make_roll_rows()
        # Lock page: a full-screen white fill behind the text for the inverted flash
        self.lock_fill = self._make_fill()
        self.lock_hint = _label(anchor_point=(0.5, 0.5), anchored_position=(64, 54))
        self.lock_inverted = False
        # Hold-to-confirm: a progress bar under the key's icon
        self.bar, self.bar_bitmap = self._make_bar()
        self.bar_filled = 0

        root = displayio.Group()
        if self.lock_fill is not None:
            root.append(self.lock_fill)         # first, so everything else draws on top
        for lbl in self.keys + [self.enc, self.timer, self.jiggle, self.caps, self.caps_inverse] + list(self.menu_rows) + [self.big, self.text, self.lock_hint]:
            root.append(lbl)
        for row in self.roll_rows:
            root.append(row.grid)
        if self.bar is not None:
            root.append(self.bar)
        display.root_group = root
        self.root = root
        self.off = False                    # screen saver has switched the panel off
        self.panel_sleep = True             # False: panel has no sleep(), blank by hiding instead
        try:
            display.auto_refresh = False    # we call refresh() ourselves
        except AttributeError:
            pass

    @staticmethod
    def _make_roll_rows():
        if bitmaptools is not None:
            try:
                return tuple(ScaledText() for _ in range(REEL_ROWS))
            except Exception as e:          # unexpected font/bitmap API: fall back to small text
                print("Menu rolling uses small text:", e)
        return tuple(_SmallRoll() for _ in range(REEL_ROWS))

    @staticmethod
    def _make_fill():
        """128x64 white: a 2x1 bitmap drawn at 64x scale (uses a few bytes, not a full bitmap)."""
        try:
            bitmap = displayio.Bitmap(2, 1, 2)
            bitmap.fill(1)
            palette = displayio.Palette(2)
            palette[0] = 0x000000
            palette[1] = 0xFFFFFF
            fill = displayio.Group(scale=64)
            fill.append(displayio.TileGrid(bitmap, pixel_shader=palette))
            fill.hidden = True
            return fill
        except Exception as e:
            print("Lock page can't invert:", e)
            return None

    @staticmethod
    def _make_bar():
        """BAR_W x BAR_H, 1 bit a pixel (about 100 bytes)."""
        try:
            bitmap = displayio.Bitmap(BAR_W, BAR_H, 2)
            palette = displayio.Palette(2)
            palette[0] = 0x000000
            palette[1] = 0xFFFFFF
            grid = displayio.TileGrid(bitmap, pixel_shader=palette, x=(128 - BAR_W) // 2, y=BAR_Y)
            grid.hidden = True
            return grid, bitmap
        except Exception as e:
            print("No confirm bar:", e)
            return None, None

    def show_confirm(self, icon):
        """Hold-to-confirm: the key's icon, large, over an empty bar."""
        self.clear()
        if self.big.scale != 2:
            self.big.scale = 2
            self.dirty = True
        self._set(self.big, icon)
        self._set(self.enc, "HOLD")
        bitmap = self.bar_bitmap
        if bitmap is None:
            return
        bitmap.fill(0)
        for x in range(BAR_W):              # outline
            bitmap[x, 0] = bitmap[x, BAR_H - 1] = 1
        for y in range(BAR_H):
            bitmap[0, y] = bitmap[BAR_W - 1, y] = 1
        self.bar_filled = 0
        self.bar.hidden = False
        self.dirty = True

    def set_confirm(self, fraction):
        """Fill the bar to fraction (0..1); only the new columns are drawn."""
        bitmap = self.bar_bitmap
        if bitmap is None:
            return
        inside = BAR_W - 4
        filled = min(inside, int(inside * fraction))
        for x in range(self.bar_filled, filled):
            for y in range(2, BAR_H - 2):
                bitmap[x + 2, y] = 1
        if filled != self.bar_filled:
            self.bar_filled = filled
            self.dirty = True

    def _ink(self, lbl, color):
        if getattr(lbl, "color", None) != color:
            lbl.color = color
            self.dirty = True

    def show_lock(self, title, hint, inverted):
        """Full-screen lock page; inverted = black text on white."""
        self.clear()
        self.lock_inverted = inverted
        if self.lock_fill is not None and self.lock_fill.hidden == inverted:
            self.lock_fill.hidden = not inverted
            self.dirty = True
        ink = 0x000000 if inverted else 0xFFFFFF
        self._ink(self.big, ink)
        self._ink(self.lock_hint, ink)
        if self.big.scale != 2:
            self.big.scale = 2
            self.dirty = True
        self._set(self.big, title)
        self._set(self.lock_hint, hint)

    def _set(self, lbl, text):
        if lbl.text != text:
            lbl.text = text
            self.dirty = True

    def set_brightness(self, level):
        """Screen saver dimming (OLED contrast)."""
        try:
            self.display.brightness = level
        except (AttributeError, ValueError, RuntimeError, NotImplementedError):
            pass

    def power(self, on):
        """Screen saver: panel off / back on. Content keeps updating while off and is
        sent in one go when it wakes."""
        if on == (not self.off):
            return
        self.off = not on
        if self.panel_sleep:
            try:
                if on:
                    self.display.wake()
                else:
                    self.display.sleep()
            except AttributeError:
                self.panel_sleep = False
        if not self.panel_sleep:
            self.root.hidden = not on       # fallback: draw a blank screen
        self.dirty = True

    def refresh(self):
        """Send pending changes to the OLED (one transfer per batch of changes)."""
        if not self.dirty or (self.off and self.panel_sleep):
            return
        self.dirty = False
        try:
            self.display.refresh(target_frames_per_second=None)
        except (AttributeError, TypeError):
            pass                            # displays without manual refresh redraw on their own

    def clear(self, keep_roll=False):
        """Blank everything except the timer and jiggle indicators."""
        for lbl in self.keys:
            self._set(lbl, "")
        for lbl in self.menu_rows:
            self._set(lbl, "")
        self._set(self.enc, "")
        self._set(self.big, "")
        self._set(self.text, "")
        self._set(self.lock_hint, "")
        if self.bar is not None and not self.bar.hidden:
            self.bar.hidden = True
            self.dirty = True
        if self.lock_inverted:                  # leaving the lock page: back to white on black
            self.lock_inverted = False
            if self.lock_fill is not None:
                self.lock_fill.hidden = True
            self._ink(self.big, 0xFFFFFF)
            self._ink(self.lock_hint, 0xFFFFFF)
            self.dirty = True
        if not keep_roll:
            for row in self.roll_rows:
                if row.set(""):
                    self.dirty = True

    def show_text(self, lines):
        self.clear()
        self._set(self.text, "\n".join(lines))

    def show_keys(self, icons, enc_icon):
        self.clear()
        for i, lbl in enumerate(self.keys):
            self._set(lbl, icons[i] if i < len(icons) else "")
        self._set(self.enc, enc_icon)

    def show_menu(self, prev, curr, next_):
        self.clear()
        self._set(self.menu_rows[0], next_)
        self._set(self.menu_rows[2], prev)
        row = self.roll_rows[0]
        if len(curr) > MENU_CHARS and isinstance(row, ScaledText):
            if row.set(curr, REEL_SLOTS[1][0], MAX_SCALE):  # too long for 2x: shrunk to fit
                self.dirty = True
        else:
            self._set(self.menu_rows[1], curr)

    def show_reel(self, moves, t):
        """One frame of a menu roll. moves = ((text, from_slot, to_slot), ...);
        t = 0..1 of the way through. Each item slides between slots and grows or
        shrinks smoothly (small at the edges, large in the middle)."""
        self.clear(keep_roll=True)
        for i, row in enumerate(self.roll_rows):
            if i < len(moves):
                text, a, b = moves[i]
                ya, sa = REEL_SLOTS[a]
                yb, sb = REEL_SLOTS[b]
                y = ya + (yb - ya) * t
                scale = round((sa + (sb - sa) * t) * 8) / 8     # 1/8 steps: crisper, fewer re-scales
                changed = row.set(text, y, scale)
            else:
                changed = row.set("")
            if changed:
                self.dirty = True

    def show_stopwatch(self, text, icons):
        """Large time in the middle, key icons on the bottom row."""
        self.show_big(text, scale=2, title="STOPWATCH")
        for i in range(4, 8):
            self._set(self.keys[i], icons[i])

    def show_big(self, text, scale=2, title=""):
        self.clear()
        if self.big.scale != scale:
            self.big.scale = scale
            self.dirty = True
        self._set(self.big, text)
        self._set(self.enc, title)

    def flash(self, text, seconds, scale=2):
        """Show a centered message for a moment, then blank it."""
        self.show_big(text.upper(), scale)
        self.refresh()
        self.wait(seconds)
        self._set(self.big, "")

    def set_timer(self, text):
        self._set(self.timer, text)

    def set_caps(self, on, inverse=False):
        """on: show the CAPS indicator; inverse: white text on black instead of the box."""
        box, plain = on and not inverse, on and inverse
        if self.caps.hidden == box or self.caps_inverse.hidden == plain:
            self.caps.hidden = not box
            self.caps_inverse.hidden = not plain
            self.dirty = True

    def set_jiggle(self, text):
        self._set(self.jiggle, text)
