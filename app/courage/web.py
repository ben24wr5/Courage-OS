"""Live info from free services (no extra keys): pictures, weather, news, radio."""
import time
import xml.etree.ElementTree as ET

import requests

UA = {"User-Agent": "CourageOS/1.0 (home project)"}
_cache = {}


def _cached(key, seconds, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < seconds:
        return hit[1]
    try:
        val = fn()
    except Exception as e:
        print("web error", key, e, flush=True)
        val = hit[1] if hit else None
    _cache[key] = (time.time(), val)
    return val


def online():
    try:
        requests.head("https://generativelanguage.googleapis.com", timeout=3, headers=UA)
        return True
    except Exception:
        return False


def picture(query):
    """Find a matching photo on Wikimedia Commons. Returns an image URL or None."""
    if not query:
        return None

    def go():
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=8, params={
            "action": "query", "format": "json", "generator": "search", "gsrsearch": f"filetype:bitmap {query}",
            "gsrnamespace": 6, "gsrlimit": 5, "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": 900})
        pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
        for p in pages:
            info = (p.get("imageinfo") or [{}])[0]
            if info.get("mime") in ("image/jpeg", "image/png") and info.get("thumburl"):
                return info["thumburl"]
        return None
    return _cached("pic:" + query.lower(), 3600, go)


CODES = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "fog", 48: "fog", 51: "drizzle",
         53: "drizzle", 55: "drizzle", 61: "light rain", 63: "rain", 65: "heavy rain", 71: "light snow", 73: "snow",
         75: "heavy snow", 80: "showers", 81: "showers", 82: "heavy showers", 95: "thunderstorms"}


def weather(city):
    if not city:
        return "unknown (no town set yet; ask them where they live)"

    def go():
        g = requests.get("https://geocoding-api.open-meteo.com/v1/search", headers=UA, timeout=8,
                         params={"name": city, "count": 1}).json()["results"][0]
        w = requests.get("https://api.open-meteo.com/v1/forecast", headers=UA, timeout=8, params={
            "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto",
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "forecast_days": 2}).json()
        c, d = w["current"], w["daily"]
        return (f"now {round(c['temperature_2m'])}C and {CODES.get(c['weather_code'], 'mixed')}, wind "
                f"{round(c['wind_speed_10m'])} km/h. Today {round(d['temperature_2m_min'][0])}-"
                f"{round(d['temperature_2m_max'][0])}C, {d['precipitation_probability_max'][0]}% chance of rain. "
                f"Tomorrow {round(d['temperature_2m_min'][1])}-{round(d['temperature_2m_max'][1])}C, "
                f"{CODES.get(d['weather_code'][1], 'mixed')}.")
    return _cached("wx:" + city.lower(), 1800, go) or "unavailable right now"


def news():
    def go():
        r = requests.get("https://feeds.bbci.co.uk/news/rss.xml", headers=UA, timeout=8)
        items = ET.fromstring(r.content).findall(".//item/title")
        return "; ".join(i.text for i in items[:6])
    return _cached("news", 1800, go) or "unavailable right now"


def radio_station(query):
    """Find a live radio stream URL on radio-browser.info."""
    def go():
        r = requests.get("https://de1.api.radio-browser.info/json/stations/search", headers=UA, timeout=8,
                         params={"name": query, "limit": 5, "order": "clickcount", "reverse": "true",
                                 "hidebroken": "true"}).json()
        if not r:
            r = requests.get("https://de1.api.radio-browser.info/json/stations/search", headers=UA, timeout=8,
                             params={"tag": query, "limit": 5, "order": "clickcount", "reverse": "true",
                                     "hidebroken": "true"}).json()
        return (r[0]["name"].strip(), r[0]["url_resolved"]) if r else None
    return _cached("radio:" + query.lower(), 3600, go)
