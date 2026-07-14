"""
A tiny libretro-inspired "core" interface.

Real RetroArch is a native frontend that loads compiled libretro cores
(.so/.dll files) written in C/C++ -- that binary plugin model doesn't
exist in a pure-Python, PIL-rendered phone OS. What Kos borrows from
RetroArch instead is the *architecture and feature set*: a frontend
(apps/emulator_app.py) that's completely decoupled from any one system,
a ROM browser that groups games by core, save states, rewind, and a
fast-forward toggle -- all driven through this one small interface.

Adding a new system later is just: write a class implementing
EmulatorCore, decorate it with @register, and import that module once
(see the bottom of apps/emulator_app.py). The frontend picks it up
automatically -- no other file needs to change.
"""

REGISTRY = {}


class EmulatorCore:
    core_id = "base"
    display_name = "Base Core"
    extensions = ()           # ROM file extensions this core handles, e.g. (".ch8",)
    input_layout = []         # rows of key labels for the auto-built on-screen pad
    display_size = (64, 32)   # native pixel resolution of the core's framebuffer
    on_color = (210, 235, 210)
    off_color = (12, 24, 14)

    def load(self, path):
        """Load a ROM file from disk."""
        raise NotImplementedError

    def run_frame(self, dt, fast_forward=False):
        """Advance emulation by roughly one displayed frame's worth of work."""
        raise NotImplementedError

    def get_display(self):
        """Flat list of pixels (row-major) sized display_size[0]*display_size[1]."""
        raise NotImplementedError

    def press(self, label):
        """A key from input_layout was pressed."""
        pass

    def release(self, label):
        """A key from input_layout was released."""
        pass

    def is_sound_active(self):
        """True while the core wants a tone playing (e.g. CHIP-8's sound timer)."""
        return False

    @property
    def error(self):
        return None

    def save_state(self):
        """Return a JSON-serializable snapshot of full emulation state."""
        raise NotImplementedError

    def load_state(self, state):
        """Restore a snapshot previously returned by save_state()."""
        raise NotImplementedError


def register(core_cls):
    """Class decorator: makes a core discoverable by the frontend."""
    REGISTRY[core_cls.core_id] = core_cls
    return core_cls


def core_for_filename(filename):
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    for core_cls in REGISTRY.values():
        if ext in core_cls.extensions:
            return core_cls
    return None


def all_extensions():
    exts = set()
    for core_cls in REGISTRY.values():
        exts.update(core_cls.extensions)
    return exts
