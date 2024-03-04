# micropython-spectrum-analyzer-demo
MicroPython audio spectrum analyzer for an I2S (INMP441) microphone and 8x8 (MAX7219) LED array

Created because I wanted something sound-reactive like WLED, but for more platforms (such as the Raspberry Pi Pico and ESP32-C3), and based on MicroPython for ease of development. The code can handle around 30 "frames" a second on an RP2040 with moderate over-clocking, no threads required.

Requires [a build of MicroPython with ulab](https://github.com/v923z/micropython-builder/releases) for the heavy lifting.

This initial release is under-documented, but fully functional, and includes automatic background hum removal and automatic scaling.

The input device is an I2S microphone (I developed against an INMP441 clone from AliExpress), but could be adapted for an analog module if you implement threading (or are happier with a lower "frame" rate and responsiveness).

The output device is an 8x8 MAX7219 matrix, but could be adapted easily for WS2812 LEDs or whatever you prefer.
