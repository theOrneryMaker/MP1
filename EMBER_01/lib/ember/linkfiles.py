# ember/linkfiles.py (from FIRMWARE_04)
# MP1 Link file commands: the page (MP1.html) lists, reads and saves the macropad's files over USB
# serial, so the MP1 drive never has to be opened. Loaded the first time the page asks for a file,
# then kept with link.py.
#
#   {"c": "ls", "id": 1, "path": "layers"}                  -> {"t": "r", "id": 1, "items": [[name, is folder, size], ...]}
#   {"c": "read", "id": 2, "path": "keymap.json", "off": 0}  -> {"t": "r", "id": 2, "data": base64, "size": n, "eof": true/false}
#   {"c": "write", "id": 3, "path": "keymap.json", "off": 0, "data": base64, "last": true}
#                                                            -> {"t": "r", "id": 3}   (saved when "last"; the old one kept as .bak)
#   {"c": "delete", "id": 4, "path": "layers/old.mp1layer.json"}, {"c": "mkdir", "id": 5, "path": "profiles"}
#   {"c": "df", "id": 7}                                     -> {"t": "r", "id": 7, "free": bytes, "size": bytes}
#   {"c": "restart", "id": 6}                                -> the macropad restarts (to use a saved keymap / settings)
# The firmware's own files (lib/, code.py, boot.py) can only be written or deleted during a firmware
# update ({"c": "sync", "on": true, "update": true}, link.py), and keep no .bak (room on the drive).
# A problem comes back as {"t": "r", "id": n, "err": "..."}. Saving only works while the MP1 drive
# isn't showing on a computer (the macropad started normally): then the macropad can write its files.

import os
import binascii

CHUNK = 768             # bytes per read reply (about 1 KB as base64)
_saving = {}            # path -> [save id, bytes so far, the open .part file]: each file's save going on


def _drop(path):
    """Forget a save (and close its file)."""
    st = _saving.pop(path, None)
    if st is not None:
        try:
            st[2].close()
        except Exception:
            pass
PROTECTED = ("lib", "boot.py", "code.py", "boot_out.txt")     # firmware: not over the link (yet)


def _path(raw):
    path = str(raw or "").replace("\\", "/").strip("/")
    parts = path.split("/")
    if not path or ".." in parts or "" in parts:
        raise ValueError("not a valid path: {}".format(raw))
    return path


def _firmware(path):
    return path.split("/")[0] in PROTECTED


def _writable(path, link=None):
    if _firmware(path) and not (link is not None and getattr(link, "updating", False)):
        raise ValueError("{} is part of the firmware: it can't be changed from here".format(path))


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def handle(link, msg):
    what, n = msg.get("c"), msg.get("id")
    reply = {"t": "r", "id": n}
    link.touch(writing=what in ("write", "delete", "mkdir"))
    try:
        if what == "skey":                      # secret.json's key (the configurator reads / writes it)
            import microcontroller
            uid = bytes(microcontroller.cpu.uid)    # (as keymap.secret_key: not loading keymap.py for it)
            salt = b"MP1 secret layer"
            reply["key"] = binascii.hexlify(bytes(salt[i] ^ uid[i % len(uid)] for i in range(16))).decode()
            link.send(reply)
            return
        if what == "df":                        # the drive's free space, in bytes
            st = os.statvfs("/")
            reply["free"] = st[0] * st[3]
            reply["size"] = st[0] * st[2]
            link.send(reply)
            return
        if what == "restart":
            link.done()
            link.send(reply)
            import supervisor
            supervisor.reload()
            return
        path = _path(msg.get("path")) if what != "ls" or msg.get("path") else ""
        if what == "ls":
            items = []
            for name in sorted(os.listdir(path or "/")):
                st = os.stat((path + "/" if path else "") + name)
                items.append([name, bool(st[0] & 0x4000), st[6]])
            reply["items"] = items
        elif what == "read":
            off = int(msg.get("off", 0))
            size = os.stat(path)[6]
            with open(path, "rb") as f:
                f.seek(off)
                data = f.read(CHUNK)
            reply["data"] = binascii.b2a_base64(data).decode().strip()
            reply["size"] = size
            reply["eof"] = off + len(data) >= size
            if size > CHUNK:                    # (small files: too quick to show)
                link.progress("READING", path, off + len(data), size)
        elif what == "write":
            _writable(path, link)
            part = path + ".part"
            data = binascii.a2b_base64(msg.get("data", ""))
            off = int(msg.get("off", 0))
            xid = msg.get("xid")
            # Each piece must belong to the save that started this file and follow straight on from
            # the last: pieces of two saves at once, or a save cut short by a restart, are refused
            # (the file stays as it was) instead of being joined into a damaged file.
            if off == 0:
                _drop(path)
                _saving[path] = [xid, 0, open(part, "wb")]   # kept open for the whole save: quicker
            else:
                st = _saving.get(path)
                if st is None or st[0] != xid or st[1] != off:
                    _drop(path)
                    _remove(part)
                    raise ValueError("the save of {} was interrupted (another save started, or the macropad restarted). Nothing was changed: save again".format(path))
            st = _saving[path]
            st[2].write(data)
            st[1] = off + len(data)
            total = int(msg.get("total", 0))
            if total > CHUNK:
                link.progress("SAVING", path, off + len(data), total)
            if msg.get("last"):
                got = _saving[path][1]
                _drop(path)
                if total and got != total:
                    _remove(part)
                    raise ValueError("the save of {} came out {} bytes instead of {}. Nothing was changed: save again".format(path, got, total))
                if _exists(path):               # the old one kept as .bak, like the configurator does
                    _remove(path + ".bak")
                    if _firmware(path):         # (firmware: replaced outright)
                        os.remove(path)
                    else:
                        os.rename(path, path + ".bak")
                os.rename(part, path)
        elif what == "cancel":             # (the page gave up on a save)
            _drop(_path(msg.get("path")))
        elif what == "delete":
            _writable(path, link)
            if os.stat(path)[0] & 0x4000:
                os.rmdir(path)              # a folder: only once it's empty (the page empties it first)
            else:
                os.remove(path)
        elif what == "mkdir":
            _writable(path, link)
            if not _exists(path):
                os.mkdir(path)
        else:
            reply["err"] = "unknown request {}".format(what)
    except OSError as e:
        code = e.args[0] if e.args else None
        reply["err"] = ("the MP1 drive is showing on a computer (the encoder was held at start-up), so the "
                        "macropad can't save its own files. Restart it without holding the encoder."
                        if code == 30 else "not found" if code == 2 else "file error {}".format(e))
    except Exception as e:
        reply["err"] = str(e)
    link.send(reply)
