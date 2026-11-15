"""Weather: ztOS's weather app. The weather now, by the hour and for ten days
for the places you keep, from Open-Meteo; and a live Start tile that a
systemd user timer keeps current while the app is closed (`--tile`)."""
import datetime
import os
import queue
import subprocess
import sys
import threading

import forecast

APP_ID = "os.ztos.weather"
DATA = os.path.expanduser(f"~/.local/share/ztos/data/{APP_ID}")
TILE_PNG = os.path.join(DATA, "tile.png")
UNIT_DIR = os.path.expanduser("~/.config/systemd/user")
UNIT = "ztos-weather-tile"


# ---- what the app keeps ---------------------------------------------------------

def _store(name):
    import ztos
    return ztos.store(name)


def current_place(settings):
    places = settings.get("places") or []
    if not places:
        return None
    i = settings.get("current", 0)
    return places[i if 0 <= i < len(places) else 0]


def cache_key(place) -> str:
    return f"{place['latitude']},{place['longitude']}"


# ---- the live tile ----------------------------------------------------------------

def publish_tile(place, data):
    """The tile's back: the temperature large, the sky, high and low, feels like;
    the glyph dimmed behind (medium) or beside (wide) them."""
    import ztos
    import glyphs
    c = data.get("current") or {}
    today = (forecast.days(data) or [None])[0]
    os.makedirs(DATA, exist_ok=True)
    try:
        glyphs.image(forecast.kind(c.get("weather_code")), bool(c.get("is_day", 1)), 256).save(TILE_PNG)
        image = TILE_PNG
    except Exception:
        image = ""
    lines = [forecast.condition(c.get("weather_code"))]
    if today:
        lines.append(f"↑{forecast.deg(today[1])}  ↓{forecast.deg(today[2])}")
    lines.append(f"feels {forecast.deg(c.get('apparent_temperature'))}")
    ztos.tile_update(place["name"], lines, value=forecast.deg(c.get("temperature_2m")), image=image)


def app_binary() -> str:
    """This app's installed binary, for the timer (as a system app or the user's)."""
    for path in (sys.argv[0], f"/usr/local/lib/ztos/apps/{APP_ID}",
                 os.path.expanduser(f"~/.local/share/ztos/apps/{APP_ID}")):
        if path and os.path.basename(path) == APP_ID and os.access(path, os.X_OK):
            return os.path.abspath(path)
    return ""


def set_timer(on: bool):
    """Every 30 minutes (and 2 minutes after a start), `--tile` refreshes the
    tile with the app closed. A user unit the app writes itself."""
    binary = app_binary()
    if on and binary:
        os.makedirs(UNIT_DIR, exist_ok=True)
        with open(os.path.join(UNIT_DIR, UNIT + ".service"), "w") as f:
            f.write("[Unit]\nDescription=ztOS Weather: refresh the live tile\n"
                    "After=network-online.target\n\n[Service]\nType=oneshot\n"
                    "Environment=ZTOS_ZYGOTE=0 QT_QPA_PLATFORM=offscreen\n"
                    f"ExecStart={binary} --tile\n")
        with open(os.path.join(UNIT_DIR, UNIT + ".timer"), "w") as f:
            f.write("[Unit]\nDescription=ztOS Weather: refresh the live tile every 30 minutes\n\n"
                    "[Timer]\nOnBootSec=2min\nOnUnitActiveSec=30min\n\n[Install]\nWantedBy=timers.target\n")
        cmds = [["systemctl", "--user", "daemon-reload"], ["systemctl", "--user", "enable", "--now", UNIT + ".timer"]]
    else:
        cmds = [["systemctl", "--user", "disable", "--now", UNIT + ".timer"]]
    for cmd in cmds:
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass


