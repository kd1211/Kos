#!/usr/bin/env bash
#
# install.sh -- installs Kos's dependencies and sets it up as a systemd
# service that starts on boot and restarts if it ever crashes.
#
# Usage:
#   cd Kos           # wherever you cloned/extracted it -- it installs
#                     # IN PLACE, right here, not copied anywhere else
#   sudo ./install.sh
#
# Safe to re-run any time (e.g. after `git pull` or a System Updater
# update) -- it just re-installs dependencies and rewrites the service
# file, it won't duplicate anything.

set -euo pipefail

# -- must be root: installs apt packages, writes a systemd unit, and may
# enable SPI/I2C via raspi-config -----------------------------------------
if [ "$(id -u)" -ne 0 ]; then
    echo "Please run this with sudo:"
    echo "  sudo ./install.sh"
    exit 1
fi

# the directory this script itself lives in becomes the permanent install
# location -- main.py and every app already resolve their own paths
# relative to themselves (see apps/system_updater_app.py's PROJECT_ROOT),
# so Kos runs fine from wherever you put it; nothing gets copied around
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "$SCRIPT_DIR/main.py" ]; then
    echo "Error: main.py not found in $SCRIPT_DIR"
    echo "Run this script from inside the Kos project folder."
    exit 1
fi

# who to run the service as -- defaults to whoever invoked sudo, falling
# back to 'pi' (the traditional default account) if that can't be
# determined, e.g. when logged in directly as root
RUN_USER="${SUDO_USER:-pi}"
if ! id "$RUN_USER" &>/dev/null; then
    RUN_USER="root"
fi

echo "==> Installing Kos from: $SCRIPT_DIR"
echo "==> Service will run as user: $RUN_USER"
echo

# -- system packages ---------------------------------------------------------
# Prefer apt's prebuilt ARM packages over pip wheels for the heavier
# dependencies (pillow, numpy, pygame especially) -- compiling those from
# source via pip on a Pi Zero can take the better part of an hour, or
# fail outright without build tooling installed. apt just works.
echo "==> Installing system packages (this can take a few minutes)..."
apt-get update -qq
apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-pil \
    python3-numpy \
    python3-requests \
    python3-pygame \
    python3-spidev \
    python3-rpi.gpio \
    python3-smbus \
    i2c-tools \
    fonts-dejavu-core \
    network-manager \
    bluez \
    poppler-utils \
    alsa-utils

# smbus2 specifically (the project imports `smbus2`, not the older
# `smbus` apt already installed above) -- try apt first, pip as a
# fallback since availability varies across Raspberry Pi OS releases
if ! python3 -c "import smbus2" &>/dev/null; then
    if ! apt-get install -y --no-install-recommends python3-smbus2 2>/dev/null; then
        echo "==> python3-smbus2 not available via apt, installing with pip instead..."
        pip3 install --break-system-packages smbus2 2>/dev/null || pip3 install smbus2
    fi
fi

# picamera2 (Camera app) is genuinely optional -- not everyone has a
# camera module attached, and it isn't reliably pip-installable outside
# Raspberry Pi OS's own apt repo (it needs libcamera's system bindings),
# so this is best-effort and never fails the rest of setup
echo "==> Installing picamera2 (optional, for the Camera app)..."
apt-get install -y --no-install-recommends python3-picamera2 2>/dev/null \
    || echo "    picamera2 not available here -- Camera app will just report no camera detected"

# catch anything still missing (e.g. a requirement added later that
# apt doesn't package) without clobbering the apt-provided versions above
echo "==> Checking for any remaining Python dependencies via pip..."
pip3 install --break-system-packages -r requirements.txt 2>/dev/null \
    || pip3 install -r requirements.txt

echo

# -- enable SPI and I2C (needed for the LCD and the battery HAT) -------------
if command -v raspi-config &>/dev/null; then
    echo "==> Enabling SPI and I2C interfaces..."
    raspi-config nonint do_spi 0
    raspi-config nonint do_i2c 0
else
    echo "==> raspi-config not found (not a Raspberry Pi OS image?) -- skipping SPI/I2C setup."
    echo "    Make sure SPI and I2C are enabled some other way before starting the service."
fi
echo

# -- systemd service ----------------------------------------------------------
SERVICE_PATH="/etc/systemd/system/kos.service"
echo "==> Writing $SERVICE_PATH ..."
cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=Kos - touchscreen launcher
After=multi-user.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=/usr/bin/python3 $SCRIPT_DIR/main.py
Restart=on-failure
RestartSec=2
User=$RUN_USER
# GPIO/SPI/I2C access typically needs these groups if not running as root
SupplementaryGroups=gpio spi i2c

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable kos.service

echo
echo "==> Done."
echo
echo "Kos is installed as a systemd service (kos.service), running as '$RUN_USER',"
echo "and will start automatically on every boot."
echo
echo "Useful commands:"
echo "  sudo systemctl start kos      # start it right now"
echo "  sudo systemctl stop kos       # stop it"
echo "  sudo systemctl restart kos    # restart (e.g. after an update)"
echo "  sudo systemctl status kos     # check if it's running"
echo "  journalctl -u kos -f          # follow its logs live"
echo
read -r -p "Start Kos now? [Y/n] " REPLY
if [[ ! "$REPLY" =~ ^[Nn]$ ]]; then
    systemctl start kos.service
    echo "Started. Check 'sudo systemctl status kos' or 'journalctl -u kos -f' if the screen stays blank."
fi
