#!/bin/bash
# Check a drive image made by phone_image.mjs (run in WSL): fsck.fat finds no errors, and every file in plan.json
# reads back with the same size and SHA-1 (mtools; long names included).
#   wsl -d Ubuntu-24.04 -- bash tools/dev/tests/phone_image_check.sh OUTDIR   (OUTDIR as a /mnt/c/... path)
set -e
D="$1"
IMG="$D/drive.img"
echo "== fsck.fat"
fsck.fat -n "$IMG" | tail -3
echo "== files"
python3 - "$D" <<'EOF'
import hashlib, json, subprocess, sys
d = sys.argv[1]
plan = json.load(open(d + "/plan.json"))
bad = 0
for f in plan["files"]:
    p = f["path"]
    try:
        data = subprocess.run(["mtype", "-i", d + "/drive.img", "::/" + p], capture_output=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        print("MISSING", p, e.stderr.decode().strip()[:80]); bad += 1; continue
    if len(data) != f["size"] or hashlib.sha1(data).hexdigest() != f["sha1"]:
        print("DIFFERENT", p, len(data), f["size"]); bad += 1
for dd in plan["dirs"]:
    r = subprocess.run(["mdir", "-i", d + "/drive.img", "::/" + dd], capture_output=True)
    if r.returncode:
        print("NO FOLDER", dd); bad += 1
print("{} files, {} folders checked: {}".format(len(plan["files"]), len(plan["dirs"]), "all match" if not bad else str(bad) + " PROBLEMS"))
sys.exit(1 if bad else 0)
EOF
