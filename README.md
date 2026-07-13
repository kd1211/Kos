# Kos — a tiny touchscreen phone OS for the Raspberry Pi

Built for two specific Waveshare boards:

- **3.5inch Capacitive Touch LCD** — 320×480 IPS panel, ST7796S driver chip
  (SPI) + FT6336U capacitive touch controller (I2C).
- **UPS HAT (C)** — battery power board with an INA219 voltage/current
  monitor (I2C), for the Raspberry Pi.

## Hardware setup

1. Mount the UPS HAT (C) onto the Pi's GPIO header via its pogo pins,
   clip in the included Li-po battery, and charge it fully once before
   first use (per the wiki, this activates the protection circuit).
2. Connect the LCD's 15PIN cable to the Pi as described on the LCD wiki:
   SPI (DIN/CLK/CS/DC/RST) for the display, I2C (SDA/SCL) for touch,
   plus VCC/GND/BL.
3. SPI and I2C need to be enabled -- `install.sh` below does this for
   you automatically. To do it by hand instead:
   ```bash
   sudo raspi-config
   # Interface Options -> SPI -> Enable
   # Interface Options -> I2C -> Enable
   sudo reboot
   ```
4. Confirm the buses are alive:
   ```bash
   ls /dev/spidev*      # expect /dev/spidev0.0
   i2cdetect -y 1       # expect 0x38 (touch) and 0x43 (battery)
   ```

## Install

```bash
cd Kos                  # wherever you cloned/extracted it
sudo ./install.sh
```

This installs every dependency (preferring apt's prebuilt ARM packages
over pip, since compiling pillow/numpy/pygame from source on a Pi Zero
can take the better part of an hour), enables SPI and I2C, and sets
Kos up as a systemd service (`kos.service`) that starts on boot and
restarts itself if it ever crashes. It installs *in place* -- wherever
you run it from is where it stays; nothing gets copied elsewhere. Safe
to re-run any time, including after a System Updater update.

```bash
sudo systemctl start kos      # start it right now
sudo systemctl status kos     # check if it's running
journalctl -u kos -f          # follow its logs live
```

<details>
<summary>Installing dependencies by hand instead</summary>

```bash
sudo apt-get update
sudo apt-get install -y python3-pip python3-pil python3-numpy python3-spidev \
    python3-rpi.gpio python3-smbus python3-smbus2 python3-requests python3-pygame
pip3 install -r requirements.txt --break-system-packages
```

