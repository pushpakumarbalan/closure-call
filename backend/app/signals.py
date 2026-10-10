"""Supplementary signals a real facility manager would check, beyond NWS alerts.

1. River gauges via NOAA National Water Prediction Service (NWPS) - public, no key. Gives observed and
   forecast stage with official flood categories (action / minor / moderate / major).
2. Air quality via AirNow (key optional). Falls back to NWS Air Quality Alert products when no key.
3. Road conditions: 511 feeds are state-specific and mostly keyed. We model a stub that reads from the
   facility's `road_feed` if configured; in the demo it is left as a documented gap, not a mock.
"""
from __future__ import annotations

import httpx

from . import config
from .models import Signal, now_iso

FLOOD_CATEGORY_RANK = {"no_flooding": 0, "not_defined": 0, "obs_not_current": 0, "action": 1, "minor": 2, "moderate": 3, "major": 4}
AQI_CATEGORY = [
    (50, "Good"), (100, "Moderate"), (150, "Unhealthy for Sensitive Groups"), (200, "Unhealthy"),
    (300, "Very Unhealthy"), (10_000, "Hazardous"),
]


def aqi_category(aqi: int) -> str:
    for cap, name in AQI_CATEGORY:
        if aqi <= cap:
            return name
    return "Hazardous"


async def river_gauge_signals(gauge_ids: list[str]) -> list[Signal]:
    sigs: list[Signal] = []
    if not gauge_ids:
        return sigs
    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as c:
        for lid in gauge_ids:
            url = f"{config.NWPS_BASE}/gauges/{lid}"
            try:
                r = await c.get(url)
                r.raise_for_status()
                g = r.json()
            except Exception as e:  # keep going; one gauge failing shouldn't sink the evaluation
                sigs.append(Signal(key=f"river:{lid}", label=f"River gauge {lid}", value=None, display=f"gauge {lid} unavailable ({type(e).__name__})",
                                   source="NOAA NWPS", source_url=url, observed_at=None))
                continue
            status = g.get("status") or {}
            obs = status.get("observed") or {}
            fc = status.get("forecast") or {}
            cats = (g.get("flood") or {}).get("categories") or {}
            obs_cat = obs.get("floodCategory", "not_defined")
            fc_cat = fc.get("floodCategory", "not_defined")
            worst_cat = max([obs_cat, fc_cat], key=lambda k: FLOOD_CATEGORY_RANK.get(k, 0))
            minor_stage = (cats.get("minor") or {}).get("stage")
            stage = obs.get("primary")
            margin = f"{minor_stage - stage:.1f} ft below minor flood stage" if (minor_stage and stage is not None and stage < minor_stage) else (
                f"{stage - minor_stage:.1f} ft above minor flood stage" if (minor_stage and stage is not None) else "")
            sigs.append(Signal(
                key=f"river:{lid}", label=f"{g.get('name', lid)}",
                value={"observed_stage_ft": stage, "observed_category": obs_cat, "forecast_stage_ft": fc.get("primary"),
                       "forecast_category": fc_cat, "worst_category": worst_cat, "worst_rank": FLOOD_CATEGORY_RANK.get(worst_cat, 0),
                       "categories": {k: v.get("stage") for k, v in cats.items()}},
                unit="ft",
                display=f"{g.get('name', lid)}: {stage} ft observed ({obs_cat.replace('_', ' ')}), forecast {fc.get('primary')} ft ({fc_cat.replace('_', ' ')}). {margin}".strip(),
                source="NOAA National Water Prediction Service", source_url=f"https://water.noaa.gov/gauges/{lid}",
                observed_at=obs.get("validTime"),
                detail={"forecast_valid": fc.get("validTime"), "impacts": (g.get("impacts") or [])[:3]},
            ))
    return sigs


async def air_quality_signals(lat: float, lon: float, nws_alerts: list[dict]) -> list[Signal]:
    if config.AIRNOW_API_KEY:
        url = config.AIRNOW_BASE
        params = {"format": "application/json", "latitude": lat, "longitude": lon, "distance": 50, "API_KEY": config.AIRNOW_API_KEY}
        try:
            async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as c:
                r = await c.get(url, params=params)
                r.raise_for_status()
                rows = r.json()
            if rows:
                worst = max(rows, key=lambda x: x.get("AQI", 0))
                aqi = int(worst.get("AQI", 0))
                return [Signal(key="aqi", label="Air Quality Index", value=aqi, unit="AQI",
                               display=f"AQI {aqi} ({aqi_category(aqi)}) - {worst.get('ParameterName')} at {worst.get('ReportingArea')}",
                               source="AirNow (EPA)", source_url="https://www.airnow.gov/", observed_at=f"{worst.get('DateObserved','').strip()}T{worst.get('HourObserved', 0):02d}:00")]
        except Exception:
            pass
    # Fallback: NWS Air Quality Alert product counts as a categorical signal.
    aq = [a for a in nws_alerts if a["hazard_family"] == "air_quality"]
    if aq:
        a = aq[0]
        return [Signal(key="aqi", label="Air quality (NWS product)", value=151, unit="AQI(est)",
                       display=f"{a['event']} in effect ({a['sender']}); treated as USG-or-worse", source="NWS Alerts API (CAP)",
                       source_url=a.get("url"), observed_at=a.get("sent"))]
    return [Signal(key="aqi", label="Air Quality Index", value=None, display="No AirNow key configured and no NWS air quality product in effect",
                   source="AirNow (not configured)", observed_at=now_iso())]


def road_signal(facility: dict) -> list[Signal]:
    """State DOT 511 feeds require per-state keys; expose the gap honestly rather than fake it."""
    feed = facility.get("road_feed")
    if not feed:
        return [Signal(key="roads", label="State DOT road conditions", value=None,
                       display=f"No 511 feed configured for {facility.get('state', 'this state')}; manager should check {facility.get('road_feed_hint', 'state 511 site')}",
                       source="State DOT 511 (not configured)", source_url=facility.get("road_feed_hint_url"), observed_at=now_iso())]
    return []
