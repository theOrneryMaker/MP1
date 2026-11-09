# MP1 Macropad: Upgrading from the Old Firmware

About 15 minutes. You need the USB cable, a computer with **Chrome or Edge** (other browsers work too, they just download files instead of saving them where you choose), and the new firmware folder (`FIRMWARE_00`).

## At a glance: what happens to each old file

| Old file on MACROPAD | What to do |
|---|---|
| `keymap.json` | **Save it, then convert** to `keymap.js` (step 4). The new firmware won't read the old format. Until you do, the package's **starter `keymap.js`** is used, so the pad still works. |
| `settings.json` | **Save it, then convert** to `settings.js` (step 5). All your settings carry over. |
| `wiring.py` | **Save it, but don't reuse the file.** Copy any pin numbers you changed into the *new* `wiring.py` (step 6). The old file is missing entries the new firmware needs and will stop it starting. |
| `boot.py` | **Keep it** (leave it on the drive). The new firmware uses the same one. |
| `boot_out.txt`, `settings.toml` (if there) | Keep. |
| `code.py`, `keymap.py`, `default.json`, `help.html`, `keymap_configurator.html`, `macro_recorder.html` | Delete. Replaced by the new files (the macro recorder is now built into the configurator). |
| `lib/` folder | **Delete the whole folder** and copy in the new one. An old `lib/macropad/menus/` folder left behind stops the new firmware starting. |

---

## Step 1: Open the drive

Hold the **encoder button** down while you plug the macropad in, and keep holding it for about 3 seconds. The **MACROPAD** drive appears on your computer.

## Step 2: Check the CircuitPython version

Open `boot_out.txt` on MACROPAD. The first line shows the version.

- **10.x** (tested on 10.0.3): good, go to step 3.
- **9.x or older**: back up first (step 3), then update CircuitPython:
  1. Download the CircuitPython **10.x** `.uf2` for the **YD-RP2040** from circuitpython.org.
  2. Unplug. Hold the board's **BOOT** button, plug in, release. A drive called **RPI-RP2** appears.
  3. Drag the `.uf2` onto RPI-RP2. The board restarts and MACROPAD comes back (your files are kept).

The new `lib` files are built for CircuitPython 10 and won't load on older versions.

## Step 3: Back up the old firmware

Copy **everything** on MACROPAD into a new folder on your computer, e.g. `MP1 backup 2026-11-08`. You need these four from it:

- `keymap.json`
- `settings.json`
- `wiring.py`
- `boot.py`

Keep the backup until the new firmware is working.

## Step 4: Convert keymap.json to keymap.js

1. On your computer, open **`keymap_configurator.html`** from the **new** firmware folder (double-click it).
2. Click **Open file…** and pick `keymap.json` from your **backup** folder.
3. It converts automatically and shows **"Converted a version 1 keymap with N layers"** plus a list of anything it adjusted. Read the list.
4. Check each layer tab:
   - **Home layer:** the layer the pad starts on is ticked **Home layer**.
   - **Secret layer:** your old secret layer is now **Secret 1**.
   - **Icons:** each icon is up to 4 characters, as before.
5. The **Save keymap** section at the bottom should say **No problems found**. Fix anything it lists.
6. Click **Save as…** and save it as **`keymap.js`** (keep the `.js` ending).

## Step 5: Convert settings.json to settings.js

1. Open **`settings_editor.html`** from the **new** firmware folder.
2. Click **Open file…** and pick `settings.json` from your **backup** folder. Your settings load; new settings that didn't exist before get their defaults.
3. Optional: look through the sections. For example, add-ons are off by default: set **LED count** above 0 if you have an LED strip, and pick a **Buzzer** type if you have a buzzer.
4. Click **Save as…** and save it as **`settings.js`**.

(Skipping this step also works: the pad still reads `settings.json`. But with `settings.js` the web pages load your settings automatically.)

## Step 6: wiring.py: use the new file