def tile_only() -> int:
    """`--tile`: fetch the current place's weather and update the tile, no window."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtGui import QGuiApplication
    QGuiApplication.instance() or QGuiApplication(sys.argv[:1])
    import ztos
    settings = ztos.store("settings")
    place = current_place(settings)
    if not place or settings.get("tile", True) is False:
        return 0
    fahrenheit = bool(settings.get("fahrenheit"))
    cache = ztos.store("cache")
    try:
        data = forecast.fetch(place, fahrenheit)
    except Exception as e:      # offline: the tile keeps what it showed
        print("weather: tile refresh failed:", e)
        return 1
    cache[cache_key(place)] = data
    cache.save()
    publish_tile(place, data)
    return 0


if __name__ == "__main__" and "--tile" in sys.argv:
    sys.exit(tile_only())


# ---- the app ------------------------------------------------------------------------

import ztos                                             # noqa: E402
import glyphs                                           # noqa: E402
from PySide6.QtCore import QRectF, QTimer, Qt           # noqa: E402
from PySide6.QtGui import QColor, QFont, QPainter       # noqa: E402
from PySide6.QtWidgets import QSizePolicy, QWidget      # noqa: E402

app = ztos.App()
WHITE = QColor("white")


def font(families, size) -> QFont:
    f = QFont()
    f.setFamilies(families)
    f.setPixelSize(int(size))
    return f


class Jobs:
    """Network work off the UI thread; results come back on it (polled while any
    is out, so nothing crosses threads but a queue)."""

    def __init__(self):
        self.q = queue.Queue()
        self.out = 0
        self.timer = QTimer(interval=80)
        self.timer.timeout.connect(self._poll)

    def run(self, work, done):
        def go():
            try:
                self.q.put((done, work(), None))
            except Exception as e:
                self.q.put((done, None, e))
        self.out += 1
        threading.Thread(target=go, daemon=True).start()
        self.timer.start()

    def _poll(self):
        while not self.q.empty():
            done, result, error = self.q.get()
            self.out -= 1
            done(result, error)
        if self.out <= 0:
            self.timer.stop()


jobs = Jobs()


class NowView(QWidget):
    """The top of "now": the place, the sky as a glyph, the temperature large,
    what it is like, and when it was fetched."""

    def __init__(self, place, data):
        super().__init__()
        self.place, self.data = place, data
        self.setFixedHeight(280)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w = self.width()
        c = self.data.get("current") or {}
        today = (forecast.days(self.data) or [None])[0]
        p.setPen(WHITE)
        p.setFont(font(ztos.FONT_SEMILIGHT, 24))
        p.drawText(QRectF(0, 0, w, 32), Qt.AlignLeft | Qt.AlignVCenter, self.place["name"])
        p.setPen(ztos.GREY)
        p.setFont(font(ztos.FONT_REGULAR, 14))
        p.drawText(QRectF(0, 32, w, 20), Qt.AlignLeft | Qt.AlignVCenter, forecast.place_detail(self.place))
        glyphs.draw(p, forecast.kind(c.get("weather_code")), bool(c.get("is_day", 1)), QRectF(0, 62, 120, 120))
        p.setPen(WHITE)
        p.setFont(font(ztos.FONT_LIGHT, 96))
        p.drawText(QRectF(132, 52, w - 132, 130), Qt.AlignLeft | Qt.AlignVCenter,
                   forecast.deg(c.get("temperature_2m")))
        p.setFont(font(ztos.FONT_SEMILIGHT, 24))
        p.drawText(QRectF(0, 192, w, 32), Qt.AlignLeft | Qt.AlignVCenter, forecast.condition(c.get("weather_code")))
        p.setPen(ztos.GREY)
        p.setFont(font(ztos.FONT_REGULAR, 16))
        hi_lo = f"↑{forecast.deg(today[1])}   ↓{forecast.deg(today[2])}   " if today else ""
        p.drawText(QRectF(0, 224, w, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{hi_lo}feels like {forecast.deg(c.get('apparent_temperature'))}")
        fetched = datetime.datetime.fromtimestamp(self.data.get("fetched", 0)).strftime("%H:%M")
        p.setFont(font(ztos.FONT_REGULAR, 13))
        p.drawText(QRectF(0, 250, w, 20), Qt.AlignLeft | Qt.AlignVCenter, f"updated {fetched}")
        p.end()


class Row(QWidget):
    """One line of the hourly or daily list: a caption (and a grey line under
    it), the glyph, and figures on the right."""

    def __init__(self, caption, sub, kind, day, right, right_sub, height=64):
        super().__init__()
        self.args = (caption, sub, kind, day, right, right_sub)
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, _):
        caption, sub, kind, day, right, right_sub = self.args
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        top = 6 if sub else (h - 30) / 2
        p.setPen(WHITE)
        p.setFont(font(ztos.FONT_SEMILIGHT, 22))
        p.drawText(QRectF(0, top, 150, 30), Qt.AlignLeft | Qt.AlignVCenter, caption)
        if sub:
            p.setPen(ztos.GREY)
            p.setFont(font(ztos.FONT_REGULAR, 14))
            p.drawText(QRectF(0, top + 30, 170, 20), Qt.AlignLeft | Qt.AlignVCenter, sub)
        glyphs.draw(p, kind, day, QRectF(160, (h - 42) / 2, 42, 42))
        p.setPen(WHITE)
        p.setFont(font(ztos.FONT_SEMILIGHT, 22))
        p.drawText(QRectF(210, top, w - 210, 30), Qt.AlignRight | Qt.AlignVCenter, right)
        if right_sub:
            p.setPen(ztos.GREY)
            p.setFont(font(ztos.FONT_REGULAR, 14))
            p.drawText(QRectF(210, top + 30, w - 210, 20), Qt.AlignRight | Qt.AlignVCenter, right_sub)
        p.end()


def hh(iso: str) -> str:
    return iso[11:16] if len(iso) >= 16 else "—"


def day_name(iso: str, i: int) -> str:
    if i == 0:
        return "today"
    if i == 1:
        return "tomorrow"
    try:
        return datetime.date.fromisoformat(iso).strftime("%a %d").lower()
    except ValueError:
        return iso


def rain(pct) -> str:
    return "" if pct is None else f"rain {round(pct)}%"


class Weather:
    def __init__(self):
        self.settings = ztos.store("settings")
        self.cache = ztos.store("cache")
        self.now = ztos.Page("now")
        self.hourly = ztos.Page("hourly")
        self.daily = ztos.Page("10 days")
        self.places = ztos.Page("places")
        self.pivot = ztos.Pivot([self.now, self.hourly, self.daily, self.places])
        self.pivot.bar(ztos.RoundButton("refresh", "refresh", lambda: self.load(force=True)),
                       ztos.RoundButton("add", "add place", self.add_place))
        self.loading = False

    # -- data --
    @property
    def fahrenheit(self) -> bool:
        return bool(self.settings.get("fahrenheit"))

    def load(self, force=False):
        place = current_place(self.settings)
        self.show()
        if not place or self.loading:
            return
        data = self.cache.get(cache_key(place))
        if not force and data and forecast.fresh(data, self.fahrenheit):
            return
        self.loading = True
        for page in (self.now, self.hourly, self.daily):
            page.busy(True)
        jobs.run(lambda: forecast.fetch(place, self.fahrenheit), lambda d, e: self.loaded(place, d, e))

    def loaded(self, place, data, error):
        self.loading = False
        for page in (self.now, self.hourly, self.daily):
            page.busy(False)
        if error is not None:
            if not self.cache.get(cache_key(place)):
                ztos.message("No weather", "The forecast could not be fetched. Is the phone online?", ["ok"])
            return
        self.cache[cache_key(place)] = data
        self.cache.save()
        if self.settings.get("tile", True) and place == current_place(self.settings):
            publish_tile(place, data)
        self.show()

    # -- pages --
    def show(self):
        place = current_place(self.settings)
        data = self.cache.get(cache_key(place)) if place else None
        for page in (self.now, self.hourly, self.daily):
            page.clear()
        if not place:
            self.now.text("Keep a place to see its weather.", size=17)
            self.now.space(8)
            self.now.entry("add a place", "search by name", self.add_place)
        elif not data:
            self.now.text(f"Fetching the weather for {place['name']}...", size=17)
        else:
            self.show_now(place, data)
            self.show_hourly(data)
            self.show_daily(data)
        self.show_places()

    def show_now(self, place, data):
        c = data.get("current") or {}
        units = data.get("current_units") or {}
        today = (forecast.days(data) or [None])[0]
        self.now.add(NowView(place, data))
        self.now.section("details")
        self.now.entry("humidity", f"{c.get('relative_humidity_2m', '—')}%")
        self.now.entry("wind", f"{round(c.get('wind_speed_10m') or 0)} {units.get('wind_speed_10m', '')} "
                               f"from the {forecast.compass(c.get('wind_direction_10m'))}")
        self.now.entry("pressure", f"{round(c.get('surface_pressure') or 0)} hPa")
        self.now.entry("precipitation", f"{c.get('precipitation', 0)} {units.get('precipitation', 'mm')} now")
        if today:
            self.now.entry("chance of rain today", f"{round(today[4] or 0)}%")
            self.now.entry("UV index", f"{round(today[8] or 0)}")
            self.now.entry("sunrise", hh(today[6]))
            self.now.entry("sunset", hh(today[7]))

    def show_hourly(self, data):
        for t, temp, pct, code, day in forecast.hours_ahead(data, 24):
            self.hourly.add(Row(hh(t), forecast.condition(code).lower(), forecast.kind(code), bool(day),
                                forecast.deg(temp), rain(pct)))

    def show_daily(self, data):
        for i, (d, hi, lo, code, pct, amount, rise, sset, uv) in enumerate(forecast.days(data)):
            self.daily.add(Row(day_name(d, i), forecast.condition(code).lower(), forecast.kind(code), True,
                               f"{forecast.deg(hi)} / {forecast.deg(lo)}", rain(pct), height=72))

    def show_places(self):
        page = self.places
        page.clear()
        places = self.settings.get("places") or []
        here = current_place(self.settings)
        for i, place in enumerate(places):
            data = self.cache.get(cache_key(place)) or {}
            c = data.get("current") or {}
            detail = forecast.place_detail(place)
            if c:
                detail = f"{forecast.deg(c.get('temperature_2m'))} {forecast.condition(c.get('weather_code')).lower()}" \
                         + (f" · {detail}" if detail else "")
            title = place["name"] + ("  •" if place == here else "")
            rows = {}
            rows[i] = page.entry(title, detail, lambda i=i: self.choose(i),
                                 lambda i=i, rows=rows: ztos.menu(rows[i], [("remove", lambda: self.remove(i))]))
        page.entry("add a place", "search by name", self.add_place)
        page.section("settings")
        page.toggle("Fahrenheit and mph", self.fahrenheit, self.set_fahrenheit)
        page.toggle("Live tile", self.settings.get("tile", True), self.set_tile)
        page.space(12)
        page.text("Weather data by Open-Meteo.com (CC BY 4.0).", size=13, color=ztos.GREY)

    # -- places --
    def add_place(self):
        app.push(Search(self))

    def keep(self, place):
        places = self.settings.setdefault("places", [])
        for i, p in enumerate(places):
            if cache_key(p) == cache_key(place):
                self.settings["current"] = i
                break
        else:
            places.append(place)
            self.settings["current"] = len(places) - 1
        self.settings.save()
        if self.settings.get("tile", True):
            set_timer(True)
        self.pivot.turn(0)
        self.load(force=False)

    def choose(self, i):
        self.settings["current"] = i
        self.settings.save()
        self.pivot.turn(0, forward=False)
        self.load()

    def remove(self, i):
        places = self.settings.get("places") or []
        if 0 <= i < len(places):
            gone = places.pop(i)
            self.cache.pop(cache_key(gone), None)
            self.cache.save()
            cur = self.settings.get("current", 0)
            self.settings["current"] = max(0, cur - 1) if i <= cur else cur
            self.settings.save()
            if not places:
                ztos.tile_clear()
                set_timer(False)
        self.load()

    # -- settings --
    def set_fahrenheit(self, on):
        self.settings["fahrenheit"] = bool(on)
        self.settings.save()
        self.load(force=True)

    def set_tile(self, on):
        self.settings["tile"] = bool(on)
        self.settings.save()
        set_timer(on and bool(self.settings.get("places")))
        if not on:
            ztos.tile_clear()
        else:
            place = current_place(self.settings)
            data = self.cache.get(cache_key(place)) if place else None
            if data:
                publish_tile(place, data)


class Search(ztos.Page):
    """Add a place: a name, then the places of that name to choose from."""

    def __init__(self, weather):
        super().__init__("add a place")
        self.weather = weather
        self.box = self.textbox("city or town", on_submit=self.find, placeholder="e.g. Munich")
        self.section("places")
        self.note = self.text("Type a name and press enter.", size=15, color=ztos.GREY)
        self.rows = []

    def find(self, *_):
        name = self.box.text().strip()
        if len(name) < 2:
            return
        self.busy(True)
        jobs.run(lambda: forecast.search(name), self.found)

    def found(self, results, error):
        self.busy(False)
        for row in self.rows:
            row.hide()
            row.deleteLater()
        self.rows = []
        if error is not None:
            self.note.setText("No connection: the places could not be looked up.")
            return
        self.note.setText("" if results else "No place of that name.")
        self.note.setVisible(not results)
        for place in results:
            self.rows.append(self.entry(place["name"], forecast.place_detail(place),
                                        lambda place=place: self.pick(place)))

    def pick(self, place):
        app.pop()
        self.weather.keep(place)


weather = Weather()
QTimer.singleShot(0, weather.load)
app.run(weather.pivot)
