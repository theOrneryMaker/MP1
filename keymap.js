// MP1 macropad keymap. Edit with keymap_configurator.html (the JSON inside is the same as keymap.json).
var MP1_KEYMAP = {
  "version": 2,
  "layers": [
    {
      "name": "MEDIA",
      "default": true,
      "keys": [
        {"icon": "PREV", "media": "PREV"},
        {"icon": "PLAY", "media": "PLAYPAUSE"},
        {"icon": "NEXT", "media": "NEXT"},
        {"icon": "MUTE", "media": "MUTE"},
        {"icon": "STOP", "media": "STOP"},
        {"icon": "VOL-", "media": "VOL_DN", "repeat": true},
        {"icon": "VOL+", "media": "VOL_UP", "repeat": true},
        null
      ],
      "encoder": {"icon": "VOL", "cw": {"media": "VOL_UP"}, "ccw": {"media": "VOL_DN"}, "accel": true}
    },
    {
      "name": "EDIT",
      "keys": [
        {"icon": "CUT", "combo": ["CONTROL", "X"]},
        {"icon": "COPY", "combo": ["CONTROL", "C"]},
        {"icon": "PSTE", "combo": ["CONTROL", "V"]},
        {"icon": "ALL", "combo": ["CONTROL", "A"]},
        {"icon": "UNDO", "combo": ["CONTROL", "Z"]},
        {"icon": "REDO", "combo": ["CONTROL", "Y"]},
        {"icon": "FIND", "combo": ["CONTROL", "F"]},
        {"icon": "SAVE", "combo": ["CONTROL", "S"]}
      ],
      "encoder": {"icon": "UNDO", "cw": {"combo": ["CONTROL", "Y"]}, "ccw": {"combo": ["CONTROL", "Z"]}}
    },
    {
      "name": "NAV",
      "keys": [
        {"icon": "HOME", "key": "HOME"},
        {"icon": "UP", "key": "UP_ARROW"},
        {"icon": "END", "key": "END"},
        {"icon": "PGUP", "key": "PAGE_UP"},
        {"icon": "LEFT", "key": "LEFT_ARROW"},
        {"icon": "DOWN", "key": "DOWN_ARROW"},
        {"icon": "RGHT", "key": "RIGHT_ARROW"},
        {"icon": "PGDN", "key": "PAGE_DOWN"}
      ],
      "encoder": {"icon": "SCRL", "cw": {"scroll": -1}, "ccw": {"scroll": 1}, "accel": true}
    },
    {
      "name": "BROWSER",
      "keys": [
        {"icon": "BACK", "combo": ["ALT", "LEFT_ARROW"]},
        {"icon": "FWD", "combo": ["ALT", "RIGHT_ARROW"]},
        {"icon": "RLD", "key": "F5"},
        {"icon": "HOME", "combo": ["ALT", "HOME"]},
        {"icon": "NEW", "combo": ["CONTROL", "T"]},
        {"icon": "CLOS", "combo": ["CONTROL", "W"]},
        {"icon": "REOP", "combo": ["CONTROL", "SHIFT", "T"]},
        {"icon": "FIND", "combo": ["CONTROL", "F"]}
      ],
      "encoder": {"icon": "TABS", "cw": {"combo": ["CONTROL", "TAB"]}, "ccw": {"combo": ["CONTROL", "SHIFT", "TAB"]}}
    },
    {
      "name": "WINDOWS",
      "keys": [
        {"icon": "SN L", "combo": ["WINDOWS", "LEFT_ARROW"]},
        {"icon": "MAX", "combo": ["WINDOWS", "UP_ARROW"]},
        {"icon": "SN R", "combo": ["WINDOWS", "RIGHT_ARROW"]},
        {"icon": "TASK", "combo": ["WINDOWS", "TAB"]},
        {"icon": "MIN", "combo": ["WINDOWS", "DOWN_ARROW"]},
        {"icon": "EXPL", "combo": ["WINDOWS", "E"]},
        {"icon": "SHOT", "combo": ["WINDOWS", "SHIFT", "S"]},
        {"icon": "LOCK", "combo": ["WINDOWS", "L"]}
      ],
      "encoder": {
        "icon": "DESK",
        "cw": {"combo": ["CONTROL", "WINDOWS", "RIGHT_ARROW"]},
        "ccw": {"combo": ["CONTROL", "WINDOWS", "LEFT_ARROW"]}
      }
    },
    {
      "name": "PRESENT",
      "keys": [
        {"icon": "STRT", "key": "F5"},
        {"icon": "HERE", "combo": ["SHIFT", "F5"]},
        {"icon": "BLK", "key": "B"},
        {"icon": "WHT", "key": "W"},
        {"icon": "PREV", "key": "LEFT_ARROW"},
        {"icon": "NEXT", "key": "RIGHT_ARROW"},
        {"icon": "FRST", "key": "HOME"},
        {"icon": "END", "key": "ESCAPE"}
      ],
      "encoder": {"icon": "SLDE", "cw": {"key": "RIGHT_ARROW"}, "ccw": {"key": "LEFT_ARROW"}}
    }
  ]
};
