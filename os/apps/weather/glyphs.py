"""The weather glyphs: white line drawings in the Metro manner (one stroke
width, round ends), drawn with QPainter at any size. `kind` is what
forecast.kind() returns; at night the sun is a moon."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen


def _pen(color: QColor, w: float) -> QPen:
    pen = QPen(color, w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _sun(p: QPainter, cx: float, cy: float, r: float, w: float):
    p.drawEllipse(QPointF(cx, cy), r, r)
    for i in range(8):
        a = i * math.pi / 4
        p.drawLine(QPointF(cx + math.cos(a) * r * 1.45, cy + math.sin(a) * r * 1.45),
                   QPointF(cx + math.cos(a) * r * 1.9, cy + math.sin(a) * r * 1.9))


def _moon(p: QPainter, cx: float, cy: float, r: float):
    outer = QPainterPath()
    outer.addEllipse(QPointF(cx, cy), r, r)
    bite = QPainterPath()
    bite.addEllipse(QPointF(cx + r * 0.55, cy - r * 0.35), r * 0.85, r * 0.85)
    p.drawPath(outer.subtracted(bite))


def _cloud(p: QPainter, x: float, y: float, w: float, h: float):
    """A cloud filling the box (x, y, w, h): a flat base and three humps."""
    path = QPainterPath()
    base = y + h
    path.moveTo(x + w * 0.18, base)
    path.arcTo(QRectF(x, y + h * 0.42, w * 0.36, h * 0.58), 270, -180)
    path.arcTo(QRectF(x + w * 0.16, y + h * 0.08, w * 0.42, h * 0.62), 180, -140)
    path.arcTo(QRectF(x + w * 0.42, y, w * 0.44, h * 0.66), 150, -150)
    path.arcTo(QRectF(x + w * 0.66, y + h * 0.38, w * 0.34, h * 0.62), 90, -180)
    path.closeSubpath()
    p.drawPath(path)


def draw(p: QPainter, kind: str, day: bool, rect: QRectF, color: QColor = QColor("white")):
    """The glyph for `kind` inside `rect` (square works best)."""
    s = min(rect.width(), rect.height())
    x0 = rect.center().x() - s / 2
    y0 = rect.center().y() - s / 2
    w = max(1.2, s * 0.045)
    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(_pen(color, w))
    p.setBrush(Qt.NoBrush)
    if kind == "clear":
        if day:
            _sun(p, x0 + s / 2, y0 + s / 2, s * 0.2, w)
        else:
            _moon(p, x0 + s * 0.48, y0 + s / 2, s * 0.3)
        p.restore()
        return
    cloud_top = y0 + s * 0.3
    if kind == "partly":
        if day:
            _sun(p, x0 + s * 0.36, y0 + s * 0.34, s * 0.13, w)
        else:
            _moon(p, x0 + s * 0.36, y0 + s * 0.34, s * 0.19)
        p.setBrush(QColor(0, 0, 0))     # the cloud covers the sun's lower right
        _cloud(p, x0 + s * 0.3, y0 + s * 0.4, s * 0.62, s * 0.38)
        p.restore()
        return
    if kind in ("cloudy", "fog"):
        _cloud(p, x0 + s * 0.12, y0 + s * 0.24, s * 0.76, s * 0.44)
        if kind == "fog":
            for k, (a, b) in enumerate(((0.14, 0.86), (0.24, 0.76))):
                yy = y0 + s * (0.78 + 0.1 * k)
                p.drawLine(QPointF(x0 + s * a, yy), QPointF(x0 + s * b, yy))
        p.restore()
        return
    # cloud with something falling from it
    _cloud(p, x0 + s * 0.12, y0 + s * 0.14, s * 0.76, s * 0.42)
    base = y0 + s * 0.66
    if kind in ("rain", "drizzle"):
        n = 3 if kind == "rain" else 2
        for k in range(n):
            xx = x0 + s * (0.34 + 0.16 * k if n == 3 else 0.42 + 0.16 * k)
            length = s * (0.2 if kind == "rain" else 0.1)
            p.drawLine(QPointF(xx, base), QPointF(xx - length * 0.35, base + length))
    elif kind == "snow":
        for k in range(3):
            cx, cy = x0 + s * (0.32 + 0.18 * k), base + s * (0.08 if k != 1 else 0.17)
            r = s * 0.05
            for a in (0, 60, 120):
                t = math.radians(a)
                p.drawLine(QPointF(cx - math.cos(t) * r, cy - math.sin(t) * r),
                           QPointF(cx + math.cos(t) * r, cy + math.sin(t) * r))
    elif kind == "thunder":
        bolt = [(0.54, 0.0), (0.42, 0.14), (0.53, 0.14), (0.44, 0.3)]
        path = QPainterPath(QPointF(x0 + s * bolt[0][0], base + s * bolt[0][1]))
        for bx, by in bolt[1:]:
            path.lineTo(x0 + s * bx, base + s * by)
        p.drawPath(path)
    p.restore()


def image(kind: str, day: bool, size: int = 256, color: QColor = QColor("white")) -> QImage:
    """The glyph alone on a transparent square, for the live tile."""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    draw(p, kind, day, QRectF(size * 0.08, size * 0.08, size * 0.84, size * 0.84), color)
    p.end()
    return img
