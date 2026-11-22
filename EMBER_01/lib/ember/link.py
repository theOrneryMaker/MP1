# ember/link.py - MP1 Link: the page talks to the pad over the second USB serial channel that boot.py
# turns on (usb_cdc.data). Loaded when the page first connects, then kept (a reconnect never loads it again).
# One JSON object per line, both ways (FIRMWARE_04's protocol, minus profiles / chords / media slots,
# plus live remapping).
#
#   page -> pad:  {"c": "hello"}                         send the hello again
#                 {"c": "layer", "name": "EXCEL"}        go to a layer
#                 {"c": "press", "key": 0-7}             tap a key of the layer showing
#                 {"c": "key", "layer": "EXCEL", "k": 0-7, "key": {...}}   LIVE REMAP: one key, in the
#                     layer file's own shape (null = empty); "hold": true instead of "layer" = a HOLD+KEY key.
#                     Checked, swapped in, shown if that layer is up, and saved to its file.
#                     -> {"t": "keyok", "layer", "k", "saved": true/false} or {"t": "error", "msg"}
#                 {"c": "layerset", "layer": "EXCEL", "set": {"encoder": {...}, "lights": {...} or null, "jiggle": true, ...}}
#                     LIVE: a layer's own fields (encoder, lights, jiggle, num_lock, module_view, pic; null = remove
#                     the field), checked, swapped in and saved like a key. -> {"t": "layerok", "layer", "saved"} or error
#                 {"c": "setting", "name": "key_lines", "value": "boxes"}   LIVE: one of the pad's settings (settings.py),
#                     checked, used at once and saved to settings.json. -> {"t": "setok", "name", "saved"} or error
#                 {"c": "np", "title", "artist", "pos", "len" (s), "playing", "liked", "shuffle", "repeat", "local",
#                     "vol", "device"} or {"c": "np", "msg": ...} / {"c": "np", "device", "none": true}: the song (nowplay.py)
#                 {"c": "reload", "show": "EXCEL"}       the page wrote keymap.json / layer files (add, rename, reorder,
#                     delete): read them again and show that layer (or home). -> {"t": "reloaded", "errors": [...]}, then a hello
#                 {"c": "time", "t": [y, mo, d, h, mi, s, weekday, yearday]}   set the clock
#                 {"c": "extras"}                        reminders.json was written: read it again -> {"t": "extrasok"}
#                 {"c": "pinpad", "on": true, "dots": n, "note": "..."}   the page asks for a PIN: the pad's keys send
#                     {"t": "pinkey", "k": 0-7}, a left turn {"t": "pinback"}, a click {"t": "pinenter"}, holding
#                     {"t": "pinclose"}; nothing is typed. "on": false ends it.
#                 {"c": "opened", "id": n, "ok": true}   answer to "open"
#                 {"c": "sync", "on": true / false, "pct": 0-100}   a save / read is going on (see below)
#                 file commands (ls / read / write / delete / mkdir / df / restart / skey / cancel): linkfiles.py
#   pad -> page:  {"t": "hello", ...} / {"t": "state", ...}   the layer and its keys (labels and pictures)
#                 {"t": "open", "url": ..., "id": n}     a key's web address: the browser opens it
#                 {"t": "synced", "secs": s}             a sync ended
#                 {"t": "np", "open": true / false}      the Spotify screen opened / closed (the page asks Spotify more often)
#                 {"t": "np", "do": "like" | "shuffle" | "repeat" | "here" | "prev" | "play" | "next" | "mute" | "vol",
#                     "to": 0-100 (vol), "local": true (sent as media keys already: the page just looks again)}
#                 {"t": "error", "msg": ...}

import json
import gc
import binascii
from ember import clock

FW = "ember01"
LAYER_FIELDS = ("encoder", "lights", "jiggle", "num_lock", "module_view", "pic")
GONE_MS = 1000          # the page counts as gone after this long without the connected signal
SYNC_MIN_MS = 1500      # the SYNCING screen shows at least this long
SYNC_SILENCE_MS = 10000 # a sync ends by itself after this long without a word from the page
AUTO_QUIET_MS = 1500    # a save the page didn't announce ends when requests stop this long
OPEN_WAIT_MS = 800      # how long a web address waits for the browser to say it opened it
STATE_MS = 10000        # the state (free memory) is sent at least this often
MAX_LINE = 6144         # longer lines are dropped


