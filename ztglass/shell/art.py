# SPDX-License-Identifier: GPL-3.0-or-later
"""ztGlass's pictures, painted once and kept in ~/.cache/ztglass: the
wallpaper, a blurred copy of it, the app icons, and the glass panels cut
out of the blurred copy.

Every icon is ztGlass's own: a rounded square with a gradient of the app's
colour, a white symbol drawn here, a sheen and a hairline of light. An app
ztGlass has no symbol for shows its own icon on a light square, or the first
letter of its name."""

import hashlib
import math
import os
import random
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QRadialGradient, QTransform)

VERSION = 3  # raise when anything here paints differently
CACHE = Path(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")) / "ztglass"

FONT = "Inter"

# ---- colours ------------------------------------------------------------------------

# the gradient of each kind of app, top-left to bottom-right
TINTS = {
    "phone": ("#6ef08f", "#1fb150"), "messages": ("#72f294", "#16a945"),
    "camera": ("#a3acb9", "#545c69"), "settings": ("#b3bac6", "#626a78"),
    "weather": ("#59c8ff", "#1764e8"), "music": ("#ff7a98", "#f0284a"),
    "files": ("#69b8ff", "#1f6ff0"), "contacts": ("#ffbf73", "#f2781f"),
    "store": ("#6fa8ff", "#3446f5"), "power": ("#9cf27a", "#2fb34a"),
    "sound": ("#ff8fc7", "#d23f99"), "devices": ("#8f8aff", "#5038e6"),
    "scan": ("#4fe6d3", "#0b9fa6"), "terminal": ("#4a5160", "#161a21"),
    "welcome": ("#c58fff", "#7a3dff"), "chip": ("#ffd36b", "#f08a1d"),
    "video": ("#ff9a5c", "#e8451f"), "android": ("#9df07a", "#2fa84f"),
    "editor": ("#5fe1a8", "#11935f"), "browser": ("#62d0ff", "#1676e6"),
    "calendar": ("#ff8080", "#e8333a"), "clock": ("#4a5160", "#161a21"),
}
SPARE = [("#59c8ff", "#1764e8"), ("#72f294", "#16a945"), ("#ffbf73", "#f2781f"),
         ("#ff7a98", "#f0284a"), ("#c58fff", "#7a3dff"), ("#4fe6d3", "#0b9fa6"),
         ("#ffd36b", "#f08a1d"), ("#8f8aff", "#5038e6")]

# which kind an app is, by words in its .desktop id, name or command
KINDS = [
    ("phone", ("ztphone", "dialer", "phone", "calls")),
    ("messages", ("message", "sms", "chat")),
    ("camera", ("camera", "megapixels", "snapshot")),
    ("settings", ("settings", "preferences", "control-center")),
    ("weather", ("weather",)),
    ("music", ("music", "rhythmbox", "lollypop")),
    ("files", ("files", "nautilus", "thunar", "file manager")),
    ("contacts", ("contacts", "people")),
    ("store", ("store", "software")),
    ("power", ("power",)),
    ("sound", ("sound", "volume", "pavucontrol", "audio")),
    ("devices", ("devices",)),
    ("scan", ("scan",)),
    ("editor", ("vim", "editor", "text")),
    ("terminal", ("terminal", "foot", "console")),
    ("welcome", ("welcome", "tour")),
    ("chip", ("osial",)),
    ("video", ("mpv", "video", "vidcap", "v4l2", "player")),
    ("android", ("waydroid", "android")),
    ("browser", ("firefox", "browser", "chromium", "epiphany", "web")),
    ("calendar", ("calendar",)),
    ("clock", ("clock", "alarm")),
]


def kind_of(app):
    hay = " ".join((app["key"], app["name"], app["command"])).lower()
    for kind, words in KINDS:
        if any(w in hay for w in words):
            return kind
    return None


def tint_of(app):
    kind = kind_of(app)
    if kind in TINTS:
        return TINTS[kind]
    h = int(hashlib.md5(app["name"].encode()).hexdigest(), 16)
    return SPARE[h % len(SPARE)]


# ---- shapes ----------------------------------------------------------------------------

def squircle(x, y, s):
    """A rounded square whose corners ease into its sides."""
    r, k = s * 0.24, s * 0.24 * 0.1
    p = QPainterPath()
    p.moveTo(x + r, y)
    p.lineTo(x + s - r, y)
    p.cubicTo(x + s - k, y, x + s, y + k, x + s, y + r)
    p.lineTo(x + s, y + s - r)
    p.cubicTo(x + s, y + s - k, x + s - k, y + s, x + s - r, y + s)
    p.lineTo(x + r, y + s)
    p.cubicTo(x + k, y + s, x, y + s - k, x, y + s - r)
    p.lineTo(x, y + r)
    p.cubicTo(x, y + k, x + k, y, x + r, y)
    p.closeSubpath()
    return p


def rounded(x, y, w, h, r):
    p = QPainterPath()
    p.addRoundedRect(QRectF(x, y, w, h), r, r)
    return p


def circle(cx, cy, r):
    p = QPainterPath()
    p.addEllipse(QPointF(cx, cy), r, r)
    return p


# ---- symbols, white, in a 100 x 100 box ------------------------------------------------

WHITE = QColor(255, 255, 255)


def fill(p, path, color=WHITE):
    p.fillPath(path, color)


def stroke(p, path, width, color=WHITE):
    pen = QPen(color, width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.strokePath(path, pen)


def sym_phone(p):
    s = QPainterPath()
    s.moveTo(31, 12)
    s.cubicTo(24, 12, 14, 18, 14, 30)
    s.cubicTo(14, 58, 42, 86, 70, 86)
    s.cubicTo(82, 86, 88, 76, 88, 69)
    s.lineTo(88, 64)
    s.quadTo(88, 60, 84, 58)
    s.lineTo(71, 52)
    s.quadTo(67, 50, 64, 53)
    s.lineTo(59, 58)
    s.cubicTo(50, 54, 46, 50, 42, 41)
    s.lineTo(47, 36)
    s.quadTo(50, 33, 48, 29)
    s.lineTo(42, 16)
    s.quadTo(40, 12, 36, 12)
    s.closeSubpath()
    fill(p, s)


def sym_messages(p):
    s = QPainterPath()
    s.addEllipse(QRectF(12, 16, 76, 60))
    tail = QPainterPath()
    tail.moveTo(24, 62)
    tail.quadTo(24, 80, 12, 86)
    tail.quadTo(34, 86, 44, 72)
    tail.closeSubpath()
    fill(p, s.united(tail))


def sym_camera(p):
    body = rounded(10, 30, 80, 52, 12).united(rounded(34, 20, 32, 16, 6))
    body = body.subtracted(circle(50, 56, 19)).united(circle(50, 56, 12))
    fill(p, body)


def sym_settings(p):
    gear = circle(50, 50, 30)
    for i in range(8):
        tooth = QPainterPath()
        tooth.addRoundedRect(QRectF(-8, -42, 16, 20), 4, 4)
        t = QTransform()
        t.translate(50, 50)
        t.rotate(i * 45)
        gear = gear.united(t.map(tooth))
    fill(p, gear.subtracted(circle(50, 50, 13)))


def sym_weather(p):
    sun = circle(38, 38, 17)
    fill(p, sun, QColor("#ffd84a"))
    cloud = circle(44, 64, 15).united(circle(62, 54, 19)).united(circle(78, 66, 12))
    cloud = cloud.united(rounded(30, 62, 56, 18, 9))
    fill(p, cloud)


def sym_music(p):
    beam = QPainterPath()
    beam.moveTo(36, 26)
    beam.lineTo(80, 14)
    beam.lineTo(80, 26)
    beam.lineTo(36, 38)
    beam.closeSubpath()
    notes = beam.united(rounded(36, 26, 8, 48, 3)).united(rounded(72, 14, 8, 50, 3))
    for cx, cy in ((30, 74), (66, 64)):
        head = QPainterPath()
        head.addEllipse(QRectF(-13, -9.5, 26, 19))
        t = QTransform()
        t.translate(cx, cy)
        t.rotate(-20)
        notes = notes.united(t.map(head))
    fill(p, notes)


def sym_files(p):
    fill(p, rounded(12, 22, 34, 16, 5).united(rounded(12, 28, 76, 50, 8)), QColor(255, 255, 255, 170))
    fill(p, rounded(12, 38, 76, 44, 8))


def sym_contacts(p):
    head = circle(50, 34, 16)
    shoulders = QPainterPath()
    shoulders.addEllipse(QRectF(20, 56, 60, 48))
    clip = QPainterPath()
    clip.addRect(QRectF(0, 0, 100, 84))
    fill(p, head.united(shoulders.intersected(clip)))


def sym_store(p):
    bag = rounded(20, 36, 60, 50, 9)
    handle = circle(50, 36, 15).subtracted(circle(50, 36, 9))
    top = QPainterPath()
    top.addRect(QRectF(0, 0, 100, 36))
    fill(p, bag.united(handle.intersected(top)))


def sym_power(p):
    shell = rounded(12, 32, 66, 36, 9).subtracted(rounded(18, 38, 54, 24, 5))
    fill(p, shell.united(rounded(80, 42, 7, 16, 3)).united(rounded(22, 42, 32, 16, 3)))


def sym_sound(p):
    cone = QPainterPath()
    cone.moveTo(16, 40)
    cone.lineTo(30, 40)
    cone.lineTo(50, 22)
    cone.lineTo(50, 78)
    cone.lineTo(30, 60)
    cone.lineTo(16, 60)
    cone.closeSubpath()
    fill(p, cone)
    for r in (14, 26):
        arc = QPainterPath()
        arc.arcMoveTo(QRectF(50 - r, 50 - r, 2 * r, 2 * r), -45)
        arc.arcTo(QRectF(50 - r, 50 - r, 2 * r, 2 * r), -45, 90)
        stroke(p, arc, 7)


def sym_devices(p):
    stroke(p, rounded(16, 18, 42, 64, 8), 7)
    fill(p, rounded(52, 38, 34, 46, 7))
    fill(p, rounded(30, 70, 14, 4, 2))


def sym_scan(p):
    path = QPainterPath()
    for x, y, dx, dy in ((18, 18, 1, 1), (82, 18, -1, 1), (18, 82, 1, -1), (82, 82, -1, -1)):
        path.moveTo(x, y + dy * 18)
        path.lineTo(x, y)
        path.lineTo(x + dx * 18, y)
    stroke(p, path, 8)
    line = QPainterPath()
    line.moveTo(30, 50)
    line.lineTo(70, 50)
    stroke(p, line, 7)


def sym_terminal(p):
    chevron = QPainterPath()
    chevron.moveTo(22, 32)
    chevron.lineTo(42, 50)
    chevron.lineTo(22, 68)
    stroke(p, chevron, 8)
    fill(p, rounded(50, 62, 28, 8, 4))


def sym_welcome(p):
    star = QPainterPath()
    star.moveTo(50, 10)
    star.quadTo(54, 46, 90, 50)
    star.quadTo(54, 54, 50, 90)
    star.quadTo(46, 54, 10, 50)
    star.quadTo(46, 46, 50, 10)
    small = QPainterPath()
    small.moveTo(78, 12)
    small.quadTo(80, 20, 88, 22)
    small.quadTo(80, 24, 78, 32)
    small.quadTo(76, 24, 68, 22)
    small.quadTo(76, 20, 78, 12)
    fill(p, star.united(small))


def sym_chip(p):
    body = rounded(26, 26, 48, 48, 8).subtracted(rounded(38, 38, 24, 24, 4))
    for i in range(3):
        o = 34 + i * 13
        for rect in ((o - 3, 12, 6, 14), (o - 3, 74, 6, 14), (12, o - 3, 14, 6), (74, o - 3, 14, 6)):
            body = body.united(rounded(*rect, 3))
    fill(p, body)


def sym_video(p):
    play = QPainterPath()
    play.moveTo(36, 24)
    play.lineTo(78, 50)
    play.lineTo(36, 76)
    play.closeSubpath()
    stroke(p, play, 10)
    fill(p, play)


def sym_android(p):
    head = QPainterPath()
    head.moveTo(18, 70)
    head.arcTo(QRectF(18, 34, 64, 72), 180, -180)
    head.closeSubpath()
    head = head.subtracted(circle(37, 56, 5)).subtracted(circle(63, 56, 5))
    fill(p, head)
    for x0, x1 in ((34, 26), (66, 74)):
        a = QPainterPath()
        a.moveTo(x0, 38)
        a.lineTo(x1, 24)
        stroke(p, a, 6)


def sym_editor(p):
    pencil = QPainterPath()
    pencil.moveTo(66, 16)
    pencil.lineTo(84, 34)
    pencil.lineTo(40, 78)
    pencil.lineTo(16, 84)
    pencil.lineTo(22, 60)
    pencil.closeSubpath()
    fill(p, pencil)
    cut = QPainterPath()
    cut.moveTo(58, 26)
    cut.lineTo(74, 42)
    stroke(p, cut, 5, QColor(0, 0, 0, 60))


def sym_browser(p):
    stroke(p, circle(50, 50, 34), 7)
    needle = QPainterPath()
    needle.moveTo(66, 34)
    needle.lineTo(56, 56)
    needle.lineTo(34, 66)
    needle.lineTo(44, 44)
    needle.closeSubpath()
    fill(p, needle)


def sym_calendar(p):
    f = QFont(FONT)
    f.setPixelSize(46)
    f.setWeight(QFont.DemiBold)
    p.setFont(f)
    p.setPen(WHITE)
    import time
    p.drawText(QRectF(0, 28, 100, 60), Qt.AlignCenter, str(time.localtime().tm_mday))
    f.setPixelSize(15)
    f.setWeight(QFont.Bold)
    p.setFont(f)
    p.drawText(QRectF(0, 12, 100, 20), Qt.AlignCenter, time.strftime("%a").upper())


def sym_clock(p):
    stroke(p, circle(50, 50, 34), 6)
    hands = QPainterPath()
    hands.moveTo(50, 26)
    hands.lineTo(50, 50)
    hands.lineTo(66, 60)
    stroke(p, hands, 6)


SYMBOLS = {
    "phone": sym_phone, "messages": sym_messages, "camera": sym_camera, "settings": sym_settings,
    "weather": sym_weather, "music": sym_music, "files": sym_files, "contacts": sym_contacts,
    "store": sym_store, "power": sym_power, "sound": sym_sound, "devices": sym_devices,
    "scan": sym_scan, "terminal": sym_terminal, "welcome": sym_welcome, "chip": sym_chip,
    "video": sym_video, "android": sym_android, "editor": sym_editor, "browser": sym_browser,
    "calendar": sym_calendar, "clock": sym_clock,
}

# ---- icons ----------------------------------------------------------------------------------

ICON_DIRS = ["/usr/share/icons/hicolor", "/usr/local/share/icons/hicolor",
             os.path.expanduser("~/.local/share/icons/hicolor")]


def own_icon(name, px):
    """The app's own icon, as an image of px, or None."""
    if not name:
        return None
    if os.path.isabs(name) and os.path.exists(name):
        icon = QIcon(name)
    else:
        icon = QIcon.fromTheme(name)
        if icon.isNull():
            for base in ICON_DIRS:
                for sub in ("scalable/apps", "512x512/apps", "256x256/apps", "128x128/apps", "64x64/apps", "48x48/apps"):
                    for ext in (".svg", ".png"):
                        path = os.path.join(base, sub, name + ext)
                        if os.path.exists(path):
                            icon = QIcon(path)
                            break
                    if not icon.isNull():
                        break
                if not icon.isNull():
                    break
            else:
                for ext in (".svg", ".png", ".xpm"):
                    path = "/usr/share/pixmaps/" + name + ext
                    if os.path.exists(path):
                        icon = QIcon(path)
                        break
    if icon.isNull():
        return None
    pixmap = icon.pixmap(px, px)
    return None if pixmap.isNull() else pixmap.toImage()


def paint_icon(app, px):
    img = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    shape = squircle(0, 0, px)
    kind = kind_of(app)
    top, bottom = tint_of(app)
    foreign = None if kind else own_icon(app["icon"], int(px * 0.7))
    if foreign is not None:
        top, bottom = "#fbfcff", "#dfe5ee"
    g = QLinearGradient(0, 0, px * 0.35, px)
    g.setColorAt(0, QColor(top))
    g.setColorAt(1, QColor(bottom))
    p.fillPath(shape, QBrush(g))
    p.save()
    p.setClipPath(shape)
    sheen = QLinearGradient(0, 0, 0, px * 0.62)
    sheen.setColorAt(0, QColor(255, 255, 255, 70))
    sheen.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(0, 0, px, px), QBrush(sheen))
    p.restore()
    # the symbol: a soft shadow, then white
    if kind:
        layer = QImage(px, px, QImage.Format_ARGB32_Premultiplied)
        layer.fill(Qt.transparent)
        q = QPainter(layer)
        q.setRenderHint(QPainter.Antialiasing)
        q.translate(px * 0.22, px * 0.22)
        q.scale(px * 0.56 / 100, px * 0.56 / 100)
        SYMBOLS[kind](q)
        q.end()
        shadow = QImage(layer)
        q = QPainter(shadow)
        q.setCompositionMode(QPainter.CompositionMode_SourceIn)
        q.fillRect(shadow.rect(), QColor(0, 0, 0, 45))
        q.end()
        p.drawImage(QPointF(0, px * 0.014), shadow)
        p.drawImage(QPointF(0, 0), layer)
    elif foreign is not None:
        o = (px - foreign.width()) / 2
        p.drawImage(QPointF(o, (px - foreign.height()) / 2), foreign)
    else:
        f = QFont(FONT)
        f.setPixelSize(int(px * 0.46))
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(WHITE)
        p.drawText(QRectF(0, 0, px, px * 0.98), Qt.AlignCenter, app["name"][:1].upper())
    # a hairline of light round the edge
    edge = QLinearGradient(0, 0, 0, px)
    edge.setColorAt(0, QColor(255, 255, 255, 120))
    edge.setColorAt(1, QColor(255, 255, 255, 25))
    pen = QPen(QBrush(edge), max(1.0, px / 120))
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    inset = pen.widthF() / 2
    p.drawPath(squircle(inset, inset, px - 2 * inset))
    p.end()
    return img


def icon_file(app, px):
    name = hashlib.md5(f"{VERSION}|{px}|{app['key']}|{app['name']}|{app['icon']}|{app['command']}".encode()).hexdigest()
    folder = CACHE / "icons"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (name + ".png")
    if kind_of(app) == "calendar":  # its day changes
        path = folder / (name + "-" + __import__("time").strftime("%Y%m%d") + ".png")
    if not path.exists():
        paint_icon(app, px).save(str(path))
    return str(path)


# ---- the wallpaper -------------------------------------------------------------------------

# soft lights over a deep blue: where, how big (of the height), what colour
LIGHTS = [
    (0.10, 0.10, 0.62, "#4f7dff", 235), (0.98, 0.26, 0.58, "#ff4f9a", 215),
    (0.48, 0.52, 0.42, "#8b5cff", 170), (0.04, 0.74, 0.60, "#12d6c0", 205),
    (0.92, 0.92, 0.58, "#ffa04a", 210), (0.60, 0.04, 0.30, "#58e1ff", 140),
]


def paint_wallpaper(w, h):
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    base = QLinearGradient(0, 0, w * 0.3, h)
    base.setColorAt(0, QColor("#0b1640"))
    base.setColorAt(1, QColor("#1c0b38"))
    p.fillRect(0, 0, w, h, QBrush(base))
    for fx, fy, fr, color, alpha in LIGHTS:
        c = QColor(color)
        r = fr * h
        g = QRadialGradient(QPointF(fx * w, fy * h), r)
        for at, a in ((0, 1.0), (0.35, 0.62), (0.7, 0.18), (1, 0)):
            c.setAlpha(int(alpha * a))
            g.setColorAt(at, c)
        p.fillRect(0, 0, w, h, QBrush(g))
    # a fine grain, so the gradients do not band
    tile = QImage(128, 128, QImage.Format_ARGB32_Premultiplied)
    rnd = random.Random(7)
    for y in range(128):
        for x in range(128):
            v = rnd.randint(0, 255)
            a = 9
            tile.setPixelColor(x, y, QColor(v, v, v, a))
    p.fillRect(0, 0, w, h, QBrush(tile))
    p.end()
    return img


def blur(img, factor=24):
    """Soft: down to a 24th, and smoothly up again, twice."""
    w, h = img.width(), img.height()
    small = img.scaled(max(4, w // factor), max(4, h // factor), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    small = small.scaled(max(4, w // (factor // 2)), max(4, h // (factor // 2)), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    small = small.scaled(max(4, w // factor), max(4, h // factor), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return small.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)


def wallpapers(w, h, photo=None):
    """(wallpaper, blurred) files for a screen of w x h pixels."""
    CACHE.mkdir(parents=True, exist_ok=True)
    src = photo if photo and os.path.exists(photo) else None
    sig = f"{VERSION}|{w}x{h}|{src}|{os.path.getmtime(src) if src else 0}"
    name = hashlib.md5(sig.encode()).hexdigest()[:12]
    sharp, soft = CACHE / f"wall-{name}.png", CACHE / f"wall-{name}-blur.png"
    if not sharp.exists() or not soft.exists():
        if src:
            photo_img = QImage(src)
            img = photo_img.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            img = img.copy((img.width() - w) // 2, (img.height() - h) // 2, w, h)
        else:
            img = paint_wallpaper(w, h)
        img.save(str(sharp))
        blur(img).save(str(soft))
    return str(sharp), str(soft)


# ---- glass -------------------------------------------------------------------------------------

def paint_glass(blurred, x, y, w, h, r, dpr, tint, dark):
    """A panel of glass at (x, y) points: the blurred wallpaper under it, a
    light (or dark) frost, a sheen from above and a rim of light."""
    pw, ph = max(1, int(round(w * dpr))), max(1, int(round(h * dpr)))
    img = QImage(pw, ph, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    p.scale(dpr, dpr)
    shape = rounded(0, 0, w, h, r)
    p.setClipPath(shape)
    if blurred is not None:
        p.drawImage(QRectF(-x, -y, blurred.width() / dpr, blurred.height() / dpr), blurred)
    p.fillPath(shape, QColor(0, 0, 0, int(255 * tint)) if dark else QColor(255, 255, 255, int(255 * tint)))
    sheen = QLinearGradient(0, 0, 0, h)
    sheen.setColorAt(0, QColor(255, 255, 255, 46))
    sheen.setColorAt(0.45, QColor(255, 255, 255, 0))
    sheen.setColorAt(1, QColor(255, 255, 255, 14))
    p.fillPath(shape, QBrush(sheen))
    p.setClipping(False)
    rim = QLinearGradient(0, 0, w * 0.6, h)
    rim.setColorAt(0, QColor(255, 255, 255, 190))
    rim.setColorAt(0.5, QColor(255, 255, 255, 50))
    rim.setColorAt(1, QColor(255, 255, 255, 110))
    p.setPen(QPen(QBrush(rim), 1.0))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), r - 0.5, r - 0.5)
    p.end()
    return img


class Glass:
    def __init__(self):
        self.blurred = None
        self.blur_path = None
        self.dpr = 1.0

    def use(self, blur_path, dpr):
        if blur_path != self.blur_path:
            self.blur_path = blur_path
            self.blurred = QImage(blur_path)
        self.dpr = dpr

    def file(self, x, y, w, h, r, tint=0.16, dark=False):
        if w <= 0 or h <= 0:
            return ""
        sig = f"{VERSION}|{self.blur_path}|{x:.1f},{y:.1f},{w:.1f},{h:.1f},{r:.1f}|{self.dpr}|{tint}|{dark}"
        name = hashlib.md5(sig.encode()).hexdigest()[:16]
        folder = CACHE / "glass"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + ".png")
        if not path.exists():
            paint_glass(self.blurred, x, y, w, h, r, self.dpr, tint, dark).save(str(path))
        return str(path)
