# Changes

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
