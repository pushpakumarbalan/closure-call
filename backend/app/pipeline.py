"""Evidence gathering: pull every input for a facility, timestamped, in parallel."""
from __future__ import annotations

import asyncio
from datetime import datetime

from . import nws, signals as supp
from .decision import decision_phase, evaluate
from .facility import get_roster, roster_summary
from .models import Signal, now_iso


class Evidence:
    def __init__(self, facility: dict, lat: float, lon: float, drill_note: str | None):
        self.facility = facility
        self.lat, self.lon = lat, lon
        self.drill_note = drill_note
        self.alerts: list[dict] = []
        self.conditions: dict = {}
        self.signals: list[Signal] = []
        self.gathered_at = now_iso()
        self.phase, self.local_time = decision_phase(facility)
        self.result: dict | None = None

    def signals_by_group(self) -> dict[str, list[Signal]]:
        groups = {"alerts": [], "observations": [], "forecast": [], "river": [], "air": [], "roads": []}
        for s in self.signals:
            if s.key.startswith("nws_alert"):
                groups["alerts"].append(s)
            elif s.key.startswith("obs_"):
                groups["observations"].append(s)
            elif s.key.startswith("fcst_"):
                groups["forecast"].append(s)
            elif s.key.startswith("river"):
                groups["river"].append(s)
            elif s.key == "aqi":
                groups["air"].append(s)
            elif s.key == "roads":
                groups["roads"].append(s)
        return groups


async def gather(facility: dict, lat: float | None = None, lon: float | None = None, drill_note: str | None = None) -> Evidence:
    lat = lat if lat is not None else facility["lat"]
    lon = lon if lon is not None else facility["lon"]
    ev = Evidence(facility, lat, lon, drill_note)
    is_drill = drill_note is not None
    alerts_task = nws.active_alerts_for_point(lat, lon)
    cond_task = nws.conditions_for_point(lat, lon)
    # River gauges are tied to the real facility; in a relocated drill they don't apply.
    river_task = supp.river_gauge_signals([] if is_drill else facility.get("river_gauges", []))
    alerts, cond, river = await asyncio.gather(alerts_task, cond_task, river_task, return_exceptions=True)
    ev.alerts = alerts if isinstance(alerts, list) else []
    ev.conditions = cond if isinstance(cond, dict) else {}
    air = await supp.air_quality_signals(lat, lon, ev.alerts)
    ev.signals = (
        nws.alert_signals(ev.alerts)
        + nws.condition_signals(ev.conditions)
        + (river if isinstance(river, list) else [])
        + air
        + supp.road_signal(facility)
    )
    if isinstance(alerts, Exception):
        ev.signals.append(Signal(key="nws_alert:error", label="NWS alerts", value=None, display=f"NWS alerts unavailable: {alerts}", source="NWS Alerts API"))
    ev.result = evaluate(facility, ev.signals, ev.phase)
    return ev


def evidence_summary_for_llm(ev: Evidence) -> dict:
    """Compact, fully-cited view the agent reasons over."""
    r = ev.result or {}
    return {
        "facility": {k: ev.facility[k] for k in ("id", "name", "type", "agency", "address", "hours", "notes", "hazard_profile")},
        "evaluation_point": {"lat": ev.lat, "lon": ev.lon, "drill": ev.drill_note},
        "local_time": ev.local_time,
        "decision_phase": ev.phase,
        "roster": roster_summary(ev.facility["id"]),
        "inputs": [
            {"key": s.key, "display": s.display, "source": s.source, "observed_at": s.observed_at, "url": s.source_url}
            for s in ev.signals
        ],
        "engine": {
            "posture": r.get("posture").value if r.get("posture") else None,
            "posture_label": r.get("posture_label"),
            "triggered": [h.model_dump() for h in r.get("triggered", [])],
            "near_misses": [h.model_dump() for h in r.get("near_misses", [])],
            "confidence": r.get("confidence"),
            "confidence_reasons": r.get("confidence_reasons"),
            "what_would_change": r.get("what_would_change"),
            "notes": r.get("notes"),
        },
    }


def roster_for(ev: Evidence) -> list[dict]:
    return get_roster(ev.facility["id"])
