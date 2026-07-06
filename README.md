# PiOS — a tiny touchscreen phone OS for the Raspberry Pi

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
3. Enable SPI and I2C:
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
sudo apt-get update
sudo apt-get install -y python3-pip python3-pil python3-numpy python3-spidev python3-smbus
pip3 install -r requirements.txt --break-system-packages
```

## Run

```bash
sudo python3 main.py
```

(`sudo` is required for GPIO/SPI access, the same as Waveshare's own demos.)

To boot straight into PiOS on power-up, add a line to the pi user's
crontab or a systemd service that runs `sudo python3 /path/to/main.py`.

## What's included

- `drivers/lcd_st7796.py` — SPI driver for the ST7796S panel (init sequence,
  RGB565 framebuffer push from a PIL image).
- `drivers/touch_ft6336u.py` — I2C driver for the FT6336U touch controller.
- `drivers/ina219_battery.py` — I2C driver for the INA219 fuel gauge on the
  UPS HAT (C), reporting voltage, current, power and estimated battery %.
- `ui/framework.py` — the "OS": a status bar (clock + live battery icon),
  an `App` base class (tap, drag, and release hooks), a shared
  auto-scaling grid layout (`build_grid`) used by both Home and folders,
  a `FolderView` class, a `Keyboard` widget (on-screen QWERTY for any app
  that needs typed text), and a sleep/wake power-saving mode.
- `emulators/chip8.py` — a full CHIP-8 interpreter (all standard
  opcodes). CHIP-8 was chosen deliberately: it needs almost no CPU, so
  it actually runs well on a Pi Zero-class board, and there's a large
  body of public-domain/freely redistributable CHIP-8 software, unlike
  console emulation which requires copyrighted BIOS/ROM files.
- `roms/demo.ch8` — an original demo ROM (hand-assembled by
  `scripts/make_demo_rom.py`) that draws the interpreter's built-in
  hex-digit sprites, just to prove the emulator works out of the box.
  Drop your own legally-obtained `.ch8` files into `roms/` to play more.
- `apps/` — organized into a flat Home screen plus two folders:

  **On the Home screen directly:**
  - **Home** — the launcher (auto-scaling icon grid, plus folder icons)
  - **Clock** — live time and date
  - **Battery** — live voltage/current/power/percent from the UPS HAT
  - **Settings** — Display, Sound, Theme, Wi-Fi & Bluetooth toggles, a PIN
    lock (enforced by a numeric-keypad lock screen the OS shows on
    wake/boot), Date & Time, Installed Apps management, Developer Mode
    (adds a "DEV" tag to the status bar), and About/reset
  - **Paint** — finger-drag drawing with a color palette, eraser, four
    brush sizes, multi-step undo, and one-tap "Save" into the Gallery's
    Pictures folder
  - **Flashlight** — full-brightness white screen / torch
  - **App Store** — browses and installs single-file apps from a GitHub
    repo (see below) -- requires internet and `pip install requests`

  **Inside the "Games" folder:**
  - **Tic-Tac-Toe**, **Memory** (card matching), **Reaction** (whack-a-mole)
  - **RetroArch** — ROM picker + on-screen controls

  **Inside the "Tools" folder:**
  - **Calculator**, **Notes**
  - **File Browser** — navigate the filesystem, paginated, with an "Up"
    button. Tapping a file opens an action bar to Open / Copy / Move /
    Delete (copy/move stash a clipboard, then "Paste" appears once you
    browse to the destination folder). Opening a file routes it to the
    right app — images to Gallery, everything else to Text Editor — and
    tapping a `.phoneapp` file installs it as a new app on the spot,
    using the same single-file install path as the App Store.
  - **Calendar** — month grid, prev/next navigation, quick-add events per day
  - **Weather** — current conditions for a few preset cities via the free
    Open-Meteo API (no key needed) -- requires internet and `pip install requests`
  - **Browser** — a minimal *text-only* web browser with up to four
    independent tabs (tab strip under the status bar, "+" to open, "✕" to
    close) and editable bookmarks (add, rename, re-URL, or delete, saved
    to `~/.pios_bookmarks.json`) alongside a typed-in URL (on-screen
    keyboard). Fetches the page and strips it down to readable, paginated
    text (no images/CSS/JS -- this is a phone-OS-scale "browser", not a
    full engine)
  - **System** — CPU temperature, uptime, storage, memory

### App Store
`apps/app_store_app.py` fetches an `apps.json` manifest from a GitHub repo
you control (`STORE_REPO_OWNER` / `STORE_REPO_NAME` / `STORE_REPO_BRANCH`
at the top of that file) and lists the apps in it. Tapping **Install**
downloads the app's `.py` file into `apps/installed/`, imports it, and
registers it live so it shows up on Home right away. The install is
remembered in `~/.pios_installed_apps.json` and re-registered automatically
on the next boot via `load_installed_apps()` in `main.py`.

To publish an app, push a single-file `App` subclass to your repo plus an
`apps.json` at the repo root:
```json
[
  { "name": "Dice", "class_name": "DiceApp", "icon": "🎲",
    "description": "Roll a virtual dice", "file": "dice_app.py" }
]
```

### On-screen keyboard
`ui/framework.py`'s `Keyboard` widget is a compact QWERTY layout (with a
shift key and a 123/symbols toggle) that any app can drop in for text
entry — see **Notes** ("Type note...") and **Browser** ("Type a URL...")
for the pattern: create a `Keyboard(x, y, w, h)`, forward taps to it from
the app's `on_tap`, and handle the characters/`"BACKSPACE"`/`"ENTER"`
tokens it reports back.

### Folders
`main.py` groups apps into folders with `os_.register_folder(title, [app_names], icon=...)`.
Apps assigned to a folder are hidden from the top-level Home screen and
only reachable by opening that folder; unassigned apps stay on Home.
Folders are one level deep by design — opening an app from inside a
folder and tapping its own "Home" button takes you to the top-level
Home screen, not back into the folder.

### Quality-of-life touches
- **Sleep mode**: `Settings -> Sleep display` blanks the screen and cuts
  the backlight to save the UPS HAT's battery; tap anywhere to wake it.
- **Auto-scaling launcher grid**: the Home screen recalculates icon size
  so any number of installed apps fits without needing pagination.
- **Drag support**: the framework distinguishes taps (for buttons) from
  continuous touch-and-drag (for Paint), so both interaction styles work
  on the same touch driver.

## Notes on tuning for your exact unit

- If touch coordinates come out swapped or mirrored, adjust
  `swap_xy` / `invert_x` / `invert_y` in `FT6336U(...)` in `main.py`.
- If colors look off (red/blue swapped), flip the `0x36` memory-access
  value in `lcd_st7796.py`'s init sequence.
- INA219 address defaults to `0x43` (UPS HAT (C) default); check with
  `i2cdetect -y 1` and pass `addr=` if yours differs.
- Adding a new app is just a new `App` subclass in `apps/` plus one
  `os_.register_app(YourApp)` line in `main.py`.
