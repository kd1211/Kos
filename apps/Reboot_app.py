#!/usr/bin/env python3

import os
import sys

print("Rebooting system...")

try:
    os.system("sudo reboot")
except Exception as e:
    print("Error:", e)
    sys.exit(1)
