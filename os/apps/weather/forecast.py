"""Weather data for ztOS Weather: Open-Meteo (https://open-meteo.com), free,
no key, CC BY 4.0 (the app says where the data comes from), and the WMO
weather codes it reports. No Qt here: the tile refresh runs it headless."""
import json
import time
import urllib.parse
import urllib.request

FORECAST = "https://api.open-meteo.com/v1/forecast"
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
AGENT = {"User-Agent": "ztOS-Weather/1.0"}
FRESH_S = 20 * 60          # data younger than this is not fetched again on its own

# WMO weather interpretation codes (Open-Meteo's table)
CONDITIONS = {
    0: "Clear", 1: "Mostly clear", 2: "Partly cloudy", 3: "Cloudy",
    45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm, hail", 99: "Thunderstorm, hail",
}


def condition(code) -> str:
    return CONDITIONS.get(int(code or 0), "—")


def kind(code) -> str:
    """Which glyph draws this code."""
    c = int(code or 0)
    if c == 0:
        return "clear"
    if c in (1, 2):
        return "partly"
    if c == 3:
        return "cloudy"
    if c in (45, 48):
        return "fog"
    if c in (51, 53, 55, 56, 57):
        return "drizzle"
    if c in (61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if c in (71, 73, 75, 77, 85, 86):
        return "snow"
    if c in (95, 96, 99):
        return "thunder"
    return "cloudy"


def compass(degrees) -> str:
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return names[int(((degrees or 0) % 360) / 45 + 0.5) % 8]


def _get(url: str, params: dict, timeout: float = 15.0) -> dict:
    full = url + "?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(urllib.request.Request(full, headers=AGENT), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def search(name: str, language: str = "en") -> list:
    """Places called `name`: [{name, region, country, latitude, longitude}]."""
    name = name.strip()
    if len(name) < 2:
        return []
    data = _get(GEOCODE, {"name": name, "count": 10, "language": language, "format": "json"})
    out = []
    for r in data.get("results") or []:
        out.append({
            "name": r.get("name", ""),
            "region": r.get("admin1", ""),
            "country": r.get("country", ""),
            "latitude": round(float(r["latitude"]), 4),
            "longitude": round(float(r["longitude"]), 4),
        })
    return out


def place_detail(place: dict) -> str:
    return ", ".join(x for x in (place.get("region"), place.get("country")) if x)


def fetch(place: dict, fahrenheit: bool = False) -> dict:
    """The forecast for `place`, as Open-Meteo sends it, with `fetched` (unix
    time) and the units it was asked in."""
    params = {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,is_day,precipitation,"
                   "weather_code,surface_pressure,wind_speed_10m,wind_direction_10m",
        "hourly": "temperature_2m,precipitation_probability,weather_code,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max,"
                 "precipitation_probability_max,precipitation_sum",
        "timezone": "auto",
        "forecast_days": 10,
        "temperature_unit": "fahrenheit" if fahrenheit else "celsius",
        "wind_speed_unit": "mph" if fahrenheit else "kmh",
        "precipitation_unit": "inch" if fahrenheit else "mm",
    }
    data = _get(FORECAST, params)
    data["fetched"] = time.time()
    data["fahrenheit"] = fahrenheit
    return data


def fresh(data: dict, fahrenheit: bool) -> bool:
    return bool(data) and data.get("fahrenheit") == fahrenheit and time.time() - data.get("fetched", 0) < FRESH_S


def deg(value) -> str:
    return "—" if value is None else f"{round(value)}°"


def hours_ahead(data: dict, count: int = 24) -> list:
    """The next `count` hours from now: [(iso time, temp, rain %, code, is_day)]."""
    h = data.get("hourly") or {}
    times = h.get("time") or []
    now = (data.get("current") or {}).get("time", "")[:13]      # "2026-11-15T14"
    start = next((i for i, t in enumerate(times) if t[:13] >= now), 0)
    rows = []
    for i in range(start, min(start + count, len(times))):
        rows.append((times[i], h["temperature_2m"][i], (h.get("precipitation_probability") or [None] * len(times))[i],
                     h["weather_code"][i], h.get("is_day", [1] * len(times))[i]))
    return rows


def days(data: dict) -> list:
    """[(iso date, max, min, code, rain %, rain amount, sunrise, sunset, uv)]."""
    d = data.get("daily") or {}
    out = []
    for i, day in enumerate(d.get("time") or []):
        out.append((day, d["temperature_2m_max"][i], d["temperature_2m_min"][i], d["weather_code"][i],
                    (d.get("precipitation_probability_max") or [None] * 99)[i],
                    (d.get("precipitation_sum") or [None] * 99)[i],
                    (d.get("sunrise") or [""] * 99)[i], (d.get("sunset") or [""] * 99)[i],
                    (d.get("uv_index_max") or [None] * 99)[i]))
    return out
