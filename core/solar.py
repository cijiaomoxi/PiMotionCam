"""NOAA approximate solar times, civil twilight and signed minute offsets.

Equations: https://gml.noaa.gov/grad/solcalc/solareqns.PDF
Operational schedules only; refraction/weather and polar limits affect times.
"""

from __future__ import annotations
import calendar
import math
import re
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def solar_times(day, latitude, longitude, zone=""):
    lat, lon = float(latitude), float(longitude)
    if not (-89.9 <= lat <= 89.9 and -180 <= lon <= 180):
        raise ValueError("Latitude or longitude is outside its range")
    g = (
        2
        * math.pi
        / (366 if calendar.isleap(day.year) else 365)
        * (day.timetuple().tm_yday - 1)
    )
    eq = 229.18 * (
        0.000075
        + 0.001868 * math.cos(g)
        - 0.032077 * math.sin(g)
        - 0.014615 * math.cos(2 * g)
        - 0.040849 * math.sin(2 * g)
    )
    dec = (
        0.006918
        - 0.399912 * math.cos(g)
        + 0.070257 * math.sin(g)
        - 0.006758 * math.cos(2 * g)
        + 0.000907 * math.sin(2 * g)
        - 0.002697 * math.cos(3 * g)
        + 0.00148 * math.sin(3 * g)
    )
    latitude = math.radians(lat)
    base = datetime.combine(day, time(), timezone.utc)
    out = {}
    for name, zenith, sign in [
        ("dawn", 96, 1),
        ("sunrise", 90.833, 1),
        ("sunset", 90.833, -1),
        ("dusk", 96, -1),
    ]:
        cos_angle = (
            math.cos(math.radians(zenith)) - math.sin(latitude) * math.sin(dec)
        ) / (math.cos(latitude) * math.cos(dec))
        if not -1 <= cos_angle <= 1:
            out[name] = None
            continue
        angle = math.degrees(math.acos(cos_angle))
        dt = base + timedelta(minutes=720 - 4 * (lon + sign * angle) - eq)
        dt = dt.astimezone(ZoneInfo(zone)) if zone else dt.astimezone()
        out[name] = dt
    return out


def scheduled_time(spec, day, location, offset=0):
    spec = str(spec).strip().lower()
    match = re.fullmatch(r"(dawn|sunrise|sunset|dusk)([+-]\d{1,3})?", spec)
    if match:
        if location.get("latitude") is None or location.get("longitude") is None:
            return None
        dt = solar_times(
            day,
            location["latitude"],
            location["longitude"],
            location.get("timezone", ""),
        )[match[1]]
        return dt + timedelta(minutes=int(match[2] or 0) + int(offset)) if dt else None
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", spec)
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        return None
    dt = datetime.combine(day, time(int(match[1]), int(match[2])))
    zone = location.get("timezone", "")
    return (dt.replace(tzinfo=ZoneInfo(zone)) if zone else dt.astimezone()) + timedelta(
        minutes=int(offset)
    )
