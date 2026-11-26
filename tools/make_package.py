"""The Ember update package: one zip with the firmware and the drive files, for the phone app's full update
(and for anyone updating by hand). The drive files include the page, so every pad carries its own copy
(works with no internet).
    py tools/make_package.py [EMBER_01]   ->  EMBER_01/BUILD_FROZEN/MP1_Ember_update_<fw>_YD-RP2040.zip
Run tools/make_page.py first (the page) and the firmware build (BUILD_FROZEN/firmware/*.uf2).
Never ships user files (keymap, layers, settings, wiring, secret): the update keeps the pad's own.
"""
import json
import os
import re
import sys
import time
import zipfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
# UF2 name -> (board, CircuitPython board_ids it may go on: stock YD-RP2040, MP1 04 custom, MP1 Ember)
BOARDS = {"mp1_ember_yd_rp2040": ("YD-RP2040", ["vcc_gnd_yd_rp2040", "mp1_yd_rp2040", "mp1_ember_yd_rp2040"])}
DRIVE = ["boot.py", "code.py"]                        # from the build folder, as they are
PAGE = ("BUILD_PAGES/MP1 Ember.html", "MP1 Ember.html")


def main(folder):
    fw_dir = os.path.join(ROOT, folder)
    link = open(os.path.join(fw_dir, "lib", "ember", "link.py"), encoding="utf-8").read()
    fw = re.search(r'FW\s*=\s*"([^"]+)"', link).group(1)
    ver = re.search(r'VER\s*=\s*"([^"]+)"', link).group(1)          # the release, e.g. 01.4
    page = os.path.join(fw_dir, PAGE[0])
    if not os.path.exists(page):
        sys.exit("no page: run tools/make_page.py first")
    fdir = os.path.join(fw_dir, "BUILD_FROZEN", "firmware")
    made = 0
    for uf2 in sorted(n for n in os.listdir(fdir) if n.endswith(".uf2")):
        if uf2[:-4] not in BOARDS:
            continue
        board, ids = BOARDS[uf2[:-4]]
        zname = os.path.join(fw_dir, "BUILD_FROZEN", "MP1_Ember_update_{}_{}.zip".format(fw, board))
        files = {"drive/" + n: os.path.join(fw_dir, n) for n in DRIVE}
        files["drive/" + PAGE[1]] = page
        man = {"mp1_package": 1, "fw": fw, "version": ver, "board": board, "board_ids": ids, "uf2": "firmware.uf2",
               "built": time.strftime("%Y-%m-%d %H:%M"),
               "firmware_built": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(os.path.join(fdir, uf2))))}
        with zipfile.ZipFile(zname, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("mp1_package.json", json.dumps(man, indent=2))
            z.write(os.path.join(fdir, uf2), "firmware.uf2")
            for arc, src in files.items():
                z.write(src, arc)
        print("update package:", zname, os.path.getsize(zname) // 1024, "KB:", ", ".join(["firmware.uf2"] + sorted(files)))
        made += 1
    if not made:
        sys.exit("no firmware UF2 in " + fdir)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "EMBER_01")
