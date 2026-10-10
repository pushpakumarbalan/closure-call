"""National Weather Service / NOAA client. Public API, no key, descriptive User-Agent required.

Everything returned here is a `Signal` (value + source + timestamp) so the decision engine
and the decision record can cite it verbatim.
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any

import httpx

from . import config
from .models import Signal, now_iso

HEADERS = {"User-Agent": config.NWS_USER_AGENT, "Accept": "application/geo+json"}

# CAP (Common Alerting Protocol) enumerations used by NWS. Ordered weakest -> strongest.
SEVERITY_RANK = {"Unknown": 0, "Minor": 1, "Moderate": 2, "Severe": 3, "Extreme": 4}
CERTAINTY_RANK = {"Unknown": 0, "Unlikely": 1, "Possible": 2, "Likely": 3, "Observed": 4}
URGENCY_RANK = {"Unknown": 0, "Past": 0, "Future": 1, "Expected": 2, "Immediate": 3}

# Map NWS event names to the hazard families the threshold tables understand.
HAZARD_FAMILIES: dict[str, list[str]] = {
    "winter": [
        "Blizzard Warning", "Ice Storm Warning", "Winter Storm Warning", "Winter Storm Watch",
        "Winter Weather Advisory", "Snow Squall Warning", "Freezing Rain Advisory",
        "Extreme Cold Warning", "Extreme Cold Watch", "Cold Weather Advisory", "Wind Chill Warning",
        "Wind Chill Advisory", "Freezing Fog Advisory",
    ],
    "severe_storm": [
        "Tornado Warning", "Tornado Watch", "Severe Thunderstorm Warning", "Severe Thunderstorm Watch",
        "High Wind Warning", "High Wind Watch", "Wind Advisory", "Extreme Wind Warning",
        "Hurricane Warning", "Hurricane Watch", "Tropical Storm Warning", "Tropical Storm Watch",
        "Storm Warning", "Dust Storm Warning",
    ],
    "flood": [
        "Flash Flood Warning", "Flash Flood Watch", "Flash Flood Emergency", "Flood Warning", "Flood Watch",
        "Flood Advisory", "Coastal Flood Warning", "Coastal Flood Advisory", "Storm Surge Warning",
        "River Flood Warning",
    ],
    "heat": ["Extreme Heat Warning", "Extreme Heat Watch", "Heat Advisory", "Excessive Heat Warning"],
    "air_quality": ["Air Quality Alert", "Air Stagnation Advisory", "Red Flag Warning", "Fire Weather Watch"],
}
EVENT_TO_FAMILY = {ev: fam for fam, evs in HAZARD_FAMILIES.items() for ev in evs}


def hazard_family(event: str) -> str:
    return EVENT_TO_FAMILY.get(event, "other")


class _Cache:
    def __init__(self, ttl: float):
        self.ttl = ttl
        self.store: dict[str, tuple[float, Any]] = {}

    def get(self, k: str):
        v = self.store.get(k)
        if v and time.time() - v[0] < self.ttl:
            return v[1]
        return None

    def set(self, k: str, val: Any):
        self.store[k] = (time.time(), val)


_cache = _Cache(ttl=60)


async def _get(client: httpx.AsyncClient, url: str, params: dict | None = None) -> dict:
    key = url + str(sorted((params or {}).items()))
    cached = _cache.get(key)
    if cached is not None:
        return cached
    r = await client.get(url, params=params, headers=HEADERS, timeout=config.HTTP_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    _cache.set(key, data)
    return data


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(follow_redirects=True)


# --------------------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------------------

def normalize_alert(feature: dict) -> dict:
    p = feature.get("properties", {})
    event = p.get("event", "Unknown")
    return {
        "id": p.get("id") or feature.get("id"),
        "event": event,
        "hazard_family": hazard_family(event),
        "headline": p.get("headline"),
        "severity": p.get("severity", "Unknown"),
        "certainty": p.get("certainty", "Unknown"),
        "urgency": p.get("urgency", "Unknown"),
        "severity_rank": SEVERITY_RANK.get(p.get("severity", "Unknown"), 0),
        "certainty_rank": CERTAINTY_RANK.get(p.get("certainty", "Unknown"), 0),
        "urgency_rank": URGENCY_RANK.get(p.get("urgency", "Unknown"), 0),
        "area": p.get("areaDesc"),
        "sender": p.get("senderName"),
        "sent": p.get("sent"),
        "effective": p.get("effective"),
        "onset": p.get("onset"),
        "expires": p.get("expires"),
        "ends": p.get("ends"),
        "status": p.get("status"),
        "message_type": p.get("messageType"),
        "description": p.get("description"),
        "instruction": p.get("instruction"),
        "url": p.get("@id") or p.get("id"),
        "has_geometry": feature.get("geometry") is not None,
        "affected_zones": (p.get("affectedZones") or [])[:3],
    }


def _centroid(geom: dict) -> tuple[float, float] | None:
    coords: list = []

    def walk(c):
        if isinstance(c, list) and c and isinstance(c[0], (int, float)):
            coords.append(c)
        elif isinstance(c, list):
            for x in c:
                walk(x)

    walk(geom.get("coordinates"))
    if not coords:
        return None
    return sum(c[1] for c in coords) / len(coords), sum(c[0] for c in coords) / len(coords)


async def zone_centroid(zone_url: str) -> dict | None:
    """Zone-based alerts carry no polygon; fetch the zone to get a representative point."""
    if not zone_url.startswith(config.NWS_BASE + "/zones/"):
        return None
    async with _client() as c:
        data = await _get(c, zone_url)
    geom = data.get("geometry")
    if not geom:
        return None
    ll = _centroid(geom)
    return {"lat": ll[0], "lon": ll[1], "zone": data.get("properties", {}).get("name")} if ll else None


async def active_alerts_national(limit_geometry: bool = True) -> dict:
    """All active alerts in the US as GeoJSON for the map, plus normalized summaries."""
    async with _client() as c:
        data = await _get(c, f"{config.NWS_BASE}/alerts/active", {"status": "actual", "message_type": "alert,update"})
    feats = data.get("features", [])
    out_feats = []
    for f in feats:
        n = normalize_alert(f)
        geom = f.get("geometry")
        out_feats.append({"type": "Feature", "geometry": geom, "properties": n})
    return {"type": "FeatureCollection", "fetched_at": now_iso(), "count": len(out_feats), "features": out_feats}


async def active_alerts_for_point(lat: float, lon: float) -> list[dict]:
    async with _client() as c:
        data = await _get(c, f"{config.NWS_BASE}/alerts/active", {"point": f"{lat:.4f},{lon:.4f}", "status": "actual"})
    out = [normalize_alert(f) for f in data.get("features", [])]
    # Products whose urgency is Past (event over) or that are cancellations should not drive a decision.
    return [a for a in out if a["urgency"] != "Past" and a["message_type"] != "Cancel"]


# --------------------------------------------------------------------------------------
# Forecast + observations
# --------------------------------------------------------------------------------------

_WIND_RE = re.compile(r"(\d+)(?:\s*to\s*(\d+))?\s*mph", re.I)


def _parse_wind_mph(s: str | None) -> float | None:
    if not s:
        return None
    m = _WIND_RE.search(s)
    if not m:
        return None
    hi = m.group(2) or m.group(1)
    return float(hi)


def _ms_to_mph(v: float | None) -> float | None:
    return None if v is None else v * 2.23694


def _kmh_to_mph(v: float | None) -> float | None:
    return None if v is None else v * 0.621371


def _c_to_f(v: float | None) -> float | None:
    return None if v is None else v * 9 / 5 + 32


def _m_to_mi(v: float | None) -> float | None:
    return None if v is None else v / 1609.34


async def point_metadata(lat: float, lon: float) -> dict:
    async with _client() as c:
        data = await _get(c, f"{config.NWS_BASE}/points/{lat:.4f},{lon:.4f}")
    return data.get("properties", {})


async def conditions_for_point(lat: float, lon: float) -> dict[str, Any]:
    """Hourly forecast for the next ~18h and the latest observation from the nearest station."""
    meta = await point_metadata(lat, lon)
    out: dict[str, Any] = {"meta": {k: meta.get(k) for k in ("gridId", "gridX", "gridY", "forecastZone", "county", "radarStation")}}
    async with _client() as c:
        hourly_task = _get(c, meta["forecastHourly"]) if meta.get("forecastHourly") else None
        stations_task = _get(c, meta["observationStations"]) if meta.get("observationStations") else None
        results = await asyncio.gather(*(t for t in (hourly_task, stations_task) if t), return_exceptions=True)
        hourly = results[0] if hourly_task else None
        stations = results[1] if stations_task and len(results) > 1 else (results[0] if stations_task and not hourly_task else None)

        periods = []
        if isinstance(hourly, dict):
            for p in hourly.get("properties", {}).get("periods", [])[:18]:
                periods.append({
                    "start": p.get("startTime"),
                    "temp_f": p.get("temperature") if p.get("temperatureUnit") == "F" else _c_to_f(p.get("temperature")),
                    "wind_mph": _parse_wind_mph(p.get("windSpeed")),
                    "wind_dir": p.get("windDirection"),
                    "precip_pct": (p.get("probabilityOfPrecipitation") or {}).get("value"),
                    "short": p.get("shortForecast"),
                })
        out["hourly"] = periods
        out["forecast_url"] = meta.get("forecastHourly")

        obs = None
        if isinstance(stations, dict):
            feats = stations.get("features", [])[:3]
            for st in feats:
                sid = st.get("properties", {}).get("stationIdentifier")
                if not sid:
                    continue
                try:
                    o = await _get(c, f"{config.NWS_BASE}/stations/{sid}/observations/latest")
                    pr = o.get("properties", {})
                    if pr.get("timestamp"):
                        def val(k):
                            return (pr.get(k) or {}).get("value")

                        obs = {
                            "station": sid,
                            "station_name": st.get("properties", {}).get("name"),
                            "timestamp": pr.get("timestamp"),
                            "text": pr.get("textDescription"),
                            "temp_f": _c_to_f(val("temperature")),
                            "wind_chill_f": _c_to_f(val("windChill")),
                            "heat_index_f": _c_to_f(val("heatIndex")),
                            "wind_mph": _kmh_to_mph(val("windSpeed")),
                            "gust_mph": _kmh_to_mph(val("windGust")),
                            "visibility_mi": _m_to_mi(val("visibility")),
                            "url": f"{config.NWS_BASE}/stations/{sid}/observations/latest",
                        }
                        break
                except Exception:
                    continue
        out["observation"] = obs
    return out


# --------------------------------------------------------------------------------------
# Signal builders
# --------------------------------------------------------------------------------------

def alert_signals(alerts: list[dict]) -> list[Signal]:
    sigs: list[Signal] = []
    for a in alerts:
        sigs.append(
            Signal(
                key=f"nws_alert:{a['event']}",
                label=f"NWS {a['event']}",
                value={"severity": a["severity"], "certainty": a["certainty"], "urgency": a["urgency"],
                       "severity_rank": a["severity_rank"], "certainty_rank": a["certainty_rank"], "urgency_rank": a["urgency_rank"]},
                display=f"{a['event']} - {a['severity']} / {a['certainty']} / {a['urgency']} ({a['sender']})",
                source="NWS Alerts API (CAP)",
                source_url=a.get("url"),
                observed_at=a.get("sent") or a.get("effective"),
                detail={k: a.get(k) for k in ("headline", "area", "onset", "ends", "expires", "hazard_family", "instruction")},
            )
        )
    if not alerts:
        sigs.append(Signal(key="nws_alert:none", label="NWS active alerts", value=0, display="No active NWS alerts for this point",
                           source="NWS Alerts API (CAP)", source_url=f"{config.NWS_BASE}/alerts/active", observed_at=now_iso()))
    return sigs


def condition_signals(cond: dict[str, Any]) -> list[Signal]:
    sigs: list[Signal] = []
    obs = cond.get("observation")
    if obs:
        ts = obs.get("timestamp")
        if obs.get("wind_mph") is not None:
            sigs.append(Signal(key="obs_wind_mph", label="Observed sustained wind", value=round(obs["wind_mph"], 1), unit="mph",
                               display=f"{obs['wind_mph']:.0f} mph sustained at {obs['station']}", source=f"NWS observation {obs['station']}",
                               source_url=obs["url"], observed_at=ts))
        if obs.get("gust_mph") is not None:
            sigs.append(Signal(key="obs_gust_mph", label="Observed wind gust", value=round(obs["gust_mph"], 1), unit="mph",
                               display=f"{obs['gust_mph']:.0f} mph gust at {obs['station']}", source=f"NWS observation {obs['station']}",
                               source_url=obs["url"], observed_at=ts))
        if obs.get("temp_f") is not None:
            sigs.append(Signal(key="obs_temp_f", label="Observed temperature", value=round(obs["temp_f"], 1), unit="F",
                               display=f"{obs['temp_f']:.0f} F, {obs.get('text') or ''}".strip(", "), source=f"NWS observation {obs['station']}",
                               source_url=obs["url"], observed_at=ts))
        if obs.get("wind_chill_f") is not None:
            sigs.append(Signal(key="obs_wind_chill_f", label="Observed wind chill", value=round(obs["wind_chill_f"], 1), unit="F",
                               display=f"{obs['wind_chill_f']:.0f} F wind chill", source=f"NWS observation {obs['station']}",
                               source_url=obs["url"], observed_at=ts))
        if obs.get("heat_index_f") is not None:
            sigs.append(Signal(key="obs_heat_index_f", label="Observed heat index", value=round(obs["heat_index_f"], 1), unit="F",
                               display=f"{obs['heat_index_f']:.0f} F heat index", source=f"NWS observation {obs['station']}",
                               source_url=obs["url"], observed_at=ts))
        if obs.get("visibility_mi") is not None:
            sigs.append(Signal(key="obs_visibility_mi", label="Observed visibility", value=round(obs["visibility_mi"], 2), unit="mi",
                               display=f"{obs['visibility_mi']:.1f} mi visibility", source=f"NWS observation {obs['station']}",
                               source_url=obs["url"], observed_at=ts))
    hourly = cond.get("hourly") or []
    if hourly:
        window = hourly[:12]
        winds = [h["wind_mph"] for h in window if h.get("wind_mph") is not None]
        temps = [h["temp_f"] for h in window if h.get("temp_f") is not None]
        precips = [h["precip_pct"] for h in window if h.get("precip_pct") is not None]
        first = window[0]
        if winds:
            sigs.append(Signal(key="fcst_wind_max_mph", label="Forecast max wind (next 12h)", value=max(winds), unit="mph",
                               display=f"up to {max(winds):.0f} mph forecast, next 12h", source="NWS hourly forecast",
                               source_url=cond.get("forecast_url"), observed_at=first.get("start")))
        if temps:
            sigs.append(Signal(key="fcst_temp_min_f", label="Forecast min temp (next 12h)", value=min(temps), unit="F",
                               display=f"low {min(temps):.0f} F / high {max(temps):.0f} F, next 12h", source="NWS hourly forecast",
                               source_url=cond.get("forecast_url"), observed_at=first.get("start")))
            sigs.append(Signal(key="fcst_temp_max_f", label="Forecast max temp (next 12h)", value=max(temps), unit="F",
                               display=f"high {max(temps):.0f} F, next 12h", source="NWS hourly forecast",
                               source_url=cond.get("forecast_url"), observed_at=first.get("start")))
        if precips:
            sigs.append(Signal(key="fcst_precip_max_pct", label="Forecast max precip chance (next 12h)", value=max(precips), unit="%",
                               display=f"{max(precips):.0f}% max precip chance; {first.get('short')}", source="NWS hourly forecast",
                               source_url=cond.get("forecast_url"), observed_at=first.get("start")))
        wintry = [h for h in window if h.get("short") and re.search(r"snow|sleet|ice|freezing|blizzard|wintry", h["short"], re.I)]
        if wintry:
            sigs.append(Signal(key="fcst_wintry_hours", label="Forecast hours with wintry precip (next 12h)", value=len(wintry), unit="h",
                               display=f"{len(wintry)} of next 12 hours show {wintry[0]['short']}", source="NWS hourly forecast",
                               source_url=cond.get("forecast_url"), observed_at=wintry[0].get("start")))
    return sigs
