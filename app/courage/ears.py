"""The ears: listens on the microphone, cuts out each thing you say, turns it into text (offline, Whisper)."""
import os
import queue
import threading
import time

import numpy as np

RATE = 16000
BLOCK = 480  # 30 ms


class Ears:
    def __init__(self, model_dir, on_text, on_level=None):
        self.model_dir = model_dir
        self.on_text = on_text
        self.on_level = on_level or (lambda lvl, speaking: None)
        self.muted = threading.Event()
        self.q = queue.Queue()
        self.model = None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _load(self):
        from faster_whisper import WhisperModel
        threads = max(1, (os.cpu_count() or 2) - 1)
        self.model = WhisperModel(self.model_dir, device="cpu", compute_type="int8", cpu_threads=threads)

    def _run(self):
        import sounddevice as sd
        self._load()
        while True:
            try:
                with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK,
                                    callback=lambda d, f, t, s: self.q.put(d.copy())):
                    self._loop()
            except Exception as e:  # mic unplugged / not ready yet
                print("mic error:", e, flush=True)
                time.sleep(3)

    def _loop(self):
        noise = 0.004
        speech, silent, talking = [], 0, False
        last_level = 0
        while True:
            block = self.q.get()[:, 0]
            if self.muted.is_set():
                speech, silent, talking = [], 0, False
                continue
            level = float(np.sqrt(np.mean(block ** 2)))
            if not talking:
                noise = 0.97 * noise + 0.03 * level
            loud = level > max(noise * 3.0, 0.01)
            now = time.time()
            if now - last_level > 0.1:
                self.on_level(min(1.0, level * 20), talking)
                last_level = now
            if loud:
                talking = True
                silent = 0
                speech.append(block)
            elif talking:
                speech.append(block)
                silent += 1
                if silent > 27:  # ~0.8 s of quiet = finished
                    audio = np.concatenate(speech)
                    speech, silent, talking = [], 0, False
                    if len(audio) > RATE * 0.4:
                        self._transcribe(audio)

    def _transcribe(self, audio):
        segs, _ = self.model.transcribe(audio, language="en", beam_size=1, vad_filter=False)
        text = " ".join(s.text for s in segs).strip()
        junk = {"", "you", "thank you.", "thanks for watching!", "."}
        if text.lower() not in junk:
            self.on_text(text)
