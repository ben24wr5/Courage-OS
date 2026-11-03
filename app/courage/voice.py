"""The voice: reads answers out loud in a British voice (offline, Piper). Falls back to espeak-ng."""
import os
import subprocess
import sys
import tempfile
import threading


class Voice:
    def __init__(self, voice_model, ears=None):
        self.model = voice_model
        self.ears = ears
        self.lock = threading.Lock()
        self.proc = None

    def say(self, text, done=None):
        threading.Thread(target=self._say, args=(text, done), daemon=True).start()

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def _say(self, text, done):
        with self.lock:
            if self.ears:
                self.ears.muted.set()
            try:
                wav = tempfile.mktemp(suffix=".wav")
                ok = False
                if os.path.exists(self.model):
                    r = subprocess.run([sys.executable, "-m", "piper", "-m", self.model, "-f", wav],
                                       input=text.encode(), capture_output=True, timeout=60)
                    ok = r.returncode == 0 and os.path.exists(wav)
                if not ok:
                    subprocess.run(["espeak-ng", "-v", "en-gb", "-w", wav, text], timeout=60)
                play = wav
                robot = wav + ".robot.wav"
                # AI computer sound: a bit deeper, with a light metallic shimmer, no echo
                r2 = subprocess.run(["sox", wav, robot, "pitch", "-120", "flanger", "2", "1", "0", "30", "0.6", "sin",
                                     "gain", "-n", "-1"], capture_output=True, timeout=30)
                if r2.returncode == 0 and os.path.exists(robot):
                    play = robot
                self.proc = subprocess.Popen(["pw-play", play])
                self.proc.wait()
            except Exception as e:
                print("voice error:", e, flush=True)
            finally:
                for f in (wav, wav + ".robot.wav"):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
                if self.ears:
                    self.ears.muted.clear()
                if done:
                    done()
