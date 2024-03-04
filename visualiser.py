from ulab import numpy as np # https://github.com/v923z/micropython-builder/releases
import machine
from machine import Pin, SPI, I2S
import math, struct, sys, time
import mcauser_max7219 as max7219 # https://github.com/mcauser/micropython-max7219

mtx_id = 0
mtx_sck = Pin(2)
mtx_mosi = Pin(3)
mtx_miso = Pin(0) # unused
mtx_cs = Pin(1)

display_spi = SPI(id=mtx_id, baudrate=10_000_000, sck=mtx_sck, mosi=mtx_mosi, miso=mtx_miso)
display = max7219.Matrix8x8(display_spi, Pin(mtx_cs), 1)
display.brightness(10)

SAMPLE_RATE = 22050 # Hz (WLED is 22050)
SAMPLE_SIZE = 16 # bits
SAMPLE_COUNT = 512 # (WLED is 512)

SQUELCH = 1_500
UNPOWER, MINPEAK = lambda x: math.pow(x,1/2), None
if MINPEAK is None:
    MINPEAK = UNPOWER(SQUELCH) * 2 # heuristic, needs more testing
DECAY = 0.95

mic_id = 0
mic_sd = Pin(26)
mic_sck = Pin(27)
mic_ws = Pin(28)

