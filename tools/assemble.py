"""Join a web page's pieces: a line that is just  <!-- @include app/parts/NAME.html -->  is replaced
by that file, exactly as it is (its bytes and line endings). Paths are from the FIRMWARE_NN folder.
Pieces can include pieces. No .js files anywhere: the pieces are .html text, joined at build time,
so every page that ships is still one file (company PCs block .js files).

    py tools/assemble.py FIRMWARE_NN [OUT]      every page, joined, into OUT (default
                                                FIRMWARE_NN/BUILD_PAGES): open them from there
                                                to try a page on its own (theme.css is copied too)
make_app.py (MP1.html) reads the pages through assemble(), so the pieces never ship on their own.
"""
import os
import re
import shutil
import sys

INCLUDE = re.compile(r"^[ \t]*<!-- @include ([A-Za-z0-9_./-]+) -->[ \t]*\r?\n?$")
PAGES = ["app/shell.html", "mp1_configurator.html", "help.html", "Toolkit/module_guide.html", "Toolkit/mp1_workbench.html"]
PARTS = "app/parts"                         # (left out of every build: make_app.py removes it)


def lines(text):
    """Lines with their own endings (\\n or \\r\\n). Not str.splitlines: that also splits at
    characters like U+2028 that a script's strings may hold."""
    return re.split(r"(?<=\n)", text)


def assemble(fw, rel, _seen=()):
    """The page (or piece) at FIRMWARE_NN/rel with every include filled in."""
    if rel in _seen:
        raise ValueError("{} includes itself (through {})".format(rel, " > ".join(_seen)))
    path = os.path.join(fw, rel)
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    out = []
    for line in lines(text):
        m = INCLUDE.match(line)
        if m:
            out.append(assemble(fw, m.group(1), _seen + (rel,)))
        else:
            out.append(line)
    return "".join(out)


def main(fw, out=None):
    out = out or os.path.join(fw, "BUILD_PAGES")
    for rel in PAGES:
        if not os.path.exists(os.path.join(fw, rel)):
            continue
        dest = os.path.join(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(assemble(fw, rel))
    css = os.path.join(fw, "theme.css")
    if os.path.exists(css):
        shutil.copy2(css, os.path.join(out, "theme.css"))
    print("Pages joined into", out)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
