#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""ztglass-shell: everything of ztOS Glass that is not a window. The home
screen (pages of apps, four of them in the dock), the status bar, the lock
screen, the control centre and the volume, each a layer-shell surface over
or under the apps. The compositor (ztglass) is told what to open and tells
what happens, over $XDG_RUNTIME_DIR/ztglass.sock.

Config, ~/.config/ztglass/config (all optional):

    [home]
    dock = ztphone.desktop ztmessages.desktop os.ztos.weather.desktop ztcamera.desktop
    wallpaper = /path/to/photo.jpg
    lock = on
"""

import configparser
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
os.environ.setdefault("QT_QPA_PLATFORM", "wayland")
os.environ["QT_WAYLAND_SHELL_INTEGRATION"] = "layer-shell"
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import (Property, QObject, QSocketNotifier, QTimer, QUrl, Signal, Slot)  # noqa: E402
from PySide6.QtGui import QFont, QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickWindow  # noqa: E402

import apps as appsmod  # noqa: E402
import art  # noqa: E402

CONFIG = Path(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")) / "ztglass" / "config"
DOCK_DEFAULT = ["ztphone.desktop", "ztmessages.desktop", "os.ztos.weather.desktop", "ztcamera.desktop"]
DOCK_FALLBACK = ["phone", "messages", "browser", "camera", "weather", "music", "settings", "files"]


def log(*args):
    print("ztglass-shell:", *args, file=sys.stderr, flush=True)


def read(path, default=""):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


class Link(QObject):
    """The compositor's socket: lines out, lines in, again after it goes."""
    line = Signal(str)

    def __init__(self):
        super().__init__()
        self.sock = None
        self.notifier = None
        self.buf = b""
        self.retry = QTimer(self, interval=1000, singleShot=True)
        self.retry.timeout.connect(self.connect)
        self.connect()

    def connect(self):
        path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "ztglass.sock")
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(path)
            s.setblocking(False)
        except OSError:
            self.retry.start()
            return
        self.sock = s
        self.notifier = QSocketNotifier(s.fileno(), QSocketNotifier.Read, self)
        self.notifier.activated.connect(self.readable)
        log("linked to the compositor")

    def readable(self):
        try:
            data = self.sock.recv(4096)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self.notifier.setEnabled(False)
            self.sock.close()
            self.sock = None
            self.retry.start()
            return
        self.buf += data
        while b"\n" in self.buf:
            one, self.buf = self.buf.split(b"\n", 1)
            self.line.emit(one.decode(errors="replace"))

    def send(self, text):
        if self.sock:
            try:
                self.sock.sendall((text + "\n").encode())
            except OSError:
                pass


