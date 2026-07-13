"""
Voice recording via `arecord` (ALSA's command-line recorder) -- the
same tool you'd use by hand over SSH. A microphone is optional
peripheral hardware, like the camera, so this reports `.available`
rather than raising if arecord or a mic isn't present.

Recording is start/stop driven (indefinite duration, not a fixed clip
length), so it runs as a background subprocess: start() launches
arecord and returns immediately, stop() sends it a graceful interrupt
so it finalizes the WAV header properly instead of leaving a truncated
file, and returns the path that was being recorded to.
"""

import shutil
import signal
import subprocess
import time


def _have(cmd):
    return shutil.which(cmd) is not None


class AudioRecorder:
    def __init__(self):
        self.available = _have("arecord")
        self._proc = None
        self._path = None
        self._start_time = None

    def start(self, path):
        if not self.available or self._proc is not None:
            return False
        try:
            self._proc = subprocess.Popen(
                ["arecord", "-f", "cd", "-t", "wav", path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._path = path
            self._start_time = time.time()
            return True
        except Exception:
            self._proc = None
            return False

    def is_recording(self):
        return self._proc is not None and self._proc.poll() is None

    def elapsed(self):
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    def stop(self):
        """Stops recording (if active) and returns the file path that
        was being written to, or None if nothing was recording."""
        if self._proc is None:
            return None
        path = self._path
        try:
            self._proc.send_signal(signal.SIGINT)
            self._proc.wait(timeout=5)
        except Exception:
            try:
                self._proc.terminate()
            except Exception:
                pass
        self._proc = None
        self._path = None
        self._start_time = None
        return path
