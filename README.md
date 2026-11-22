# MP1 Ember

Firmware, a web page and an Android app for the **MP1**, a homemade macropad: 8 keys, an encoder with a push
button, a 128 x 64 OLED screen, and (optionally) LEDs and a buzzer, on a **YD-RP2040** board running CircuitPython.

Ember was built for office work: typing long, repetitive orders and forms, sharing those macros with coworkers,
and keeping the everyday shortcuts one press away.

**Website (the page, the phone app, the firmware):** https://theornerymaker.github.io/MP_Series_Macropad/ember/

## What it does

- **8 keys per layer, up to 24 layers.** Each key: keys or a key combination, text, a macro (several steps, with
  waits), media keys, opening a program or web address, going to a layer, a pad function, the mouse, a number that
  counts up, or today's date / time. Labels and pictures (icons drawn into pad pixels) show on the screen.
- **Macros from a spreadsheet.** Write an order in a .csv (one column per field, the keys between fields in the
  header) and drop it on a key. `{TAB 2}`, `{ENTER}`, `{WAIT 0.5}`, `{F7 49 0.2}`, `{DATE MM/DD/YYYY +180}`,
  `{NEXT LINE}`, `{ROW}`, `{PAUSE Check the total}`, `{DATE +10 workdays}`, a `{FOOTER}` row and `#` comment rows.
  A running macro shows its progress ("Row 37 of 80"); click the encoder to pause it, any key or a turn stops it.
  Typing speed (Normal / Careful / Slow) for websites that drop characters, for the pad or one key.
- **Sharing.** Copy a key or a whole layer as text (paste it into a chat or an email), save it as a file, load it
  on another pad, from the page or the phone.
- **The encoder:** a turn per layer (volume, scroll, ...), clicks and hold + turn for pad functions, HOLD+KEY: eight
  more keys while the encoder is held.
- **Layer picker, layer keys and layer cards** (one big card a layer, readable at arm's length).
- **Secret pages:** up to four pages of keys kept encrypted to the pad's chip, never listed or shown in the page; an
  optional PIN (a pattern on the pad's keys) encrypts them with the chip and the PIN together.
- **Starter layers:** Excel navigation, Windows, meetings (Webex / Teams), media and the pad's own tools, one click each.
- **Timer / stopwatch** (with focus cycles), **counter**, **busy light**, **reminders**, and a **bouncing clock**
  screensaver, all on the pad.
- **Spotify screen:** what's playing, play / pause / skip / shuffle / repeat / like / volume (with Spotify Premium).
- **Lights and sound:** scenes for the LEDs, beeps for start-up, layers, key clicks and alarms (each on or off).

## The parts

| | |
|---|---|
| **The pad** | `EMBER_01/lib/ember/`: the program, frozen into a custom CircuitPython build (`tools/cpbuild/`). `boot.py` and `code.py` go on the pad's drive. |
| **The page** | `MP1 Ember.html`: one file, no install. Open it in Chrome or Edge (it talks to the pad over USB with Web Serial). Every pad carries a copy on its drive, so it works without the internet. Built from `EMBER_01/app/` by `tools/make_page.py`. |
| **The phone app** | `phone_app/`: an Android app (the phone page in a WebView, with USB underneath). It updates any MP1 to Ember in one go (from any older firmware, keeping the keymap, secret layers, settings and wiring) and shares layers and keys. |

## Putting Ember on a pad

**With the phone app** (easiest, works from any firmware): install `MP1.apk` (from the website or the Releases),
plug the pad into the phone, **Check the pad**, then **Wipe and update**. It saves a backup to the phone first.

**By hand from a computer:**
1. Hold the board's BOOT button while plugging it in: a drive called RPI-RP2 appears. Copy
   `mp1_ember_yd_rp2040.uf2` onto it. The pad restarts.
2. Copy `boot.py`, `code.py` and `MP1 Ember.html` onto the pad's drive (from the update package in the Releases).
   To see the drive, hold the encoder button while plugging the pad in.
3. Open `MP1 Ember.html` in Chrome or Edge and **Connect**. A pad with an older keymap gets **Convert it**.

## Building it yourself

- The page: `py tools/make_page.py` (also writes the phone page), then `py tools/make_package.py` for the update package.
- The firmware: in WSL Ubuntu 24.04, run `tools/cpbuild/setup.sh` once, then `tools/cpbuild/build.sh EMBER_01`.
- The phone app: `phone_app/build.sh` (WSL, Android SDK; see the top of the script).
- Tests that run on a computer: `tools/dev/tests/sim_*.py` (the pad's code with stand-ins for the screen) and
  `phone_image.mjs` (the phone's full update, end to end).

## Wiring

The standard pins (YD-RP2040): key rows GP22, GP21; columns GP26-GP29; encoder GP8 / GP9, button GP10; OLED on I2C
GP14 (SDA) / GP15 (SCL); LEDs GP19; buzzer GP17. A hand-wired pad can differ: `wiring.json` on its drive says which
pins it uses.

## License

MIT (see `LICENSE`). Other people's parts keep their own licenses: see `THIRD_PARTY.md`. The PCB and 3D-printed case
files aren't published yet.

The original MP1 firmware (before Ember) is kept in this repository as the `firmware-00` tag.