class Shell(QObject):
    appsChanged = Signal()
    wallChanged = Signal()
    clockChanged = Signal()
    statusChanged = Signal()
    lockedChanged = Signal()
    controlChanged = Signal()
    volumeChanged = Signal()
    showingChanged = Signal()
    wentHome = Signal()
    openedApp = Signal(str)
    volumeShown = Signal()

    def __init__(self, app):
        super().__init__()
        self.cfg = configparser.ConfigParser()
        self.cfg.read(CONFIG)
        screen = app.primaryScreen()
        self.dpr = screen.devicePixelRatio()
        size = screen.size()
        self.screen_w, self.screen_h = size.width(), size.height()
        self.glass_maker = art.Glass()
        self._apps, self._dock, self._running = [], [], []
        self._wall = self._wall_blur = ""
        self._locked = self.cfg.get("home", "lock", fallback="on") != "off"
        self._control = False
        self._volume, self._muted = 0.5, False
        self._showing = ""
        self._battery, self._charging, self._wifi = 100, False, -1
        self.stamp = None

        self.link = Link()
        self.link.line.connect(self.heard)
        self.make_wallpaper()
        self.load_apps()
        self.poll_status()

        self.clock = QTimer(self)
        self.clock.timeout.connect(self.tick)
        self.tick()
        self.status_timer = QTimer(self, interval=10000)
        self.status_timer.timeout.connect(self.poll_status)
        self.status_timer.start()
        self.apps_timer = QTimer(self, interval=20000)
        self.apps_timer.timeout.connect(self.load_apps)
        self.apps_timer.start()
        screen.geometryChanged.connect(lambda *_: self.resized(app))

    # ---- what the screen is ------------------------------------------------------------

    def resized(self, app):
        screen = app.primaryScreen()
        size = screen.size()
        if (size.width(), size.height(), screen.devicePixelRatio()) != (self.screen_w, self.screen_h, self.dpr):
            self.screen_w, self.screen_h, self.dpr = size.width(), size.height(), screen.devicePixelRatio()
            self.make_wallpaper()
            self.load_apps(force=True)

    def make_wallpaper(self):
        t = time.monotonic()
        photo = self.cfg.get("home", "wallpaper", fallback="") or None
        px_w, px_h = int(round(self.screen_w * self.dpr)), int(round(self.screen_h * self.dpr))
        sharp, soft = art.wallpapers(px_w, px_h, photo)
        self._wall, self._wall_blur = QUrl.fromLocalFile(sharp).toString(), QUrl.fromLocalFile(soft).toString()
        self.glass_maker.use(soft, self.dpr)
        log(f"wallpaper {px_w}x{px_h} in {time.monotonic() - t:.2f} s")
        self.wallChanged.emit()

    def load_apps(self, force=False):
        stamp = appsmod.stamp()
        if stamp == self.stamp and not force:
            return
        self.stamp = stamp
        t = time.monotonic()
        found = appsmod.scan()
        px = int(round(62 * self.dpr))
        for a in found:
            a["icon_url"] = QUrl.fromLocalFile(art.icon_file(a, px)).toString()
            a["tint"] = art.tint_of(a)[1]
        by_key = {a["key"]: a for a in found}
        wanted = self.cfg.get("home", "dock", fallback="").split() or DOCK_DEFAULT
        dock = [by_key[k] for k in wanted if k in by_key][:4]
        for kind in DOCK_FALLBACK:
            if len(dock) >= 4:
                break
            for a in found:
                if a not in dock and art.kind_of(a) == kind:
                    dock.append(a)
                    break
        self._dock = dock
        self._apps = [a for a in found if a not in dock]
        log(f"{len(found)} apps, icons in {time.monotonic() - t:.2f} s")
        self.appsChanged.emit()

    # ---- the compositor ---------------------------------------------------------------------

    def heard(self, line):
        word, _, rest = line.partition(" ")
        if word == "home":
            self._showing = ""
            self.showingChanged.emit()
            self.wentHome.emit()
        elif word == "app":
            self._showing = rest
            self.showingChanged.emit()
            self.openedApp.emit(rest)
        elif word == "apps":
            self._running = rest.split()
        elif word == "blank":
            if rest == "1":
                self.set_control(False)
                if self.cfg.get("home", "lock", fallback="on") != "off":
                    self._locked = True
                    self.lockedChanged.emit()
            else:
                self.tick()
                self.poll_status()
        elif word == "volume":
            QTimer.singleShot(60, self.read_volume)

    def read_volume(self):
        try:
            out = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], capture_output=True,
                                 text=True, timeout=2).stdout
            self._volume = float(out.split()[1])
            self._muted = "MUTED" in out
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            return
        self.volumeChanged.emit()
        self.volumeShown.emit()

    @Slot(str)
    def launch(self, key):
        for a in self._apps + self._dock:
            if a["key"] == key:
                log("open", a["name"], "-", a["command"])
                self.link.send(f"launch {key} {a['command']}")
                return

    @Slot()
    def home(self):
        self.link.send("home")

    @Slot()
    def sleep(self):
        self.set_control(False)
        self.link.send("sleep")

    # ---- the time, the battery, the radio ------------------------------------------------------

    def tick(self):
        self.clockChanged.emit()
        self.clock.start(1000 * (60 - time.localtime().tm_sec) + 50)

    def poll_status(self):
        cap = read("/sys/class/power_supply/max170xx_battery/capacity") or read(
            next(iter(sorted(Path("/sys/class/power_supply").glob("*/capacity"))), "/nonexistent"), "100")
        try:
            self._battery = max(0, min(100, int(cap)))
        except ValueError:
            pass
        online = [read(p) for p in Path("/sys/class/power_supply").glob("*/online")]
        self._charging = "1" in online
        wifi = -1
        for iface in sorted(Path("/sys/class/net").glob("*/wireless")):
            name = iface.parent.name
            if read(iface.parent / "operstate") != "up":
                continue
            wifi = 3
            try:
                out = subprocess.run(["iw", "dev", name, "link"], capture_output=True, text=True, timeout=2).stdout
                dbm = float(out.split("signal:")[1].split()[0])
                wifi = 3 if dbm >= -60 else 2 if dbm >= -72 else 1
            except (OSError, IndexError, ValueError, subprocess.SubprocessError):
                pass
            break
        self._wifi = wifi
        self.statusChanged.emit()

    @Slot(result=bool)
    def wifiEnabled(self):
        try:
            return subprocess.run(["nmcli", "radio", "wifi"], capture_output=True, text=True,
                                  timeout=3).stdout.strip() == "enabled"
        except (OSError, subprocess.SubprocessError):
            return False

    @Slot(bool)
    def setWifi(self, on):
        subprocess.Popen(["nmcli", "radio", "wifi", "on" if on else "off"])
        QTimer.singleShot(3000, self.poll_status)

    @Slot(result=bool)
    def airplane(self):
        try:
            out = subprocess.run(["nmcli", "radio", "all"], capture_output=True, text=True, timeout=3).stdout
            return "enabled" not in out.split("\n", 1)[-1]
        except (OSError, subprocess.SubprocessError):
            return False

    @Slot(bool)
    def setAirplane(self, on):
        subprocess.Popen(["nmcli", "radio", "all", "off" if on else "on"])
        QTimer.singleShot(3000, self.poll_status)

    @Slot(float)
    def setVolume(self, v):
        v = max(0.0, min(1.0, v))
        self._volume = v
        subprocess.Popen(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{v:.2f}"])
        self.volumeChanged.emit()

    # ---- glass ---------------------------------------------------------------------------

    @Slot(float, float, float, float, float, result=str)
    def glass(self, x, y, w, h, r):
        path = self.glass_maker.file(x, y, w, h, r)
        return QUrl.fromLocalFile(path).toString() if path else ""

    @Slot(float, float, float, float, float, float, result=str)
    def glassTint(self, x, y, w, h, r, tint):
        path = self.glass_maker.file(x, y, w, h, r, tint=tint)
        return QUrl.fromLocalFile(path).toString() if path else ""

    # ---- for QML -----------------------------------------------------------------------------

    def set_control(self, on):
        if self._control != on:
            self._control = on
            self.controlChanged.emit()

    @Slot()
    def unlock(self):
        self._locked = False
        self.lockedChanged.emit()

    @Slot(bool)
    def showControl(self, on):
        if on:
            self.poll_status()
        self.set_control(on)

    def _clock(self):
        return time.strftime("%H:%M")

    def _date(self):
        return time.strftime("%A, %B ") + str(time.localtime().tm_mday)

    apps = Property("QVariantList", lambda self: self._apps, notify=appsChanged)
    dock = Property("QVariantList", lambda self: self._dock, notify=appsChanged)
    wallpaper = Property(str, lambda self: self._wall, notify=wallChanged)
    wallpaperBlur = Property(str, lambda self: self._wall_blur, notify=wallChanged)
    clockText = Property(str, _clock, notify=clockChanged)
    dateText = Property(str, _date, notify=clockChanged)
    battery = Property(int, lambda self: self._battery, notify=statusChanged)
    charging = Property(bool, lambda self: self._charging, notify=statusChanged)
    wifi = Property(int, lambda self: self._wifi, notify=statusChanged)
    locked = Property(bool, lambda self: self._locked, notify=lockedChanged)
    control = Property(bool, lambda self: self._control, notify=controlChanged)
    volume = Property(float, lambda self: self._volume, notify=volumeChanged)
    muted = Property(bool, lambda self: self._muted, notify=volumeChanged)
    showing = Property(str, lambda self: self._showing, notify=showingChanged)


def main():
    QQuickWindow.setDefaultAlphaBuffer(True)
    app = QGuiApplication(sys.argv)
    app.setApplicationName("ztglass-shell")
    app.setDesktopFileName("ztglass-shell")
    app.setFont(QFont(art.FONT, 12))
    shell = Shell(app)
    engine = QQmlApplicationEngine()
    engine.rootContext().setContextProperty("shell", shell)
    engine.addImportPath(str(HERE / "qml"))
    for name in ("Home", "StatusBar", "Lock", "Control", "Volume"):
        engine.load(QUrl.fromLocalFile(str(HERE / "qml" / f"{name}.qml")))
        if not engine.rootObjects():
            log("QML did not load:", name)
            return 1
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
