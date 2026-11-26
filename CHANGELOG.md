# Changes

## Ember 01.4 (2026-11-26)

- An **Update** tab in MP1 Ember, on a computer and in the phone app: update a pad from any MP1 firmware in one go
  (backup first, keymap and settings converted). On a computer (Chrome or Edge) the page asks for the pad's port, then
  for its RPI-RP2 drive, or saves the two files for you to drag onto it. It can also finish from a backup if an update
  stopped halfway.
- Pick the release: the newest is chosen, older ones (to go back if something breaks) and your own package file can be
  picked, with a warning and an "I understand" tick.
- The pad reports its release number, so the page and the app can tell when a newer Ember is out.
- Phone app 1.4: shows this website's MP1 Ember page (keys, settings, files and updates in one), with a copy built in
  for when it's offline; checks for new Ember releases once a day and lets you know; a new icon.
- The page fits a phone screen.
- Help: "Updating the pad".
- Released before testing on a real pad (the user's choice); fixes follow as patches.

## Ember 01.3 (2026-11-25)

- The pad starts and runs without waiting for the computer: plugged into a sleeping or undocked laptop it no longer
  hangs at start-up, and key presses while the computer sleeps are dropped instead of freezing the pad.
- A watchdog: if the pad ever locks up, it restarts itself after 8 seconds.
- A hand-wired pad with more or fewer lights: `"led_count": N` (0-60) in settings.json overrides the 4 LEDs (see Help).
- Help: the CSV guide rewritten, with a quick start.
- Build script: an optional Raspberry Pi Pico 2 (RP2350) target, for testing.

## Ember 01.2 (2026-11-23)

- Running macros: **hold the encoder (1 s) to stop**; a click pauses; keys and turns do nothing while a macro runs. While
  paused, turn the encoder to pick the CSV row to go on from (back or ahead), then click.
- Macro steps: a **then wait** time per step (after each press when it repeats); CSV `{F7 49 0.2}` is now one step.
- CSV: `{CLICK}`, `{RIGHTCLICK}`, `{MIDDLECLICK}`, `{DOUBLECLICK}` (where the pointer is).
- Hold-to-confirm keys: a corner mark, and a bar that fills while held.
- Mouse jiggle: a blinking dot on the top row while it's on.
- Encoder presets in the layer settings (volume, scroll, zoom, tracks, tabs, undo, arrows, pages, brightness, mouse).
- Layer files copied into the pad's `layers` folder are loaded too; the page warns while the pad's drive is showing
  (the pad can't save then).
- Open keys: web addresses and app links open through the page again (allow pop-ups once); the clock is re-sent hourly.
- Phone app 1.3.

## Ember 01.1 (2026-11-22)

- Running macros: a progress screen ("Row 37 of 80" for CSV macros); click the encoder to pause, click again to go on
  (any key or a turn still stops).
- Typing speed: Normal / Careful / Slow, for the pad (Settings) or one key.
- CSV: `{ROW}`, `{PAUSE note}`, `{FOOTER}` rows (once, at the end), `#` comment rows, workdays (`{DATE +10 workdays}`).
- Secret pages: an optional PIN, set as a pattern on the page's drawing of the pad's keys or on the pad itself; asked
  once after the pad is plugged in; the pages are encrypted with the chip and the PIN together. The pad now says why if
  its secret pages didn't load, and the page offers to reload them.
- Starter layers: Excel navigation, Windows, meetings, media, the pad's tools.
- The bouncing clock: a "When idle" setting (Dim or Bouncing clock).
- Help: the CSV guide is folded away under Macros.
- Phone app 1.2.

## Ember 01 (2026-11-21)

The first Ember release: a rework of the MP1 firmware and its tools from the ground up.

- New pad program, frozen into a custom CircuitPython 10.3.2 build (much more free memory), new screen design
  (Terminus font, key pictures in pad pixels), one simple keymap format (a file per layer).
- One page, `MP1 Ember.html`: edit keys and layers live, settings, files, the player, Spotify, help. Converts any
  older MP1 keymap.
- Macros from a .csv, with sections for forms in two parts, waits, repeats and gaps; macro stop.
- Sharing keys and layers as text or files.
- Secret pages (up to 4, encrypted to the pad's chip), layer cards, HOLD+KEY (black on white).
- Spotify screen; timer / stopwatch with focus cycles; counter and Number keys; date / time keys (with days from
  today); busy light; reminders; sounds as Boot / Layers / Keys / Alarms switches.
- Phone app 1.1: updates any MP1 to Ember in one go and shares layers and keys.
