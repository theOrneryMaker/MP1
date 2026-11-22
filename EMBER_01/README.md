# EMBER_01

The first Ember release.

- `boot.py`, `code.py`: go on the pad's drive (code.py starts the frozen program, `ember.app`).
- `lib/ember/`: the pad program (frozen into the firmware by `tools/cpbuild/build.sh`). Start with `app.py`;
  `keymap.py` documents the keymap format at the top.
- `app/`: the page (`ember.html`) and the phone page (`phone.html`), made of the pieces in `app/parts/`;
  `tools/make_page.py` joins them into `BUILD_PAGES/`.
- `examples/`: example .csv macros (a material order, repeated forms, a form in two parts).

Build output (`BUILD_PAGES/`, `BUILD_FROZEN/`) isn't kept in the repository: get it from the Releases.
