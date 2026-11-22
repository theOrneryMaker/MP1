# boot.py – runs once at power-up, before code.py.
# Hold the encoder button while plugging the macropad in (and for ~3 seconds) to show the
# MP1 drive, e.g. to copy files or edit them from a computer. Otherwise the drive
# stays hidden, which lets the macropad save its own settings (settings.json).
#
# The screen shows Boot/startup.bmp straight away (instead of staying dark while this waits),
# and code.py replaces it with Boot/boot.bmp when it starts. The screen keeps the picture in
# between. If anything about the screen fails, it just stays dark: the drive check carries on.
#
# The pins come from wiring.json ("encoder_button", "i2c_sda", "i2c_scl", "oled_address"), so
# hand-wired pads work too; an older wiring.py is used for the button if there's no
# wiring.json, and the standard MP1 pins if neither can be read.

import time
import board
import digitalio
import storage

WAIT_SECONDS = 3
HELD_READS = 3              # the button must read pressed this many times in a row (0.1 s apart):
                            # a blip at power-up or after a firmware flash doesn't show the drive
# TOOLS > SETTINGS > DRIVE asks for the drive at the next start with b"MP1D" in the chip's memory
# (NVM, near the end); this start answers with b"MP1R" (the restart was ours, not the watchdog's)
DRIVE_SLOT = 8              # bytes from the end of the NVM
STARTUP_IMAGE = "/Boot/startup.bmp"
# The default start-up image, shown when Boot/startup.bmp is missing or can't be read (1024 bytes:
# 128 x 64, 1 bit a pixel, rows top to bottom, the leftmost pixel in the top bit)
STARTUP_FALLBACK = (
    "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000000000000000000ff80ff83ffe0000000003ffc03ffc000ffc1ff83fff800000"
    "0007ffe07ffe000ffc1ff83fffc00000000ffff0c003000ffc1ff83fffc00000000ffff0c003000ffc1ff83fffe00000"
    "000ffff0c003000ffe1ff83f0fe00000000ffff0c003000ffe3ff83f07e00000000ffff0c003000ffe3df83f07e00000"
    "000ffff0c003000fde3df83f07e00000000ffff0c003000fdf3df83f0fe00000000ffff0c003000fdf7df83fffc00000"
    "000ffff0c003000fdf7df83fffc1c000000ffff0c003000fcf79f83fff87c000000ffff0c003000fcff9f83fff07c000"
    "000ffff0c003000fcff9f83ff807c0000007ffe07ffe000fcff9f83f0001c0000003ffc03ffc000fc7f1f83f0001c000"
    "000000000000000fc7f1f83f0001c000000000000000000fc7f1f83f0001c000000000000000000fc7f1f83f0001c000"
    "000000000000000fc3e1f83f0001c0000003ffc03ffc000000000000000000000007ffe07ffe00000000000000000000"
    "000c0030ffff00000000000000000000000c0030ffff00000000000000000000000c0030ffff003fffffffffffffc000"
    "000c0030ffff00000000000000000000000c0030ffff00000000000000000000000c0030ffff00000000000000000000"
    "000c0030ffff00000000000000000000000c0030ffff0089c83c03e89c73cfbc000c0030ffff008a2822020ca28a2822"
    "000c0030ffff008a2822020aa08a2822000c0030ffff00fa282203c9a08a2f3c000c0030ffff008a28220208a08a2828"
    "0007ffe07ffe008a28220208a28a28240003ffc03ffc0089cfbc03e89c73cfa200000000000000000000000000000000"
    "000000000000000000000000000000000000000000000000000000000000000000000000000000007ce78079e3917c00"
    "0000000000000000411440451111400000000000000000004114404511114000000000000000000079178045e1117800"
    "00000000000000004115004541114000000000000000000041148045210a4000000000000000000040e4407913847c00"
    "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    "00000000000000000000000000000000")  # (tools/embed_boot_images.py)


def built_in_image(hexed):
    """A 128 x 64 picture from the bytes above: (bitmap, palette)."""
    import displayio
    data = bytes.fromhex(hexed)
    bitmap = displayio.Bitmap(128, 64, 2)
    for y in range(64):
        row = y * 16
        for x in range(128):
            if data[row + (x >> 3)] & (0x80 >> (x & 7)):
                bitmap[x, y] = 1
    palette = displayio.Palette(2)
    palette[0] = 0x000000
    palette[1] = 0xFFFFFF
    return bitmap, palette


def wiring():
    """wiring.json as a dict ({} if missing or unreadable)."""
    try:
        import json
        with open("/wiring.json") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def board_pin(name, default):
    name = str(name or default).strip().upper()
    if name.startswith("BOARD."):
        name = name[6:]
    return getattr(board, name)


def button_pin(pins):
    if "encoder_button" in pins:
        try:
            return board_pin(pins["encoder_button"], "GP10")
        except Exception:
            pass
    try:
        import wiring as old    # older firmware kept the pins in wiring.py
        return old.ENC_SW
    except Exception:
        return board.GP10


def show_startup_image(pins):
    """Boot/startup.bmp on the OLED. Returns the display (keep it while waiting), or None."""
    try:
        import busio
        import displayio
        from i2cdisplaybus import I2CDisplayBus
        from adafruit_displayio_ssd1306 import SSD1306
        displayio.release_displays()
        address = pins.get("oled_address", 0x3C)
        if isinstance(address, str):
            address = int(address, 16)
        i2c = busio.I2C(board_pin(pins.get("i2c_scl"), "GP15"), board_pin(pins.get("i2c_sda"), "GP14"),
                        frequency=int(pins.get("i2c_frequency", 400000)))
        display = SSD1306(I2CDisplayBus(i2c, device_address=address), width=128, height=64)
        group = displayio.Group()
        try:
            image = displayio.OnDiskBitmap(STARTUP_IMAGE)
            group.append(displayio.TileGrid(image, pixel_shader=image.pixel_shader,
                                            x=(128 - image.width) // 2, y=(64 - image.height) // 2))
        except Exception as e:      # missing / not a BMP: the default, built in
            print("Start-up image: the built-in one ({})".format(e))
            bitmap, palette = built_in_image(STARTUP_FALLBACK)
            group.append(displayio.TileGrid(bitmap, pixel_shader=palette))
        display.root_group = group
        return display
    except Exception as e:          # no screen, other pins, missing image: carry on without it
        print("Start-up image not shown:", e)
        return None


pins = wiring()
display = show_startup_image(pins)     # (kept in a variable so it stays up while waiting)

# A second USB serial channel for MP1 Link (mp1_link.html, the mini window): the serial console
# stays exactly as it was, so Mu / the workbench console and the link never get in each other's
# way. Takes effect after the macropad is unplugged and plugged back in.
try:
    import usb_cdc
    usb_cdc.enable(console=True, data=True)
except Exception as e:
    print("MP1 Link channel not available:", e)

try:
    button = digitalio.DigitalInOut(button_pin(pins))
except Exception:
    button = digitalio.DigitalInOut(board.GP10)
button.switch_to_input(pull=digitalio.Pull.UP)

pressed = False
asked = False
try:
    import microcontroller
    nvm = microcontroller.nvm
    at = len(nvm) - DRIVE_SLOT
    asked = bytes(nvm[at:at + 4]) == b"MP1D"
    if asked:
        nvm[at:at + 4] = b"MP1R"
except Exception:
    pass
start = time.monotonic()
held = 0
while not asked and time.monotonic() - start < WAIT_SECONDS:
    held = held + 1 if not button.value else 0      # pressed = pulled to ground
    if held >= HELD_READS:
        pressed = True
        break
    time.sleep(0.1)
button.deinit()
pressed = pressed or asked

if pressed:
    print("MP1 drive shown ({}; settings can't be saved this time).".format("TOOLS > SETTINGS > DRIVE" if asked else "encoder button held"))
else:
    print("MP1 drive hidden (hold the encoder button at power-up to show it).")
    storage.disable_usb_drive()
