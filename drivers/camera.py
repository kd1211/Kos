"""
Camera support for the Raspberry Pi Camera Module, via picamera2 (the
current libcamera-based stack -- the older `picamera` library doesn't
work on modern Raspberry Pi OS / Bookworm+).

Unlike the LCD, touchscreen, and battery monitor the rest of this OS
assumes are always present (see main.py -- it doesn't even try/except
around those), a camera is genuinely optional peripheral hardware: the
board it's screwed into might not have one attached at all, or
picamera2 might not be installed. So this driver is instantiated
lazily by the Camera app itself (not at OS boot), and everything here
degrades to `.available = False` rather than raising -- checked with
`Camera().available` after construction, same shape as ui/net_control's
`.available` flags for Wi-Fi/Bluetooth.
"""

import time

try:
    from picamera2 import Picamera2
    _HAVE_PICAMERA2 = True
except Exception:
    _HAVE_PICAMERA2 = False


class Camera:
    def __init__(self, preview_size=(320, 320)):
        self.available = False
        self._cam = None
        self._preview_size = preview_size

        if not _HAVE_PICAMERA2:
            return
        try:
            self._cam = Picamera2()
            config = self._cam.create_preview_configuration(
                main={"size": preview_size, "format": "RGB888"})
            self._cam.configure(config)
            self._cam.start()
            time.sleep(0.3)  # let auto-exposure/white-balance settle before
                              # the first frame, matching picamera2's own examples
            self.available = True
        except Exception:
            self._cam = None
            self.available = False

    def capture_preview_array(self):
        """An (h, w, 3) RGB numpy array for the live viewfinder, or None
        if the camera isn't available or a frame couldn't be grabbed."""
        if not self.available:
            return None
        try:
            return self._cam.capture_array()
        except Exception:
            return None

    def capture_still(self, path):
        """Saves a full-resolution photo to `path`. Returns True/False
        rather than raising, so the app can just show a status message."""
        if not self.available:
            return False
        try:
            self._cam.capture_file(path)
            return True
        except Exception:
            return False

    def close(self):
        if self._cam is not None:
            try:
                self._cam.stop()
                self._cam.close()
            except Exception:
                pass
        self._cam = None
        self.available = False
