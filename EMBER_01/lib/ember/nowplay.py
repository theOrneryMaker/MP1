# ember/nowplay.py - the Spotify screen (the "spotify" pad function: double click by default; a click goes back).
# Loaded only while it's open (App.open_np / App.show), then let go.
#
# Top 37 px: the song, the artist, the time and a bar. Under it 8 small keys (31 x 12), fixed:
#     +  Shuffle  Repeat  Here          (Liked Songs on / off; shuffle; repeat off / all / one; play on this computer)
#     Prev  Play/Pause  Next  Mute
# The song comes from the Ember page ({"c": "np", ...}: link.py keeps it in app.np), which asks Spotify every
# few seconds. The page says whether Spotify plays on THIS computer ("local"): then Prev / Play / Next / Mute and
# the encoder (volume) are the computer's own media keys; elsewhere they go through Spotify ({"t": "np", "do": ...}
# to the page). The top row always needs the page. Without the page the bottom row and the volume still work
# (media keys).

import displayio
import bitmaptools
from ember import clock
from ember.screen import W, COL_X, draw_text, text_width, fit, hline

TOP_H = 37
KEY_W, KEY_H = 31, 12
KEY_Y = (38, 51)
KEYS = ("like", "shuffle", "repeat", "here", "prev", "play", "next", "mute")
MEDIA = {"prev": 0xB6, "play": 0xCD, "next": 0xB5, "mute": 0xE2}
VOL_UP, VOL_DN = 0xE9, 0xEA
VOL_STEP = 5                # % a click, when the volume goes through Spotify
NOTE_MS = 1500
SCROLL_MS, SCROLL_WAIT_MS = 350, 2500

ICONS = {                   # (w, h, bits: (w + 7) // 8 bytes a row) - made by the page's icon sets / by hand
    "like": (9, 9, b'>\x00A\x00\x88\x80\x88\x80\xbe\x80\x88\x80\x88\x80A\x00>\x00'),
    "liked": (9, 9, b'>\x00\x7f\x00\xfe\x80\xfc\x80\xb3\x80\xc7\x80\xef\x80\x7f\x00>\x00'),
    "shuffle": (10, 9, b'\x00\x80\xe3\xc0\xf7\xc0\x14\x80\x08\x00\x1c\x80\xf7\xc0\xe3\xc0\x00\x80'),
    "repeat": (11, 9, b'\x00\x80\x7f\xc0\x80\x80\x80\x00\x80 \x00   \x7f\xc0 \x00'),
    "repeat1": (11, 9, b'\x00\x80\x7f\xc0\x80\x80\x8c\x00\x84 \x04   \x7f\xc0 \x00'),
    "here": (13, 9, b'?\xe0`0`0`0`0`0\x00\x00\xff\xf8\xff\xf8'),
    "prev": (8, 9, b'\xc3\xc7\xcf\xff\xff\xff\xcf\xc7\xc3'),
    "play": (8, 9, b'\xc0\xf0\xf8\xfe\xff\xfe\xf8\xf0\xc0'),
    "pause": (8, 9, b'\xe7\xe7\xe7\xe7\xe7\xe7\xe7\xe7\xe7'),
    "next": (8, 9, b'\xc3\xe3\xf3\xff\xff\xff\xf3\xe3\xc3'),
    "mute": (12, 9, b'\x06\x00\x0e\x00\x1e\x00\xfe\xf0\xfe`\xfe\xf0\x1e\x00\x0e\x00\x06\x00'),
}


