"""Build the Ember page (app/ember.html) and the phone app page (app/phone.html) from their pieces (app/parts/*.html, joined by
tools/assemble.py) -> EMBER_01/BUILD_PAGES/MP1 Ember.html. One file, everything inline (no .js files).

    py tools/make_page.py [EMBER_NN]

First writes app/parts/font.html from the pad's own font table (lib/ember/font.py, made by
make_font.py), so the page draws keys with exactly the pad's pixels.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import assemble     # noqa: E402


def font_part(fw):
    """lib/ember/font.py -> app/parts/font.html (the same numbers, as JavaScript)."""
    ns = {}
    with open(os.path.join(fw, "lib", "ember", "font.py"), encoding="utf-8") as f:
        exec(f.read(), ns)
    js = ("<script>\n// Made by tools/make_page.py from lib/ember/font.py (Terminus 12, SIL Open Font License 1.1):\n"
          "// the pad's own font table. Don't edit.\n"
          "const FONT = {{FIRST: {}, ROWS: {}, CAPS: {}, ATLAS_W: {}, W: [{}], X: [{}], BITS: '{}'}};\n</script>\n").format(
        ns["FIRST"], ns["ROWS"], ns["CAPS"], ns["ATLAS_W"], ",".join(str(b) for b in ns["W"]),
        ",".join(str(x) for x in ns["X"]), ns["BITS"].hex())
    with open(os.path.join(fw, "app", "parts", "font.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(js)


def _literals(path, names):
    """The plain-value assignments NAME = ... of a pad file, read without running it."""
    import ast
    out = {}
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in names:
            out[node.targets[0].id] = ast.literal_eval(node.value)
    missing = set(names) - set(out)
    if missing:
        sys.exit("{}: {} not found".format(path, ", ".join(sorted(missing))))
    return out


def lists_part(fw):
    """The pad's settings, menu groups, functions, colors and scenes -> app/parts/padlists.html, so the
    page offers exactly what the pad accepts (one shared list)."""
    import json
    lib = os.path.join(fw, "lib", "ember")
    st = _literals(os.path.join(lib, "settings.py"), ["SETTINGS"])
    mn = _literals(os.path.join(lib, "menus.py"), ["GROUPS", "LABELS", "STEP", "FUNCTION_SETTINGS"])
    gs = _literals(os.path.join(lib, "gestures.py"), ["FUNCTIONS"])
    lt = _literals(os.path.join(lib, "lights.py"), ["COLORS", "COLOR_NAMES", "SCENES", "SCENE_COLORS"])
    data = {
        "settings": {k: {"default": d, "allowed": list(a) if a is not None else None} for k, (d, a) in st["SETTINGS"].items()},
        "groups": [[g, list(names)] for g, names in mn["GROUPS"]],
        "labels": mn["LABELS"], "step": mn["STEP"], "function_settings": list(mn["FUNCTION_SETTINGS"]),
        "functions": [list(f) for f in gs["FUNCTIONS"]],
        "colors": {n: "#{:02x}{:02x}{:02x}".format(*lt["COLORS"][n]) for n in lt["COLOR_NAMES"]},
        "scenes": list(lt["SCENES"]), "scene_colors": lt["SCENE_COLORS"],
    }
    for g, names in data["groups"]:
        for n in names:
            if n not in data["settings"] or n not in data["labels"]:
                sys.exit("menus.py: {} isn't a setting with a label".format(n))
    js = ("<script>\n// Made by tools/make_page.py from lib/ember/settings.py, menus.py, gestures.py and lights.py:\n"
          "// the pad's own lists. Don't edit.\nconst PADLIST = {};\n</script>\n").format(json.dumps(data, separators=(",", ":")))
    with open(os.path.join(fw, "app", "parts", "padlists.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(js)


CHECK_JS = r"""
const fs = require('fs'), h = fs.readFileSync(0, 'utf8'); let n = 0, bad = 0;
for (const m of h.matchAll(/<script>([\s\S]*?)<\/script>/g)) {
  n++;
  try { new Function(m[1]); } catch (e) { bad++; console.log('script ' + n + ' (' + m[1].slice(0, 80).replace(/\s+/g, ' ') + '...): ' + e.message); }
}
process.exit(bad ? 1 : 0);
"""


def check_scripts(page):
    """Every <script> in the page must parse (node; skipped if node isn't there)."""
    import subprocess
    try:
        r = subprocess.run(["node", "-e", CHECK_JS], input=page.encode(), capture_output=True)
    except FileNotFoundError:
        print("(node not found: scripts not checked)")
        return
    if r.returncode:
        sys.exit("a script in the page doesn't parse:\n" + r.stdout.decode())


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "EMBER_01"
    fw = os.path.normpath(os.path.join(HERE, "..", name))
    font_part(fw)
    lists_part(fw)
    out = os.path.join(fw, "BUILD_PAGES")
    os.makedirs(out, exist_ok=True)
    # the page, and the phone app's page (the same parts where they overlap: phone_app/build.sh bundles it)
    for src, dest_name in (("app/ember.html", "MP1 Ember.html"), ("app/phone.html", "MP1 Ember Phone.html")):
        page = assemble.assemble(fw, src)
        if re.search(r"<!-- @include ", page):
            sys.exit("an @include was left in " + dest_name)
        check_scripts(page)
        dest = os.path.join(out, dest_name)
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(page)
        print("{} ({} KB)".format(dest, len(page.encode()) // 1024))


if __name__ == "__main__":
    main()
