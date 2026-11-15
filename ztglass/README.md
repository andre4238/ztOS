# ztOS Glass

A new phone interface for ztOS, separate from ztMETRO. It has a home screen with pages of apps and a dock of four under a pane of glass. A status bar runs along the top, there's a lock screen and a control centre, and gestures replace the buttons.

| Part | What it is |
|---|---|
| `compositor/` | **ztglass**, the Wayland compositor (C, wlroots 0.20). It shows one app at a time, full screen, and handles the touch screen, the keys and the gestures. |
| `shell/` | **ztglass-shell** (Python + QML, PySide6). The home screen, status bar, lock screen, control centre and volume display, as layer-shell surfaces. |
| `session/` | `ztglass-session`, the script greetd starts, and the `ztglass-shell` launcher. |

## Using it

| Gesture or key | What happens |
|---|---|
| Swipe up from the bottom edge | Back to the home screen |
| Swipe in from the left edge | Back (sends Escape to the app) |
| Pull down on the status bar | Control centre: Wi-Fi, flight mode, volume, screen off |
| Power key | Screen off and on. The lock screen comes back; swipe up to open. |
| Volume keys | Change the volume and show the volume display |

Tapping an app opens it, or brings back its window if it's already running.

## Building and installing (on the phone)

```sh
make && sudo make install
sudo pacman -S qt6-wayland layer-shell-qt pyside6 inter-font
```

To make it the session, point greetd at it in `/etc/greetd/config.toml`:

```toml
command = "/usr/local/bin/ztglass-session"
```

To go back to ztMETRO, use `/usr/local/bin/ztmetro-session` instead (`config.toml.ztmetro` is the old file).

## Config

`~/.config/ztglass/config` is optional:

```ini
[home]
dock = ztphone.desktop ztmessages.desktop os.ztos.weather.desktop ztcamera.desktop
wallpaper = /path/to/photo.jpg
lock = on
```

## How the parts talk

The shell and the compositor talk over `$XDG_RUNTIME_DIR/ztglass.sock`, one line per message.

| Direction | Messages |
|---|---|
| Shell → compositor | `launch KEY COMMAND`, `home`, `close KEY`, `sleep`, `wake` |
| Compositor → shell | `home`, `app KEY`, `apps KEY…`, `blank 0/1`, `volume up/down` |

## Artwork

The wallpaper, app icons and glass panels are painted by `shell/art.py` and cached in `~/.cache/ztglass`. Every symbol is drawn in code, so ztGlass ships no third-party artwork. The font is Inter (SIL OFL).
