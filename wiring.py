# wiring.py – Pin configuration for YD-RP2040 macropad

import board

# Key matrix
ROWS = (board.GP22, board.GP21)
COLS = (board.GP26, board.GP27, board.GP28, board.GP29)

# Encoder
ENC_A  = board.GP8
ENC_B  = board.GP9
ENC_SW = board.GP10

# OLED (I2C)
I2C_SCL = board.GP15
I2C_SDA = board.GP14
OLED_ADDRESS = 0x3C
I2C_FREQUENCY = 400000     # 400 kHz (SSD1306 fast mode). Drop to 100000 if the screen glitches.

# Optional add-ons (enable in settings.js: "led_count" and "buzzer")
LED_STRIP_PIN = board.GP19   # NeoPixel (WS2812) strip data
BUZZER_PIN = board.GP17      # passive or active buzzer
# board.GP23 is the YD-RP2040's onboard NeoPixel (not used)
