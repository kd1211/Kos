#!/usr/bin/env python3
"""
PiOS - a tiny touchscreen phone OS for the Raspberry Pi, built for:
  - Waveshare 3.5inch Capacitive Touch LCD (ST7796S + FT6336U, SPI/I2C)
  - Waveshare UPS HAT (C) (INA219 battery monitor, I2C)

Run with:
    sudo python3 main.py
(sudo is needed for GPIO/SPI access, same as Waveshare's own demos)
"""

from drivers.lcd_st7796 import ST7796
from drivers.touch_ft6336u import FT6336U
from drivers.ina219_battery import INA219
from ui.framework import PhoneOS

from apps.home import Home
from apps.clock_app import ClockApp
from apps.battery_app import BatteryApp
from apps.notes_app import NotesApp
from apps.calculator_app import CalculatorApp
from apps.settings_app import SettingsApp
from apps.paint_app import PaintApp
from apps.tictactoe_app import TicTacToeApp
from apps.memory_app import MemoryApp
from apps.reaction_app import ReactionApp
from apps.flashlight_app import FlashlightApp
from apps.sysinfo_app import SysInfoApp
from apps.file_browser_app import FileBrowserApp
from apps.calendar_app import CalendarApp
from apps.weather_app import WeatherApp
from apps.browser_app import BrowserApp
from apps.emulator_app import EmulatorApp
from apps.app_store_app import AppStoreApp, load_installed_apps
from apps.music_app import MusicApp
from apps.terminal_app import TerminalApp
from apps.gallery_app import GalleryApp
from apps.text_editor_app import TextEditorApp
from apps.messages_app import MessagesApp
from apps.system_updater_app import SystemUpdaterApp
from apps.calibrate_touch_app import CalibrateTouchApp
from apps.snake_app import SnakeApp
from apps.game2048_app import Game2048App
from apps.breakout_app import BreakoutApp
from apps.reboot_app import RebootApp


def main():
    lcd = ST7796()
    lcd.init()

    touch = FT6336U()
    battery = INA219()

    os_ = PhoneOS(lcd, touch, battery)

    # Standalone apps (shown directly on the Home screen)
    os_.register_app(Home)
    os_.register_app(ClockApp)
    os_.register_app(BatteryApp)
    os_.register_app(SettingsApp)
    os_.register_app(PaintApp)
    os_.register_app(FlashlightApp)
    os_.register_app(AppStoreApp)
    os_.register_app(RebootApp)
  
    # Apps that live inside folders
    os_.register_app(CalculatorApp)
    os_.register_app(NotesApp)
    os_.register_app(FileBrowserApp)
    os_.register_app(CalendarApp)
    os_.register_app(WeatherApp)
    os_.register_app(BrowserApp)
    os_.register_app(SysInfoApp)
    os_.register_app(TicTacToeApp)
    os_.register_app(MemoryApp)
    os_.register_app(ReactionApp)
    os_.register_app(EmulatorApp)
    os_.register_app(MusicApp)
    os_.register_app(TerminalApp)
    os_.register_app(GalleryApp)
    os_.register_app(TextEditorApp)
    os_.register_app(MessagesApp)
    os_.register_app(SystemUpdaterApp)
    os_.register_app(CalibrateTouchApp)
    os_.register_app(SnakeApp)
    os_.register_app(Game2048App)
    os_.register_app(BreakoutApp)

    # Group related apps into folders on the Home screen
    os_.register_folder("Games", ["TicTacToe", "Memory", "Reaction", "RetroArch",
                                   "Snake", "2048", "Breakout"],
                         icon="\U0001F3AE")
    os_.register_folder("Tools", ["Calculator", "Notes", "TextEditor", "FileBrowser",
                                   "Calendar", "Weather", "Browser", "System",
                                   "Terminal", "Gallery", "Messages",
                                   "System Updater", "Calibrate Touch"],
                         icon="\U0001F4C1")

    # Re-register any apps previously installed from the App Store so they
    # persist across reboots. A bad/missing download won't stop boot.
    load_installed_apps(os_)

    os_.run()


if __name__ == "__main__":
    main()