rawsamples = bytearray(SAMPLE_COUNT * SAMPLE_SIZE // 8)

microphone = I2S(mic_id, sck=mic_sck, ws=mic_ws, sd=mic_sd, mode=I2S.RX,
                 bits=SAMPLE_SIZE, format=I2S.MONO, rate=SAMPLE_RATE,
                 ibuf=len(rawsamples)*2+1024)

if sys.platform == 'rp2':
    from machine import freq
    machine.freq(200_000_000)
    #machine.freq(125_000_000) # default



def flat_top_window(N):
    n = np.linspace(0, N, num=N)
    return 0.2810639 - (0.5208972 * np.cos(2 * math.pi * n/N)) + (0.1980399 * np.cos(4 * math.pi * n/N))

fft_window = flat_top_window(SAMPLE_COUNT) # as per WLED

_scale = [None if i is 0 else math.sqrt(i)/i for i in range(30)]

def mini_wled(samples):
    assert (len(samples) == SAMPLE_COUNT)
    
    re, im = np.fft.fft(samples * fft_window)
    
    magnitudes = np.sqrt(re*re + im*im)
    
    
    def sum_and_scale(m, f, t):
        return sum([m[i] for i in range(f,t+1)]) * _scale[t-f+1]
    
    fftCalc = [
        sum_and_scale(magnitudes,1,2), #  22 -   108 Hz
        sum_and_scale(magnitudes,3,4), #     -   194 Hz
        sum_and_scale(magnitudes,5,7), #     -   323 Hz
        sum_and_scale(magnitudes,8,11), #    -   495 Hz
        sum_and_scale(magnitudes,12,16), #   -   711 Hz
        sum_and_scale(magnitudes,17,23), #   -  1012 Hz
        sum_and_scale(magnitudes,24,33), #   -  1443 Hz
        sum_and_scale(magnitudes,34,46), #   -  2003 Hz
        
        sum_and_scale(magnitudes,47,62), #   -  2692 Hz
        sum_and_scale(magnitudes,63,81), #   -  3510 Hz
        sum_and_scale(magnitudes,82,103), #  -  4457 Hz
        sum_and_scale(magnitudes,104,127), # -  5491 Hz
        sum_and_scale(magnitudes,128,152), # -  6568 Hz
        sum_and_scale(magnitudes,153,178), # -  7687 Hz
        sum_and_scale(magnitudes,179,205), # -  8850 Hz
        sum_and_scale(magnitudes,206,232), # - 10013 Hz
    ]
    
    return fftCalc









class QuietTracker:
    number_of_channels = None
    silence_value = None
    history = None
    history_ptr = -1
    history_size = 10
    last_mix_ticks = None

    def __init__(self, number_of_channels, silence_value):
        self.number_of_channels = number_of_channels
        self.silence_value = silence_value
        self.history = []
        for i in range(number_of_channels):
            self.history.append([0.0] * self.history_size)

    def is_silence(self, channels):
        assert (len(channels) == self.number_of_channels)
        for i in range(self.number_of_channels):
            if channels[i] >= self.silence_value:
                return False
        return True

    def sample_hum(self, channels):
        assert (len(channels) == self.number_of_channels)
        t = time.ticks_ms()
        if self.last_mix_ticks is None or time.ticks_diff(t, self.last_mix_ticks) >= 1000:
            self.last_mix_ticks = t
            self.history_ptr = (self.history_ptr + 1) % self.history_size
            for i in range(self.number_of_channels):
                self.history[i][self.history_ptr] = channels[i]
        else:
            for i in range(self.number_of_channels):
                self.history[i][self.history_ptr] = max(self.history[i][self.history_ptr], channels[i])

    def remove_hum(self, channels):
        assert (len(channels) == self.number_of_channels)
        for i in range(self.number_of_channels):
            channels[i] = max(0, channels[i] - max(self.history[i]))



class PeaksTracker:

    minpeak = None
    p0 = None
    p1 = None
    p2 = None
    p3 = None
    _i = -1

    def __init__(self, minpeak):
        self.minpeak = minpeak

    def sample_peaks(self, channels):
        #
        # The first few readings from INMP441 microphones are atypical (auto-calibration?)
        # We want to avoid these values having a long-lasting impact on the 'peak' value
        #
        
        p = max(channels)
        
        self._i = self._i + 1
        
        if self._i >= 100:
            if self._i == 1100:
                self._i = 100
            self.p0 = p
            # three different low-pass filters, running in parallel
            self.p1 = 0.9 * self.p1 + 0.1 * p
            self.p2 = 0.99 * self.p2 + 0.01 * p
            self.p3 = 0.999 * self.p3 + 0.001 * p
        elif self._i >= 10:
            self.p0 = p
            self.p1 = 0.9 * self.p1 + 0.1 * p
            self.p2 = 0.99 * self.p2 + 0.01 * p
            self.p3 = self.p2
        elif self._i >= 1:
            self.p0 = p
            self.p1 = 0.9 * self.p1 + 0.1 * p
            self.p2 = self.p1
            self.p3 = self.p2
        else:
            self.p0 = p
            self.p1 = self.p0
            self.p2 = self.p1
            self.p3 = self.p2

    def scaled(self, channels):
        m = max(1, self.minpeak) + max(0, (self.p0 + self.p1 + self.p2 + self.p3 - self.minpeak) / 3)
        return [max(0.0, min(1.0, channels[i] / m)) for i in range(len(channels))]



noise = QuietTracker(16, SQUELCH)
peaks = PeaksTracker(MINPEAK)

levels = [0] * 16
loop, t0 = 0, time.ticks_ms()
try:
    while True:
        loop = (loop + 1) % 100
        if loop == 0:
            t1 = time.ticks_ms()
            t0 = t1
        
        num_bytes_read = microphone.readinto(rawsamples)
        assert (num_bytes_read == len(rawsamples))
        
        if SAMPLE_SIZE == 8:
            samples = np.frombuffer(rawsamples, dtype=np.int8)
        elif SAMPLE_SIZE == 16:
            samples = np.frombuffer(rawsamples, dtype=np.int16)
        else:
            raise NotImplementedError
        
        # calculate channels from samples
        channels = mini_wled(samples)
        
        if noise.is_silence(channels):
            noise.sample_hum(channels)
            for i in range(len(channels)):
                levels[i] *= DECAY
        else:
            noise.remove_hum(channels)
            channels = [UNPOWER(channels[i]) if channels[i] >= 1 else 0 for i in range(len(channels))]
            peaks.sample_peaks(channels)
            levels = peaks.scaled(channels)
        
        for ch in range(8): # we have 16 channels of data, but only display the lower 8
            for lv in range(8):
                if levels[ch] > (lv + 0.5) / (8 + 0.5):
                    display.pixel(7-ch,lv,1)
                else:
                    display.pixel(7-ch,lv,0)
        display.show()
        
        del channels

except Exception as e:
    sys.print_exception(e)
finally:
    try:
        microphone.deinit()
    except: pass
    try:
        display.fill(0)
        display.show()
    except: pass