def _clock(s):
    s = max(0, int(s))
    return "{}:{:02d}".format(s // 60, s % 60)


def _icon(bm, name, x, y):
    w, h, data = ICONS[name]
    bpr = (w + 7) >> 3
    for yy in range(h):
        for xx in range(w):
            if data[yy * bpr + (xx >> 3)] & (0x80 >> (xx & 7)):
                bm[x + xx, y + yy] = 1


class View:
    def __init__(self, app):
        self.app = app
        g = displayio.Group()
        pal = displayio.Palette(2)
        pal[0], pal[1] = 0x000000, 0xFFFFFF
        self.top = displayio.Bitmap(W, TOP_H, 2)
        g.append(displayio.TileGrid(self.top, pixel_shader=pal))
        self.cells, self.pals = [], []
        self.lit = [False] * 8              # a key shown inverted: Shuffle / Repeat while on
        for k in range(8):
            p = displayio.Palette(2)
            p[0], p[1] = 0x000000, 0xFFFFFF
            b = displayio.Bitmap(KEY_W, KEY_H, 2)
            self.cells.append(b)
            self.pals.append(p)
            g.append(displayio.TileGrid(b, pixel_shader=p, x=COL_X[k % 4], y=KEY_Y[k // 4]))
        self.group = g
        app.screen.root.append(g)
        app.screen.overlay = g
        self.note = ""
        self.note_until = 0
        self.start = 0                      # the title's first letter showing (it scrolls when too long)
        self.scroll_at = clock.add(clock.now(), SCROLL_WAIT_MS)
        self.second = -1
        self.title = None
        self.send({"t": "np", "open": True})
        self.draw()

    def close(self):
        self.send({"t": "np", "open": False})
        scr = self.app.screen
        try:
            scr.root.remove(self.group)
        except ValueError:
            pass
        scr.overlay = None
        self.group = self.top = self.cells = self.pals = None

    def send(self, msg):
        link = self.app.link
        if link is not None and link.live:
            link.send(msg)
            return True
        return False

    def live(self):
        link = self.app.link
        return link is not None and link.live and link.port.connected

    # ── what shows ──
    def song(self):
        np = self.app.np
        return np if np and np.get("title") is not None and self.live() else None

    def draw(self):
        self.group.hidden = False
        self.draw_top(clock.now())
        self.draw_keys()
        self.app.dirty = True

    def draw_top(self, now):
        b = self.top
        bitmaptools.fill_region(b, 0, 0, W, TOP_H, 0)
        np, s = self.app.np, self.song()
        if not self.live():
            lines = ("Spotify", "Open the Ember page", "to see the song.")
        elif not np:
            lines = ("Spotify", "Asking Spotify...", "")
        elif np.get("msg"):
            lines = ("Spotify", np["msg"], "")
        elif s is None:
            lines = ("Nothing playing", np.get("device") or "", "")
        else:
            lines = None
        if lines:
            for i, t in enumerate(lines):
                draw_text(b, 1, 1 + i * 12, fit(t, W - 2))
        else:
            title = s.get("title") or ""
            if title != self.title:
                self.title, self.start = title, 0
                self.scroll_at = clock.add(now, SCROLL_WAIT_MS)
            draw_text(b, 1, 1, fit(title[self.start:], W - 2))
            draw_text(b, 1, 13, fit(s.get("artist") or "", W - 2))
            if self.note and clock.diff(now, self.note_until) < 0:
                draw_text(b, (W - text_width(self.note)) // 2, 26, self.note)
            else:
                pos, ln = self.position(now), s.get("len") or 0
                a, z = _clock(pos), _clock(ln)
                draw_text(b, 1, 26, a)
                draw_text(b, W - 1 - text_width(z), 26, z)
                x0, x1 = text_width(a) + 5, W - text_width(z) - 6
                if x1 - x0 > 8:
                    hline(b, x0, x1, 29, True)
                    fill = x0 + int((x1 - x0) * min(pos, ln) / ln) if ln else x0     # (whole pixels: pos counts fractions)
                    bitmaptools.fill_region(b, x0, 28, max(x0 + 1, fill + 1), 31, 1)
        hline(b, 0, W - 1, TOP_H - 1, True)

    def position(self, now):
        s = self.app.np
        pos = s.get("pos") or 0
        if s.get("playing"):                # (never negative: the song can arrive a moment after `now` was read)
            pos += max(0, clock.diff(now, self.app.np_at)) / 1000
        return min(pos, s.get("len") or pos)

    def draw_keys(self):
        s = self.song()
        for k, name in enumerate(KEYS):
            b = self.cells[k]
            bitmaptools.fill_region(b, 0, 0, KEY_W, KEY_H, 0)
            on = False
            icon = name
            if s:
                if name == "like" and s.get("liked"):
                    icon = "liked"
                elif name == "shuffle":
                    on = bool(s.get("shuffle"))
                elif name == "repeat":
                    rep = s.get("repeat") or "off"
                    icon, on = ("repeat1" if rep == "track" else "repeat"), rep != "off"
                elif name == "play" and s.get("playing"):
                    icon = "pause"
            w = ICONS[icon][0]
            _icon(b, icon, (KEY_W - w) // 2, 1)
            if k < 4 and not self.live():   # (the top row needs the page: dotted under it)
                hline(b, KEY_W // 2 - 5, KEY_W // 2 + 5, KEY_H - 1, True)
            self.lit[k] = on                # (on: the whole key inverted)
            self.flash(k, False)

    def flash(self, k, down):
        """A press shows the key the other way round (an inverted, "on" key flashes back to normal)."""
        p = self.pals[k]
        p[0], p[1] = (0xFFFFFF, 0x000000) if down != self.lit[k] else (0x000000, 0xFFFFFF)
        self.app.dirty = True

    def say(self, text, now=None):
        now = now if now is not None else clock.now()
        self.note, self.note_until = text, clock.add(now, NOTE_MS)
        self.draw_top(now)
        self.app.dirty = True

    # ── keys, the encoder, time ──
    def local(self):
        """Prev / Play / Next / Mute / volume as this computer's media keys? (Spotify here, or nothing known)"""
        s = self.song()
        return s is None or bool(s.get("local"))

    def key(self, k, pressed, now):
        self.flash(k, pressed)
        if not pressed:
            return
        name, s = KEYS[k], self.song()
        if k >= 4:
            if self.local():
                self.app.actions.cc.send(MEDIA[name])
                self.send({"t": "np", "do": name, "local": True})     # (the page looks again sooner)
            else:
                self.send({"t": "np", "do": name})
            if s and name == "play":
                s["playing"] = not s.get("playing")
                s["pos"], self.app.np_at = self.position(now), now
        elif not self.send({"t": "np", "do": name}):
            return self.say("Needs the Ember page", now)
        elif s:                             # (shown at once; the page's next look confirms it)
            if name == "like":
                s["liked"] = not s.get("liked")
            elif name == "shuffle":
                s["shuffle"] = not s.get("shuffle")
            elif name == "repeat":
                s["repeat"] = {"off": "context", "context": "track"}.get(s.get("repeat") or "off", "off")
        self.draw_keys()
        self.draw_top(now)
        self.flash(k, True)                 # (still held: drawing the keys again reset its flash)

    def turn(self, delta, now):
        s = self.song()
        if self.local():
            code = VOL_UP if delta > 0 else VOL_DN
            for _ in range(min(abs(delta), 4)):
                self.app.actions.cc.send(code)
            return self.say("Volume +" if delta > 0 else "Volume -", now)
        vol = s.get("vol")
        if vol is None:
            return self.say("Volume: on the device", now)
        vol = max(0, min(100, vol + delta * VOL_STEP))
        s["vol"] = vol
        self.send({"t": "np", "do": "vol", "to": vol})
        self.say("Volume {}%".format(vol), now)

    def changed(self):
        """A new message from the page."""
        if self.group is not None:
            self.draw()

    def tick(self, now):
        s = self.song()
        redraw = False
        if self.note and clock.diff(now, self.note_until) >= 0:
            self.note = ""
            redraw = True
        if s:
            sec = int(self.position(now))
            if sec != self.second:
                self.second = sec
                redraw = True
            title = s.get("title") or ""
            if text_width(title[self.start:]) > W - 2 and clock.diff(now, self.scroll_at) >= 0:
                self.start += 1
                self.scroll_at = clock.add(now, SCROLL_WAIT_MS if text_width(title[self.start:]) <= W - 2 else SCROLL_MS)
                redraw = True
            elif self.start and clock.diff(now, self.scroll_at) >= 0:
                self.start = 0              # (the end was shown a moment: from the start again)
                self.scroll_at = clock.add(now, SCROLL_WAIT_MS)
                redraw = True
        if redraw:
            self.draw_top(now)
            self.app.dirty = True