Open your old wiring.py and the new wiring.py and verify your pins match.
- **Standard build** (keys on GP21/22 and GP26-29, encoder on GP8/9/10, screen on GP14/15): nothing to do. Use the new `wiring.py` as it is.
- **You changed pins:** open your **old** `wiring.py` and the **new** one side by side. Copy only your pin numbers into the new file: `ROWS`, `COLS`, `ENC_A`, `ENC_B`, `ENC_SW`, `I2C_SCL`, `I2C_SDA`, `OLED_ADDRESS`. Leave the new lines (`I2C_FREQUENCY`, `LED_STRIP_PIN`, `BUZZER_PIN`) in place.

**Don't** copy the old `wiring.py` onto the drive: it's missing those new lines, and the macropad won't start.

## Step 7: Clean the drive

On MACROPAD, **delete everything except**:

- `boot.py`
- `boot_out.txt`
- `settings.toml` (if there is one)

Make sure the **`lib`** folder is gone completely.

## Step 8: Copy the new firmware

Copy these from the **new** firmware folder to the root of MACROPAD (not into a sub-folder):

- `lib` (the whole folder)
- `code.py`, `keymap.py`, `wiring.py` (from step 6)
- `boot.bmp`, `default.js`
- `keymap_configurator.html`, `settings_editor.html`, `help.html`
- `mp1files.js`, `theme.css`, `theme.js`

Then the keymap and settings:

- `keymap.js`: **your converted one** (step 4). If you haven't converted yet, copy the package's **starter `keymap.js`** for now. It has six ready-made layers (MEDIA, EDIT, NAV, BROWSER, WINDOWS, PRESENT), so the pad works straight away, and you can swap in your converted keymap later.
- `settings.js`: your converted one (step 5). Without it the pad uses `settings.json` if that's still there, or the defaults.

Notes:

- `enctest.py` is a troubleshooting tool. You don't need to copy it.
- The starter `keymap.js` contains no personal text. A `keymap.js` you get from anyone else can hold typed text such as passwords, so only use the starter or your own.
- The screen may flash errors while files are copying (CircuitPython restarts on every change). Ignore them until everything is copied.

## Step 9: Start it normally

Unplug, then plug back in **without** holding the encoder. You should see:

1. The **MP1** start-up image.
2. Your home layer's name, then its icons.

If the screen lists errors instead, read them (turn the encoder to page through them, click to close). They name the layer and key to fix in the configurator.

## Step 10: Check the web pages

Hold the encoder while plugging in to open the drive, then open `keymap_configurator.html` and `settings_editor.html` **from the Macropad drive**. They load `keymap.js` and `settings.js` by themselves. In Chrome or Edge, **Connect folder…** (pick MACROPAD) lets **Save to drive** write straight to the pad from then on. `help.html` explains every new feature.

---

## If something goes wrong

| What you see | Cause and fix |
|---|---|
| Screen says **"keymap.json is the old v1 format"** | There's no `keymap.js` on the drive, only the old `keymap.json`. Copy the starter `keymap.js` (or do step 4 and copy your converted one), and delete `keymap.json`. |
| Your old keys are gone, and you see MEDIA, EDIT, NAV... | That's the starter `keymap.js`. Convert your old `keymap.json` (step 4) and copy your `keymap.js` over the starter one. |
| Nothing starts. The serial console shows an error about `menus`, or **`wiring` has no attribute `I2C_FREQUENCY` / `LED_STRIP_PIN`** | Old files are left over: the old `lib/macropad` folder, or the old `wiring.py`. Redo steps 7 and 8. |
| **"Incompatible .mpy file"** | CircuitPython is older than 10. Do the update in step 2. |
| **NOT SAVED** when changing a setting on the pad | The pad was started with the encoder held (drive visible), or `boot.py` is missing. Restart normally. Settings only save when the drive is hidden. |
| MACROPAD doesn't appear | Hold the encoder button while plugging in, and keep holding for 3 seconds. |
| Something else | Put your backup back on the drive (delete everything, copy the backup in) to return to the old firmware. |