class Link:
    def __init__(self, app, port):
        self.app = app
        self.port = port
        try:
            port.timeout = 0
            port.write_timeout = 0.05       # never hold up the main loop if the page stops reading
        except (AttributeError, ValueError):
            pass
        self.buf = b""
        self.live = True
        self.gone_at = None
        self.seq = 0
        self.files = None                   # linkfiles.py, the first time the page asks for a file
        self.syncing = False
        self.sync_since = self.busy_at = 0
        self.ending = False
        self.updating = False
        self.sent = None                    # what the last state showed (sent again when it changes)
        self.sent_at = clock.now()
        app.actions.open_url = self.open_url
        self.hello()

    def send(self, obj):
        try:
            self.port.write(json.dumps(obj).encode() + b"\n")
        except Exception:
            pass

    # ── what the page shows ──
    def view(self):
        """(layer name, its keys, encoder label, HOLD+KEY up) as the page should show them."""
        app = self.app
        hold = app.mode == app.HOLD
        if not hold and app.km.is_secret(app.index):       # (never its name or keys)
            return "SECRET", [None] * 8, "", False
        layer = app.km.layer(app.km.HOLD) if hold else app.layer
        keys = []
        for k in range(8):
            if not layer.present[k]:
                keys.append(None)
                continue
            pic = layer.pics[k]
            keys.append([layer.labels[k], [pic[0], pic[1], binascii.b2a_base64(pic[2]).decode().strip()] if pic else None])
        if hold:
            app.layer = app.km.layer(app.index)
        return app.km.name_of(app.index), keys, "" if hold else layer.enc_label, hold

    def state(self, kind="state"):
        app = self.app
        name, keys, enc, hold = self.view()
        self.sent = (app.index, hold, app.jiggle_on, app.km.offsets)
        self.sent_at = clock.now()
        gc.collect()
        msg = {"t": kind, "layer": name, "keys": keys, "enc": enc, "hold": hold, "jiggle": app.jiggle_on,
               "secret": app.km.is_secret(app.index),
               "free": gc.mem_free()}
        if kind == "hello":
            import sys
            lights = sys.modules.get("ember.lights")     # (the scenes, drop-ins too: only if the lights are in use)
            msg.update({"fw": FW, "frozen": True, "layers": list(app.km.NAMES), "home": app.km.NAMES[app.km.HOME],
                        "errors": list(app.errors), "clock": getattr(app, "clock_set", False),
                        "scenes": list(lights.SCENES) if lights else None,
                        "hw": {"lights": app.lights.pixels is not None, "sound": app.hw.get("buzzer", "none") != "none"},
                        "np": app.np_view is not None,
                        "secret_pages": len(app.km.SECRET), "secret_note": app.km.SECRET_NOTE, "secret_pin": app.km.PIN})
        self.send(msg)

    def hello(self):
        self.state("hello")

    # ── the main loop calls this every pass while the page is connected ──
    def tick(self, now):
        port = self.port
        if not port.connected:
            if self.gone_at is None:
                self.gone_at = now
            elif self.live and clock.since(self.gone_at, now) >= GONE_MS:
                self.live = False
                self.app.actions.open_url = None
            return
        self.gone_at = None
        if not self.live:
            self.live = True
            self.buf = b""
            self.app.actions.open_url = self.open_url
            self.hello()
        for _ in range(8):
            n = port.in_waiting
            if not n:
                break
            self.buf += port.read(n)
            while b"\n" in self.buf:
                line, self.buf = self.buf.split(b"\n", 1)
                if line.strip():
                    self.handle(line)
            if len(self.buf) > MAX_LINE:
                self.buf = b""
        app = self.app
        if (app.index, app.mode == app.HOLD, app.jiggle_on, app.km.offsets) != self.sent \
                or clock.since(self.sent_at, now) >= STATE_MS:
            self.state()

    # ── SYNC: while the page reads or saves files nothing else runs ──
    def touch(self, writing=False):
        self.busy_at = clock.now()
        if writing and not self.syncing:
            self.sync_start(auto=True)

    def progress(self, what, name, done, total):
        self.touch()

    def sync_start(self, auto=False, update=False):
        now = clock.now()
        self.busy_at = now
        self.ending = "auto" if auto else False
        self.updating = bool(update)
        if not self.syncing:
            self.syncing = True
            self.sync_since = now
            self.app.enter_sync("UPDATING" if update else "SYNCING")

    def sync_tick(self, now):
        self.tick(now)
        if not self.syncing:
            return
        now = clock.now()
        quiet = clock.since(self.busy_at, now)
        if (not self.live or quiet >= SYNC_SILENCE_MS
                or (self.ending and clock.since(self.sync_since, now) >= SYNC_MIN_MS
                    and quiet >= (AUTO_QUIET_MS if self.ending == "auto" else 0))):
            self.done()

    def done(self):
        if self.syncing:
            self.syncing = self.updating = False
            self.send({"t": "synced", "secs": clock.since(self.sync_since, clock.now()) / 1000})
            self.app.leave_sync()

    # ── web addresses ──
    def open_url(self, url):
        """A key's web address, opened by the browser the page is in. True if it did."""
        if not self.port.connected:
            return False
        self.seq += 1
        n = self.seq
        self.send({"t": "open", "url": url, "id": n})
        end = clock.add(clock.now(), OPEN_WAIT_MS)
        import time
        while clock.diff(clock.now(), end) < 0:
            k = self.port.in_waiting
            if k:
                self.buf += self.port.read(k)
                keep, found = [], None
                for line in self.buf.split(b"\n")[:-1]:
                    try:
                        msg = json.loads(line)
                    except ValueError:
                        msg = None
                    if isinstance(msg, dict) and msg.get("c") == "opened" and msg.get("id") == n:
                        found = msg.get("ok") is True
                    elif line.strip():
                        keep.append(line)
                rest = self.buf.split(b"\n")[-1]
                self.buf = b"\n".join(keep + [rest]) if keep else rest
                if found is not None:
                    return found
            time.sleep(0.01)
        return False

    # ── requests ──
    def handle(self, line):
        try:
            msg = json.loads(line)
            what = msg.get("c")
        except (ValueError, AttributeError):
            self.send({"t": "error", "msg": "not a JSON object"})
            return
        app = self.app
        if what == "hello":
            self.hello()
        elif what == "layer":
            i = app.km.find(msg.get("name"))
            if i is None:
                self.send({"t": "error", "msg": "no layer called {}".format(msg.get("name"))})
            elif app.mode != app.NORMAL:
                self.send({"t": "error", "msg": "the pad is busy (a menu or the lock is showing)"})
            else:
                app.show(i)
        elif what == "press":
            k = msg.get("key")
            if app.mode != app.NORMAL or not isinstance(k, int) or not 0 <= k < 8:
                self.send({"t": "error", "msg": "the pad is busy"})
            elif app.km.is_secret(app.index):
                self.send({"t": "error", "msg": "a secret layer's keys can't be pressed from here"})
            elif app.layer.confirm[k]:
                self.send({"t": "error", "msg": "a hold-to-confirm key only works on the pad"})
            elif app.layer.keys[k]:
                app.actions.tap(app.layer.keys[k])
                app.lights.react(clock.now())
        elif what == "key":
            self.remap(msg)
        elif what == "layerset":
            self.layerset(msg)
        elif what == "pinpad":              # the page asks for a PIN: the pad's keys give it the pattern (nothing typed)
            from ember.extras import PinPadView
            v = app.tool_view
            if msg.get("on"):
                if not isinstance(v, PinPadView):
                    app.show()
                    app.mode = app.TOOLVIEW
                    v = app.tool_view = PinPadView(app, self)
                v.show(int(msg.get("dots") or 0), str(msg.get("note") or "")[:21])
            elif isinstance(v, PinPadView):
                v.closed = lambda: None     # (the page closed it itself: no need to tell it)
                app.show()
        elif what == "extras":              # the page wrote reminders.json: read it again
            app.extras.load_reminders()
            self.send({"t": "extrasok", "reminders": len(app.extras.reminders)})
        elif what == "np":                  # the song (the page asks Spotify): kept for the Spotify screen
            msg.pop("c", None)
            app.np = msg
            app.np_at = clock.now()
            if app.np_view is not None:
                app.np_view.changed()
        elif what == "setting":
            self.setting(msg.get("name"), msg.get("value"))
        elif what == "reload":
            self.reload(msg.get("show"))
        elif what == "opened":
            pass
        elif what == "time":
            try:
                import rtc
                import time
                t = msg["t"]
                rtc.RTC().datetime = time.struct_time((t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7], -1))
                app.clock_set = True
            except Exception as e:
                self.send({"t": "error", "msg": "clock not set: {}".format(e)})
        elif what == "sync":
            if msg.get("on") and "pct" in msg and self.syncing:
                self.touch()
                app.sync_progress(msg.get("pct"))
            elif msg.get("on"):
                self.sync_start(update=msg.get("update") is True)
            else:
                self.ending = True
        elif what in ("ls", "read", "write", "delete", "mkdir", "restart", "skey", "df", "cancel"):
            if self.files is None:
                from ember import linkfiles
                self.files = linkfiles
            self.files.handle(self, msg)
        else:
            self.send({"t": "error", "msg": "unknown request {}".format(what)})

    def remap(self, msg):
        """Live remapping: one key changed from the page, used at once and saved."""
        k, key, hold = msg.get("k"), msg.get("key"), msg.get("hold") is True
        if not isinstance(k, int) or not 0 <= k < 8:
            return self.send({"t": "error", "msg": "no such key: {}".format(k)})
        if key is not None and not isinstance(key, dict):
            return self.send({"t": "error", "msg": "a key should be {...} or null"})

        def change(data):
            field = "hold_keys" if hold else "keys"
            keys = data.get(field)
            if not isinstance(keys, list):
                keys = []
            while len(keys) < 8:
                keys.append(None)
            keys[k] = key
            data[field] = keys
        name, saved = self.change(msg.get("layer"), hold, change)
        if saved is not None:
            self.send({"t": "keyok", "layer": name, "k": k, "saved": saved})

    def layerset(self, msg):
        """Live: a layer's own fields (encoder, lights, ...) changed from the page."""
        new = msg.get("set")
        if not isinstance(new, dict) or not new:
            return self.send({"t": "error", "msg": "set should be {...}"})
        for f in new:
            if f not in LAYER_FIELDS:
                return self.send({"t": "error", "msg": "a layer has no field {}".format(f)})

        def change(data):
            for f, v in new.items():
                if v is None:
                    data.pop(f, None)
                else:
                    data[f] = v
        name, saved = self.change(msg.get("layer"), False, change)
        if saved is not None:
            self.send({"t": "layerok", "layer": name, "saved": saved})

    def change(self, name, hold, change):
        """Read a layer's file (or keymap.json for HOLD+KEY), change(data) it, check and pack it with the
        start-up loader, swap it in, save the file. (name, saved) or (name, None) after an error was sent."""
        app, km = self.app, self.app.km
        if hold:
            name = "HOLD+KEY"
        index = km.HOLD if hold else km.find(name)
        if index is None:
            self.send({"t": "error", "msg": "no layer called {}".format(name)})
            return name, None
        path = "keymap.json" if hold else "layers/" + km.FILES[index]
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            self.send({"t": "error", "msg": "{} can't be read ({})".format(path, e)})
            return name, None
        change(data)
        from ember import keymap as loader
        del loader.ERRORS[:]
        packed = loader._pack_layer({"keys": data.get("hold_keys")} if hold else data, name)
        problems = list(loader.ERRORS)
        loader = None
        from ember import forget
        forget("keymap")
        gc.collect()
        if problems:
            self.send({"t": "error", "msg": "; ".join(problems)})
            return name, None
        km.replace(index, packed)
        app.hold_view = None                # (the HOLD+KEY screen is made again when next held)
        packed = None
        saved = True
        try:
            with open(path + ".new", "w") as f:
                json.dump(data, f)
            import os
            try:
                os.remove(path)
            except OSError:
                pass
            os.rename(path + ".new", path)
        except OSError:
            saved = False               # the drive is showing on a computer: used until a restart
        data = None
        if app.mode == app.NORMAL and index == app.index:
            app.show()
        else:
            app.layer = km.layer(app.index)
        return name, saved

    def setting(self, name, value):
        """Live: one setting from the page's Settings, checked as settings.json is at start-up, used, saved."""
        app = self.app
        from ember import settings, gestures, forget
        ok = name in settings.SETTINGS and settings._ok(name, value)
        if ok and name in ("click_single", "click_double", "click_triple", "hold_turn_right", "hold_turn_left"):
            ok = value in gestures.NAMES
        elif ok and name in ("light_scene", "light_color1", "light_color2"):
            import sys
            loaded = "ember.lights" in sys.modules
            from ember import lights
            ok = value in lights.SCENES if name == "light_scene" else lights.color(value) is not None
            lights = None
            if not loaded:
                forget("lights")            # (no lights fitted: not kept for this check)
        if not ok:
            forget("settings")
            return self.send({"t": "error", "msg": "{} can't be {}".format(name, json.dumps(value))})
        app.cfg[name] = value
        app.apply(name)
        saved = settings.save(app.cfg)
        forget("settings")
        gc.collect()
        if name in ("key_lines", "lock_boxes") and app.mode == app.NORMAL:
            app.show()
        self.send({"t": "setok", "name": name, "saved": saved})

    def reload(self, show):
        """The page wrote new keymap / layer files: read them all again (the old keymap let go first)."""
        app = self.app
        app.release_all()
        app.km = app.layer = None
        gc.collect()
        from ember import keymap as loader
        km = loader.load("/", app.secret_pin)      # (secret pages opened with their PIN since power-up: still open)
        errors = list(loader.ERRORS)
        loader = None
        from ember import forget
        forget("keymap")
        gc.collect()
        app.km = km
        app.hold_view = None
        app.errors = errors
        i = km.find(show) if show else None
        app.index = km.HOME if i is None else i
        app.prev_index = app.index
        app.layer = km.layer(app.index)
        if app.mode != app.SYNC:            # (in a sync, its end shows the layer)
            app.show()
        self.send({"t": "reloaded", "errors": errors})
        self.hello()
