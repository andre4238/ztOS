# ASUI – the A-SYSTEMS UI

A second interface for A-SYSTEMS OS, next to ASMS (the A-SYSTEMS Metro Shell).
It has a large clock on the wallpaper, a search bar, a dock under a pane of
frosted glass (the Start button and four apps), and the app list (Start) as
light acrylic rising from below. The wallpaper can be chosen; the default,
*ASUI Bloom*, is painted by the shell itself.

| Part | What it is |
|---|---|
| `compositor/` | **asui**, the Wayland compositor (C, wlroots 0.20). One app at a time, full screen; touch, keys and gestures. On simpledrm (the S10) it drops stale CPU cache lines of each frame before the panel copy, as ASMS does. |
| `shell/` | **asui-shell** (Rust + Slint, OpenGL ES through femtovg). Two windows the compositor knows by title: `ASUI Home` (under every app) and `ASUI Bar` (the status bar over an app). |
| `session/` | `asui-session` (what runs ASUI) and `ztos-session`, what greetd starts: ASUI or ASMS, as `~/.config/ztos/shell` says. |

## Using it

| Gesture | What happens |
|---|---|
| Swipe up on the lock screen | Unlock |
| Start button, or swipe up on the home screen | The app list; the search bar opens it with a keyboard |
| Long press on an app | Open / pin to dock / remove from dock |
| Long press on the wallpaper | Personalize: the wallpaper, and *Switch to ASMS* |
| Swipe up from the bottom edge (in an app) | Back to the home screen |
| Swipe in from the left edge | Back (Escape to the app) |
| Power key | Screen off and on; the lock screen comes back |

From ASMS, Settings › Theme › Shell style › **ASUI** switches back.

## Building

The compositor is built on the phone, the shell in the ARM64 build VM (the
phone needs no Rust):

```sh
# in the VM
cd asui/shell && cargo build --release
# on the phone, with shell/target/release/asui-shell copied in
make && sudo make install
```

greetd's `config.toml` runs `/usr/local/bin/ztos-session`; `~/.config/ztos/shell`
holds `asui` or `asms`.

## Config

`~/.config/asui/config` (written by the shell):

```ini
wallpaper = /path/to/photo.jpg     # empty: ASUI Bloom
dock = ztphone.desktop, superscan.desktop, ztmessages.desktop, ztcamera.desktop
lock = on
```

## Artwork

ASUI ships no third-party artwork: the wallpaper, the Start mark and the app
tiles (the apps' own white symbols on coloured tiles) are drawn in code. The
font is Inter (SIL OFL).
