# Changes

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
