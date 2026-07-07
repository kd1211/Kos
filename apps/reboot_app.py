import os

class RebootApp:
    name = "Reboot"

    def __init__(self, os_):
        self.os = os_

    def draw(self):
        self.os.lcd.clear()

        self.os.lcd.text(
            40,
            80,
            "Reboot Device?",
            size=2
        )

        self.os.lcd.text(
            40,
            140,
            "Tap screen to reboot",
            size=1
        )

    def update(self, touch):
        if touch:
            os.system("sudo reboot")
