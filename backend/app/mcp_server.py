"""Closure Call MCP server. This is the 'with MCP' path: Strands calls these tools over stdio.

It does not generate a script. The process is spawned per evaluation with the facility and point in the
environment, fetches live NWS / NWPS data, and returns JSON. Nothing is written to stdout except MCP frames.
"""
from __future__ import annotations

import asyncio
import json
import os

from mcp.server.mcpserver import MCPServer

from .facility import get_facility, roster_summary
from .pipeline import Evidence, gather

mcp = MCPServer("closurecall", instructions="Live weather, roster, and closure-threshold tools for one facility evaluation.")
_evidence: Evidence | None = None


async def _ev() -> Evidence:
    global _evidence
    if _evidence is None:
        facility = get_facility(os.environ["CLOSURECALL_FACILITY_ID"])
        if facility is None:
            raise RuntimeError("unknown facility")
        drill = os.environ.get("CLOSURECALL_DRILL") or None
        _evidence = await gather(facility, float(os.environ["CLOSURECALL_LAT"]), float(os.environ["CLOSURECALL_LON"]), drill)
    return _evidence


def _dump(ev: Evidence, keys: tuple[str, ...]) -> list[dict]:
    out = []
    for s in ev.signals:
        if any(s.key.startswith(k) or s.key == k for k in keys):
            out.append({"key": s.key, "display": s.display, "value": s.value, "source": s.source, "observed_at": s.observed_at, "url": s.source_url})
    return out


@mcp.tool(description="Facility location, hours, and today's roster summary.")
async def get_facility_profile() -> str:
    ev = await _ev()
    f = ev.facility
    return json.dumps({
        "facility": {k: f[k] for k in ("id", "name", "type", "agency", "address", "hours", "timezone", "notes", "hazard_profile")},
        "location": {"lat": ev.lat, "lon": ev.lon},
        "exercise": ev.drill_note,
        "local_time": ev.local_time,
        "decision_phase": ev.phase,
        "roster": roster_summary(f["id"]),
    })


@mcp.tool(description="Active NWS alerts for this evaluation point: event, severity, certainty, urgency, onset, ends.")
async def get_nws_alerts() -> str:
    ev = await _ev()
    alerts = [{k: a.get(k) for k in ("event", "severity", "certainty", "urgency", "headline", "area", "onset", "ends", "expires", "sender", "instruction")} for a in ev.alerts]
    return json.dumps({"count": len(alerts), "alerts": alerts})


@mcp.tool(description="Nearest NWS station observation and the next 12 hours of forecast.")
async def get_weather_conditions() -> str:
    ev = await _ev()
    return json.dumps({"observation": ev.conditions.get("observation"), "hourly_next_12h": (ev.conditions.get("hourly") or [])[:12], "signals": _dump(ev, ("obs_", "fcst_"))})


@mcp.tool(description="NOAA river-gauge stage and official flood category for this facility.")
async def get_river_gauges() -> str:
    ev = await _ev()
    return json.dumps({"gauges": _dump(ev, ("river",)) or "no gauge assigned to this facility"})


@mcp.tool(description="Air quality and state road-condition status.")
async def get_air_quality_and_roads() -> str:
    ev = await _ev()
    return json.dumps({"air_quality": _dump(ev, ("aqi",)), "roads": _dump(ev, ("roads",))})


@mcp.tool(description="Threshold engine result: posture, every crossed rule with its anchor, near misses, confidence.")
async def get_threshold_evaluation() -> str:
    ev = await _ev()
    r = ev.result or {}
    return json.dumps({
        "posture": r["posture"].value, "posture_label": r["posture_label"], "hazards": r["hazards"],
        "triggered": [h.model_dump() for h in r["triggered"]], "near_misses": [h.model_dump() for h in r["near_misses"]],
        "confidence": r["confidence"], "confidence_reasons": r["confidence_reasons"],
        "what_would_change": r["what_would_change"], "notes": r["notes"],
    })


def main() -> None:
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()
