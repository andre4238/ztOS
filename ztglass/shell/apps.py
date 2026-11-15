# SPDX-License-Identifier: GPL-3.0-or-later
"""The applications on this phone, from their .desktop files, the way a menu
finds them: the user's own first, then every data dir's, the first of a name
wins. Hidden ones (NoDisplay, Hidden, a TryExec that is not there) are left out."""

import os
import shlex
import shutil
from pathlib import Path

FIELD_CODES = ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%i", "%c", "%k", "%v", "%m")

# what ztGlass never shows, by .desktop id: helpers that are applications only
# to their own programs
SKIP = {
    "org.gnome.Terminal.Preferences.desktop", "org.gnupg.pinentry-qt.desktop",
    "xdg-desktop-portal-gtk.desktop", "waydroid.market.desktop", "waydroid.app.install.desktop",
    "ztos-android-apk.desktop",
}


# short names, the way they fit under an icon
SHORT = {
    "Devices and Services": "Devices", "Power Management": "Power", "OSIAL Management": "OSIAL",
    "mpv Media Player": "mpv", "Qt V4L2 test Utility": "V4L2 Test", "Qt V4L2 video capture utility": "Capture",
    "Messaging": "Messages",
}


def short_name(name):
    if name in SHORT:
        return SHORT[name]
    for tail in (" Management", " Utility", " Manager", " Application"):
        if name.endswith(tail) and len(name) > 12:
            return name[: -len(tail)]
    return name


def runnable(command):
    """Whether the program the command starts is there."""
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    while words and "=" in words[0] and not words[0].startswith("/"):
        words = words[1:]  # VAR=value before the program
    if not words:
        return False
    first = words[0]
    return os.access(first, os.X_OK) if os.path.isabs(first) else shutil.which(first) is not None


def data_dirs():
    home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    rest = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [home] + [d for d in rest.split(":") if d]


def parse(path):
    entry, section = {}, None
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            section = line.strip("[]")
            continue
        if section != "Desktop Entry" or "=" not in line:
            continue
        key, value = line.split("=", 1)
        entry.setdefault(key.strip(), value.strip())
    return entry


def clean_exec(command):
    """Exec without its field codes (nothing is opened with it here)."""
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    words = [w for w in words if w not in FIELD_CODES]
    return " ".join(shlex.quote(w) for w in words)


def visible(entry):
    if entry.get("Type", "Application") != "Application":
        return False
    if entry.get("NoDisplay", "").lower() == "true" or entry.get("Hidden", "").lower() == "true":
        return False
    if not entry.get("Exec") or not entry.get("Name"):
        return False
    try_exec = entry.get("TryExec")
    if try_exec and not (os.path.isabs(try_exec) and os.access(try_exec, os.X_OK)) and not shutil.which(try_exec):
        return False
    return True


def scan():
    """[{key, name, command, icon, path}] in name order."""
    seen, apps = set(), []
    for base in data_dirs():
        folder = Path(base) / "applications"
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.desktop")):
            key = str(path.relative_to(folder)).replace("/", "-")
            if key in seen:
                continue
            seen.add(key)
            entry = parse(path)
            if key in SKIP or not entry or not visible(entry):
                continue
            apps.append({
                "key": key,
                "name": short_name(entry.get("Name")),
                "command": clean_exec(entry["Exec"]),
                "icon": entry.get("Icon", ""),
                "path": str(path),
                "terminal": entry.get("Terminal", "").lower() == "true",
            })
    # Settings is ztMETRO's own and has no entry; it opens by itself here too
    if "ztsettings.desktop" not in seen and shutil.which("ztsettings"):
        apps.append({"key": "ztsettings.desktop", "name": "Settings", "command": "ztsettings",
                     "icon": "", "path": "", "terminal": False})
    for app in apps:
        if app["terminal"]:
            app["command"] = "foot -e " + app["command"]
    apps = [a for a in apps if runnable(a["command"])]
    apps.sort(key=lambda a: a["name"].lower())
    return apps


def stamp():
    """Changes when an application comes or goes: the folders' own times."""
    times = []
    for base in data_dirs():
        folder = Path(base) / "applications"
        try:
            times.append(folder.stat().st_mtime_ns)
        except OSError:
            times.append(0)
    return tuple(times)
