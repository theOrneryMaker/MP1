# Other people's work in MP1 Ember

MP1 Ember's own code is under the MIT license (see LICENSE). These parts come from others and keep their own
licenses:

| Part | Where | License |
|---|---|---|
| CircuitPython | the firmware the pad runs (`tools/cpbuild` builds it) | MIT |
| Adafruit HID, NeoPixel and SSD1306 display libraries | frozen into the firmware by `tools/cpbuild/build.sh` | MIT |
| Terminus font | the pad's font (`EMBER_01/lib/ember/font.py`, made by `tools/make_font.py` from `tools/keyfont/ter-u12n.bdf`) | SIL Open Font License 1.1 (`tools/keyfont/OFL.TXT`) |
| usb-serial-for-android | the phone app's USB serial (downloaded by Gradle) | MIT |
| Font Awesome Free icons | loaded by the page from the internet when you pick an icon | icons CC BY 4.0, fonts SIL OFL 1.1, code MIT |
| Remix Icon | loaded from the internet | Apache 2.0 |
| Simple Icons | loaded from the internet | CC0 1.0 |
| Material Symbols | loaded from the internet | Apache 2.0 |

Brand icons (Spotify, YouTube, ...) are their owners' trademarks, used only to label keys.