Run directly with:
```bash
sudo python3 main.py
```
(`sudo` is required for GPIO/SPI access, the same as Waveshare's own demos.)
</details>

## What's included

- `drivers/lcd_st7796.py` — SPI driver for the ST7796S panel (init sequence,
  RGB565 framebuffer push from a PIL image).
- `drivers/touch_ft6336u.py` — I2C driver for the FT6336U touch controller.
- `drivers/ina219_battery.py` — I2C driver for the INA219 fuel gauge on the
  UPS HAT (C), reporting voltage, current, power and estimated battery %.
- `drivers/camera.py` — wraps `picamera2` for the Camera app. Unlike the
  three drivers above, which `main.py` assumes are always present (it
  doesn't even try/except around them -- this OS is built for that
  specific hardware), a camera is genuinely optional, so this one is
  instantiated lazily by the Camera app itself and exposes an
  `.available` flag instead of raising if there's no camera attached or
  `picamera2` isn't installed.
- `ui/framework.py` — the "OS": a status bar (clock + live battery icon,
  a DEV tag when Developer Mode is on), a PIN-lock screen shown on
  wake/boot, an `App` base class (tap, drag, and release hooks), a
  shared auto-scaling grid layout (`build_grid`) used by folders, a
  `FolderView` class, a `Keyboard` widget (on-screen QWERTY for any app
  that needs typed text), a `ScrollArea` helper (drag-to-scroll lists,
  used by Settings and File Browser), automatic per-character font
  fallback (see below), and a sleep/wake power-saving mode.
- `ui/wallpaper.py` — renders the Home screen background: a few built-in
  gradients, a photo picked from `~/Pictures`, or none (solid theme
  color), cached so a photo wallpaper isn't re-decoded every frame.
- `ui/net_control.py` — Wi-Fi (via `nmcli`) and Bluetooth (via
  `bluetoothctl`) scanning/connecting for Settings, entirely on
  background threads with a lock-protected snapshot the UI polls --
  scanning a real radio takes several seconds and this OS's render loop
  is single-threaded, so blocking it would freeze touch input too.
  Reports "not available" cleanly if those tools/adapters aren't
  present rather than raising into the UI.
- `ui/notifications.py` — a small persisted notification queue any app
  posts to (`post(title, body, source=...)`), read by the Quick
  Settings panel and the status-bar badge. Thread-safe, so background
  work (an incoming chat message, a Wi-Fi scan result) can post
  directly without touching the render loop.
- `assets/fonts/` — DejaVuSans.ttf (all normal text) and Symbola.ttf (a
  fallback covering the emoji/pictograph glyphs used as app icons --
  the palette, globe, folder, lock, wallpaper, wifi, etc. -- that DejaVu
  doesn't have). Both ship *with the repo* rather than relying on
  whatever fonts happen to be preinstalled on a freshly flashed Pi.
  `ui/framework.py` picks whichever font actually has each character
  automatically (even within a single string, like a menu row's
  "\U0001F5BC  Wallpaper"), using coverage baked offline into
  `ui/_font_coverage.py` -- no extra Python packages needed at runtime
  to make this work.
- `emulators/chip8.py` — a full CHIP-8 interpreter (all standard
  opcodes). CHIP-8 was chosen deliberately: it needs almost no CPU, so
  it actually runs well on a Pi Zero-class board, and there's a large
  body of public-domain/freely redistributable CHIP-8 software, unlike
  console emulation which requires copyrighted BIOS/ROM files.
- `roms/demo.ch8` — an original demo ROM (hand-assembled by
  `scripts/make_demo_rom.py`) that draws the interpreter's built-in
  hex-digit sprites, just to prove the emulator works out of the box.
  Drop your own legally-obtained `.ch8` files into `roms/` to play more.
- `apps/` — every app registers on the top-level Home screen; **Games**
  and **Tools** start out as folders (see "Folders" below) but that's
  just the default arrangement, not a fixed structure -- drag icons
  around and it's whatever you make it.

  - **Home** — multiple pages of icons (swipe left/right, page dots at
    the bottom), an optional wallpaper (set in Settings), folders that
    work the way you'd expect on a phone (see below), and an "Edit"
    mode for rearranging: drag an icon to reorder it, drag it to the
    screen edge to carry it onto the next/previous page, or tap it (in
    Edit mode) for a small Open/Uninstall info sheet
  - **Clock** — live time and date
  - **Battery** — live voltage/current/power/percent from the UPS HAT
  - **Settings** — Display, Sound, Theme, Wallpaper (gradients or a
    Pictures photo), real **Wi-Fi** (scan, connect with a password
    keyboard for secured networks, disconnect, forget) and real
    **Bluetooth** (scan, pair, connect, disconnect, remove) via `nmcli`
    and `bluetoothctl` -- the same tools you'd use by hand over SSH, run
    on a background thread so scanning never freezes the UI -- a PIN
    lock (enforced by a numeric-keypad lock screen the OS shows on
    wake/boot), Date & Time, Installed Apps management, Developer Mode
    (adds a "DEV" tag to the status bar), **Power** (Restart/Shut Down
    with confirmation), and About (device nickname, storage used,
    reset). The menu and any long list here scroll by dragging, the
    same as File Browser.
  - **Paint** — finger-drag drawing with a color palette, eraser, four
    brush sizes, multi-step undo, and one-tap "Save" into the Gallery's
    Pictures folder
  - **Flashlight** — full-brightness white screen / torch
  - **App Store** — browses and installs single-file apps from a GitHub
    repo (see below) -- requires internet and `pip install requests`
  - **Tic-Tac-Toe**, **Memory** (card matching), **Reaction** (whack-a-mole)
  - **RetroArch** — ROM picker + on-screen controls
  - **Raycrawl** — an original first-person corridor shooter built on a
    real grid-DDA raycasting engine (the classic early-90s FPS
    technique): shaded wall strips, occlusion-correct enemy sprites, a
    minimap, and press-and-hold touch controls (move/turn/fire).
    Sub-2ms/frame in testing, so it stays smooth in pure Python on
    modest hardware.
  - **Calculator**, **Notes**
  - **File Browser** — navigate the filesystem as a drag-to-scroll list
    (no more "page 2/5" buttons), with an "Up" button. Tapping a file
    opens an action bar to Open / Copy / Move / Delete (copy/move stash
    a clipboard, then "Paste" appears once you browse to the destination
    folder). Opening a file routes it to the right app — images to
    Gallery, everything else to Text Editor — and tapping a `.phoneapp`
    file installs it as a new app on the spot, using the same
    single-file install path as the App Store.
  - **Calendar** — month grid, prev/next navigation, quick-add events per day
  - **Camera** — live viewfinder from the Pi Camera Module (via
    `picamera2`), a shutter that saves straight into `~/Pictures`
    alongside Paint's saves, a rule-of-thirds grid overlay, and a
    mirror toggle. Genuinely optional hardware -- if no camera is
    attached (or `picamera2` isn't installed) the app still opens
    cleanly and just says so, the same way Wi-Fi/Bluetooth report
    "not available" rather than crashing anything.
  - **Weather** — current conditions for a few preset cities via the free
    Open-Meteo API (no key needed) -- requires internet and `pip install requests`
  - **Browser** — a *text-only* browser (no images/CSS/JS -- fetches a
    page and flows its text) but with a real browser's interaction
    model: a persistent omnibox with Back/Forward/Reload and a bookmark
    star, real per-tab navigation history (Back/Forward move through
    already-fetched pages instantly -- no re-fetch), tappable in-page
    links (rendered in blue, underlined, resolved against the page's
    URL so relative links work), and a New Tab page showing your
    bookmarks as a tile grid instead of a plain list. Up to four
    independent tabs; bookmarks persist to `~/.kos_bookmarks.json`.
  - **System** — CPU temperature, uptime, storage, memory
  - **Voice Recorder** — records via `arecord` (ALSA), playback through
    the same pygame mixer Music uses, so a saved `.wav` is just another
    audio file. Optional hardware, same pattern as Camera: no mic or no
    `arecord` just means a clean "not available" screen.
  - **Clipboard Manager** — a shared text-clipboard history
    (`ui/clipboard.py`) that Notes and Text Editor's Copy/Paste buttons
    write into, since the on-screen Keyboard has no text-selection
    primitive to build a real system clipboard on top of. Tap an older
    entry to bring it back to the top (ready for the next Paste), or
    delete/clear individually.
  - **PDF Viewer** — rasterizes pages on demand via `pdftoppm`/`pdfinfo`
    (poppler-utils) rather than a heavy PDF-parsing library, caching
    each page in memory after the first visit so flipping back and
    forth is instant. File Browser and Downloads both open `.pdf`
    files here automatically.
  - **Downloads** — a dedicated view of `~/Downloads` (the same folder
    Messages already saves incoming files into), so received files have
    a home screen of their own instead of only being reachable by
    browsing there in File Browser. Opens files the same way File
    Browser does.

### App Store
`apps/app_store_app.py` fetches an `apps.json` manifest from a GitHub repo
you control (`STORE_REPO_OWNER` / `STORE_REPO_NAME` / `STORE_REPO_BRANCH`
at the top of that file) and lists the apps in it. Tapping **Install**
downloads the app's `.py` file into `apps/installed/`, imports it, and
registers it live so it shows up on Home right away. The install is
remembered in `~/.kos_installed_apps.json` and re-registered automatically
on the next boot via `load_installed_apps()` in `main.py`.

Currently configured against
[kd1211/Kos-App-Store](https://github.com/kd1211/Kos-App-Store).

To publish an app, push a single-file `App` subclass to your repo plus an
`apps.json` at the repo root:
```json
[
  { "name": "Dice", "class_name": "DiceApp", "icon": "🎲",
    "description": "Roll a virtual dice", "file": "dice_app.py" }
]
```

### System Updater
`apps/system_updater_app.py` checks a `version.txt` at the root of a
GitHub repo (`UPDATE_REPO_OWNER` / `UPDATE_REPO_NAME` / `UPDATE_REPO_BRANCH`
at the top of that file) against the local `version.txt`, and if they
differ, downloads that repo's zipball, backs up the current install to
`~/.kos_backup`, and replaces everything in place. Currently configured
against [kd1211/Kos](https://github.com/kd1211/Kos).

### On-screen keyboard
`ui/framework.py`'s `Keyboard` widget is a compact QWERTY layout (with a
shift key and a 123/symbols toggle) that any app can drop in for text
entry — see **Notes** ("Type note...") and **Browser** ("Type a URL...")
for the pattern: create a `Keyboard(x, y, w, h)`, forward taps to it from
the app's `on_tap`, and handle the characters/`"BACKSPACE"`/`"ENTER"`
tokens it reports back.

### Folders
Folders work like they do on a phone, not like a fixed menu structure:
- **Create one**: in Home's Edit mode, drag an app icon on top of another
  app icon. They merge into a new folder (default name "New Folder"),
  which opens immediately with a rename prompt ready.
- **Add to one**: drag an app icon onto an existing folder's icon.
- **Open one**: tap it (works whether or not you're in Edit mode) --
  it opens as an overlay showing its members, not a separate screen.
- **Rename one**: while it's open, tap its name at the top of the panel.
- **Remove a member**: with the folder open and Home in Edit mode, drag
  a member out past the panel's edge -- it lands back on the current
  Home page, right where you drop it.
- **Auto-dissolve**: a folder that's down to one member turns back into
  a plain icon automatically; one with zero members just disappears.

Folders are one level deep by design (no folders-in-folders). The
layout -- which app or folder is on which page, in what order, and
what's in each folder -- persists to `~/.kos_home_layout.json`.
"Games" and "Tools" are just the *default* starting arrangement, seeded
the first time Home ever runs; after that it's entirely yours to
rearrange.

### Quick Settings & Notifications
Swipe down from the status bar -- or just tap it -- from anywhere in
the OS (not a Home-only feature) to open a combined shade:
- **Quick toggles**: Wi-Fi, Bluetooth, Flashlight (opens the Flashlight
  app directly, since this hardware has no separate LED to toggle
  silently -- it's the screen-as-torch trick), Airplane Mode (Wi-Fi +
  Bluetooth off together), Battery Saver (caps brightness to 40% and
  shortens auto-sleep to 60s), and a Developer Mode shortcut.
- **Brightness and volume sliders**, live -- drag either one and it
  applies immediately, the same values Settings reads and writes.
- **Notifications**: any app can call `ui.notifications.post(title,
  body, source=...)` -- wired up today for incoming Messages, an
  available System Updater update, and a one-shot low-battery warning
  (15%, with hysteresis so it doesn't spam every 2 seconds). Tap a
  notification to mark it read, tap the × to dismiss just that one, or
  Clear All. An unread count badge shows on the status bar itself.

This lives in `ui/framework.py` at the `PhoneOS` level (not as an app),
the same way the PIN lock screen does, since it needs to be reachable
no matter what app is currently open. Touches that start within the
slim status-bar strip are intercepted before ever reaching whatever
app is open -- apps never have interactive content up there anyway --
so this doesn't change how any existing app behaves.

### Quality-of-life touches
- **Sleep mode**: `Settings -> Sleep display` blanks the screen and cuts
  the backlight to save the UPS HAT's battery; tap anywhere to wake it.
- **Auto-scaling icon grids**: Home and folder overlays both recalculate
  icon size so their contents fit the available space cleanly.
- **Drag support**: the framework distinguishes taps (for buttons) from
  continuous touch-and-drag (for Paint, Home's icon rearranging, and
  ScrollArea-based lists), so all of those interaction styles work on
  the same touch driver.
- **Adaptive render loop**: `PhoneOS.run()` only redraws and pushes a
  new frame to the SPI display when something's actually happening --
  a touch is held, a touch event just fired, or the current app opts
  into continuous animation via `wants_animation = True` (games with
  their own physics clock, Clock's live seconds, the emulator only
  while a ROM is actually running -- not while just browsing the ROM
  picker). Idle screens fall back to a light ~1/sec refresh (just
  enough to keep the status bar clock current) and a cheap 50ms touch
  poll, so the SPI bus and CPU are free the instant nothing's
  happening -- and immediately available the instant something is.
  Active frames use elapsed-time-aware pacing (targets ~30fps by
  sleeping only whatever's left of the frame budget) instead of a flat
  delay tacked on regardless of how long rendering already took, and
  the render target canvas is a single reused buffer rather than a
  fresh allocation every frame.

## Notes on tuning for your exact unit

- If touch coordinates come out swapped or mirrored, adjust
  `swap_xy` / `invert_x` / `invert_y` in `FT6336U(...)` in `main.py`.
- If colors look off (red/blue swapped), flip the `0x36` memory-access
  value in `lcd_st7796.py`'s init sequence.
- INA219 address defaults to `0x43` (UPS HAT (C) default); check with
  `i2cdetect -y 1` and pass `addr=` if yours differs.
- Adding a new app is just a new `App` subclass in `apps/` plus one
  `os_.register_app(YourApp)` line in `main.py`.
