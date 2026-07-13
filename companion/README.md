# Kos Chat Companion

A tiny desktop chat client for anyone on the same Wi-Fi/LAN who doesn't
have a Kos device, but still wants to join the PictoChat-style chat in
Kos's **Messages** app: draw or type a message into one of four rooms
(A/B/C/D), same as the original DS/DSi -- no accounts, no server, no
history saved anywhere.

It speaks the exact same UDP-broadcast protocol Kos's Messages app
uses, so the two interoperate directly over the local network -- no
bridge, no cloud, nothing in between.

## Requirements

- Python 3
- **tkinter** -- ships with most Python installs. If you get an import
  error, install it:
  - Debian/Ubuntu: `sudo apt install python3-tk`
  - Fedora: `sudo dnf install python3-tkinter`
  - macOS (python.org installer) / Windows: already included
- **Pillow**: `pip install pillow`

## Run it

```bash
python3 kos_chat_companion.py
```

You'll be asked for a name, then the chat window opens: room tabs
across the top, the message feed in the middle, and a small drawing
canvas + text box at the bottom to compose with -- draw, type, or
both together in the same message, then hit Send.

## Notes

- Everyone on the same room, on the same network segment, sees the
  same messages -- there's no way to message just one person.
- Nothing is saved to disk; closing the window clears your local copy
  of the conversation (though anyone else still around keeps theirs
  until they close too).
- The "N nearby" counter in the corner reflects Kos devices (and other
  companion instances) that have broadcast a presence beacon in the
  last ~12 seconds -- it's just a hint, not a directory.
