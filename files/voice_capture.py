"""Local continuous voice turns for the shared native chat."""
from lumen_i18n import worker_process, tr
from array import array
from collections import deque
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import wave


def pcm_rms(frame):
    samples = array('h', frame)
    if sys.byteorder != 'little': samples.byteswap()
    return math.sqrt(sum(v * v for v in samples) / max(1, len(samples)))


def normalized_level(rms):
    return min(1., math.sqrt(rms / 10000))


class Utterance:
    """PCM16 frame detector, with configurable threshold/pause for real microphones."""
    def __init__(self, threshold=450, silence=.9):
        self.threshold = threshold; self.silence = silence; self.frames = []; self.pre = deque(maxlen=10)
        self.voiced = 0; self.quiet = 0; self.started = False

    def feed(self, frame):
        rms = pcm_rms(frame); self.level = normalized_level(rms)
        duration = len(frame) / 32000
        if rms >= self.threshold:
            if not self.started: self.frames.extend(self.pre); self.started = True
            self.voiced += duration; self.quiet = 0
        else: self.quiet += duration
        if self.started: self.frames.append(frame)
        else: self.pre.append(frame)
        if self.started and self.quiet >= self.silence:
            if self.voiced >= .25: return True
            self.frames.clear(); self.started = False; self.voiced = 0
        return sum(map(len, self.frames)) >= 16000 * 2 * 45


def record(path, threshold, silence):
    detector = Utterance(threshold, silence)
    child = subprocess.Popen(['pw-cat', '--record', '--raw', '--rate', '16000', '--channels', '1', '--format', 's16',
                              '--properties', '{ media.role = Communication node.name = lumen-voice }', '-'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    def stop(*_): raise InterruptedError()
    signal.signal(signal.SIGTERM, stop)
    try:
        started = time.monotonic(); last_level = 0.
        while time.monotonic() - started < 180:
            frame = child.stdout.read(640)
            if not frame: raise ValueError(tr('Mikrofon liefert keine Audiodaten.'))
            finished = detector.feed(frame)
            if time.monotonic() - last_level >= .05:
                print(f'LEVEL {detector.level:.4f}', flush=True); last_level = time.monotonic()
            if finished:
                with wave.open(path, 'wb') as out:
                    out.setnchannels(1); out.setsampwidth(2); out.setframerate(16000); out.writeframes(b''.join(detector.frames))
                return
        raise ValueError(tr('Drei Minuten keine Sprache erkannt. Mikrofon wurde ausgeschaltet.'))
    finally:
        child.terminate()
        try: child.wait(timeout=3)
        except subprocess.TimeoutExpired: child.kill(); child.wait()


if __name__ == '__main__':
    try: record(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]))
    except Exception as error: print(str(error), file=sys.stderr); sys.exit(1)
