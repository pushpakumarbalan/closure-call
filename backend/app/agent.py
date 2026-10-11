"""Strands agent: reviews the evidence with tools, challenges the deterministic engine, writes the rationale.

Model: Akamai Cloud hosted inference (OpenAI-compatible) via strands.models.openai.OpenAIModel.
Fallback: if no LLM is configured or the call fails, the deterministic rationale is used and the
recommendation is labelled `rationale_source="deterministic"`. The demo never depends on the LLM being up.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any, AsyncIterator

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models.openai import OpenAIModel
from strands.tools.mcp import MCPClient

from . import config
from .decision import deterministic_rationale
from .facility import roster_summary
from .models import POSTURE_LABEL, Posture, Recommendation
from .pipeline import Evidence, evidence_summary_for_llm
from .thresholds import OPM_LADDER

log = logging.getLogger("closurecall.agent")


class AgentAssessment(BaseModel):
    rationale: str = Field(description="One paragraph, plain language, that a facility manager could paste into an email. Cite the specific inputs (with values and sources) that drove the call.")
    agrees_with_engine: bool = Field(description="True if the threshold engine's posture is the right call.")
    suggested_posture: str = Field(description="One of: normal, delay, early_dismissal, telework, closure.")
    disagreement_reason: str | None = Field(default=None, description="If you disagree with the engine, the specific evidence that justifies a different posture.")
    key_risks: list[str] = Field(default_factory=list, description="2-4 short bullets on what could go wrong or what to watch.")
    manager_checklist: list[str] = Field(default_factory=list, description="2-4 concrete next actions for the facility manager in the next hour.")


SYSTEM_PROMPT = """You are Closure Call, a decision-support agent for a federal facility manager deciding whether to open, delay, dismiss early, go to unscheduled telework, or close a building because of weather.

You do NOT make the decision. A human does. Your job:
1. Use the tools to pull the live evidence for the facility: NWS alerts, observations/forecast, river gauges, air quality, roster, and the threshold engine's evaluation.
2. Check the engine's recommendation against the evidence. The engine is rule-based and deliberately conservative; you may disagree if the evidence clearly supports it (for example, a Warning that ends before the shift starts, or an alert whose polygon is clearly for a different area).
3. Write a one-paragraph plain-language rationale a manager could paste into an email. Name the inputs with their values and sources. State the posture using the OPM operating-status language. Mention confidence and the single thing most likely to change the call.
4. Essential (emergency) personnel always report regardless of posture; say so when relevant.

OPM operating-status ladder (least to most restrictive):
""" + "\n".join(f"- {k}: {label} - {desc}" for k, label, desc in OPM_LADDER) + """

Exercises: when the prompt says EXERCISE, the facility is being evaluated as if it were located at the given point so the manager can rehearse against live conditions. Treat that point as the facility's location; do not flag the relocation as a mismatch.

Your data tools are served by the Closure Call MCP server over stdio. Call those tools. Do not write a script and do not call weather APIs yourself.

Be concrete, be brief, never invent data that the tools did not return. If a source was unavailable, say so. Before the final assessment, write at most three short bullets of working notes, then produce the assessment."""


def _model() -> OpenAIModel | None:
    if not config.LLM_ENABLED:
        return None
    return OpenAIModel(
        client_args={"api_key": config.LLM_API_KEY, "base_url": config.LLM_BASE_URL},
        model_id=config.LLM_MODEL_ID,
        params={"temperature": 0.2, "max_tokens": 1800},
    )


def _tools_for(ev: Evidence) -> list:
    """Tools are closures over this request's evidence so the agent and the record see identical data."""
    groups = ev.signals_by_group()

    def dump(sigs):
        return [{"display": s.display, "value": s.value, "source": s.source, "observed_at": s.observed_at, "url": s.source_url, "detail": s.detail} for s in sigs]

    @tool
    def get_facility_profile() -> dict:
        """Facility location, hours, hazard profile, operational notes, and today's roster summary (essential, telework-eligible, on detail, on leave)."""
        f = ev.facility
        prof = {k: f[k] for k in ("id", "name", "type", "agency", "address", "hours", "timezone", "notes", "hazard_profile")}
        if ev.drill_note:
            prof["address"] = f"EXERCISE LOCATION: {ev.lat:.3f}, {ev.lon:.3f} (the facility is treated as being at this point for this exercise)"
        return {"facility": prof, "location": {"lat": ev.lat, "lon": ev.lon}, "exercise": ev.drill_note, "local_time": ev.local_time,
                "decision_phase": ev.phase, "roster": roster_summary(f["id"])}

    @tool
    def get_nws_alerts() -> dict:
        """Active National Weather Service alerts (CAP) for the facility point: event, severity, certainty, urgency, onset/ends, headline, instruction."""
        return {"count": len(ev.alerts), "alerts": [{k: a.get(k) for k in ("event", "severity", "certainty", "urgency", "headline", "area", "onset", "ends", "expires", "sender", "instruction", "url")} for a in ev.alerts]}

    @tool
    def get_weather_conditions() -> dict:
        """Latest NWS station observation (wind, gust, temp, wind chill, heat index, visibility) and the next-12-hour hourly forecast summary for the facility point."""
        return {"observation": ev.conditions.get("observation"), "hourly_next_12h": (ev.conditions.get("hourly") or [])[:12], "derived_signals": dump(groups["observations"] + groups["forecast"])}

    @tool
    def get_river_gauges() -> dict:
        """NOAA NWPS river gauge status for gauges tied to this facility: observed and forecast stage with official flood category."""
        return {"gauges": dump(groups["river"]) or "no gauges configured for this evaluation (relocated drill or none assigned)"}

    @tool
    def get_air_quality_and_roads() -> dict:
        """Air quality (AirNow or NWS air quality product) and state DOT road-condition status for the facility."""
        return {"air_quality": dump(groups["air"]), "roads": dump(groups["roads"])}

    @tool
    def get_threshold_evaluation() -> dict:
        """The deterministic threshold engine's result: recommended posture, every triggered rule with threshold/observed/margin/anchor, near misses, confidence, and what would change it."""
        r = ev.result or {}
        return {"posture": r["posture"].value, "posture_label": r["posture_label"], "hazards": r["hazards"],
                "triggered": [h.model_dump() for h in r["triggered"]], "near_misses": [h.model_dump() for h in r["near_misses"]],
                "confidence": r["confidence"], "confidence_reasons": r["confidence_reasons"], "what_would_change": r["what_would_change"], "notes": r["notes"]}

    return [get_facility_profile, get_nws_alerts, get_weather_conditions, get_river_gauges, get_air_quality_and_roads, get_threshold_evaluation]


def _base_recommendation(ev: Evidence) -> Recommendation:
    r = ev.result or {}
    return Recommendation(
        facility_id=ev.facility["id"], facility_name=ev.facility["name"], evaluated_at=ev.gathered_at,
        posture=r["posture"], posture_label=r["posture_label"], hazards=r["hazards"], inputs=ev.signals,
        triggered=r["triggered"], near_misses=r["near_misses"], confidence=r["confidence"], confidence_reasons=r["confidence_reasons"],
        what_would_change=r["what_would_change"],
        rationale=deterministic_rationale(ev.facility, r, ev.signals, ev.phase, ev.local_time), rationale_source="deterministic",
        drill=ev.drill_note is not None, drill_note=ev.drill_note,
    )


def _apply_assessment(rec: Recommendation, a: AgentAssessment, trace: list[dict]) -> Recommendation:
    rec.rationale = a.rationale.strip()
    rec.rationale_source = "agent"
    rec.agent_trace = trace
    if not a.agrees_with_engine and a.suggested_posture in Posture._value2member_map_ and a.disagreement_reason:
        # The agent may argue; the record keeps the engine posture as a trace entry so the disagreement is auditable.
        trace.append({"type": "disagreement", "engine_posture": rec.posture.value, "agent_posture": a.suggested_posture, "reason": a.disagreement_reason})
        rec.what_would_change.insert(0, f"Agent note: engine says {POSTURE_LABEL[rec.posture]}; agent suggests {POSTURE_LABEL[Posture(a.suggested_posture)]} because {a.disagreement_reason}")
    if a.key_risks:
        trace.append({"type": "key_risks", "items": a.key_risks})
    if a.manager_checklist:
        trace.append({"type": "manager_checklist", "items": a.manager_checklist})
    return rec


def _mcp_client(ev: Evidence) -> MCPClient:
    env = os.environ.copy()
    env["CLOSURECALL_FACILITY_ID"] = ev.facility["id"]
    env["CLOSURECALL_LAT"] = str(ev.lat)
    env["CLOSURECALL_LON"] = str(ev.lon)
    env["CLOSURECALL_DRILL"] = ev.drill_note or ""
    params = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server"], env=env, cwd=str(config.ROOT))
    return MCPClient(lambda: stdio_client(params), startup_timeout=30, application_name="closurecall")


def _prompt(ev: Evidence) -> str:
    return (f"Evaluate the closure posture for {ev.facility['name']} as of {ev.local_time} (phase: {ev.phase}). "
            + (f"EXERCISE: {ev.drill_note} Evaluate conditions at the exercise location ({ev.lat:.3f}, {ev.lon:.3f}) as the facility's location. " if ev.drill_note else "")
            + "Call the tools to gather the evidence, starting with get_threshold_evaluation and get_nws_alerts, then produce your assessment.")


async def recommend_stream(ev: Evidence) -> AsyncIterator[dict]:
    """Yield SSE-friendly events: status / tool / text / result. Always ends with a result."""
    rec = _base_recommendation(ev)
    model = _model()
    if model is None:
        yield {"type": "status", "message": "No LLM configured; using deterministic rationale."}
        yield {"type": "result", "recommendation": rec.model_dump(mode="json")}
        return

    trace: list[dict] = []
    t0 = time.time()
    similar = []
    try:
        from .records import recall
        similar = recall(f"{ev.facility['name']} {ev.result['posture'].value if ev.result else ''} {ev.local_time}")
    except Exception:
        similar = []
    if similar:
        trace.append({"type": "similar_decisions", "model": "hackathon-embedding", "host": "ws.akamai-workshops.com", "items": similar})
    try:
        client = _mcp_client(ev)
        client.start()
        tools = list(client.list_tools_sync())
        yield {"type": "status", "message": f"Strands agent using MCP server closurecall ({len(tools)} tools) over stdio"}
        yield {"type": "status", "message": f"Model {config.LLM_MODEL_ID} is Akamai hosted inference, not running on this machine"}
        agent = Agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT, callback_handler=None)
        seen_tools: set[str] = set()
        async for event in agent.stream_async(_prompt(ev), structured_output_model=AgentAssessment):
            tu = event.get("current_tool_use")
            if tu and tu.get("toolUseId") and tu["toolUseId"] not in seen_tools and tu.get("name"):
                seen_tools.add(tu["toolUseId"])
                if tu["name"] == "AgentAssessment":  # structured-output call, not a data tool
                    yield {"type": "status", "message": "Agent composing assessment"}
                    continue
                trace.append({"type": "tool_call", "name": tu["name"], "t": round(time.time() - t0, 2)})
                yield {"type": "tool", "name": tu["name"]}
            if "data" in event and isinstance(event["data"], str) and event["data"]:
                yield {"type": "text", "delta": event["data"]}
            if "result" in event:
                res = event["result"]
                so = getattr(res, "structured_output", None)
                if so is None:
                    # Some providers return JSON as text; try to parse.
                    txt = str(res)
                    so = _parse_assessment(txt)
                if so is not None:
                    trace.append({"type": "done", "seconds": round(time.time() - t0, 2), "tools_called": len(seen_tools), "transport": "mcp"})
                    rec = _apply_assessment(rec, so, trace)
        client.stop(None, None, None)
    except Exception as e:  # never let the LLM or MCP take down the demo
        log.exception("agent failed; using deterministic rationale")
        trace.append({"type": "error", "message": f"{type(e).__name__}: {e}"})
        rec.agent_trace = trace
        yield {"type": "status", "message": f"Agent unavailable ({type(e).__name__}); using deterministic rationale."}
    if similar and not any(t.get("type") == "similar_decisions" for t in rec.agent_trace):
        rec.agent_trace = [{"type": "similar_decisions", "model": "hackathon-embedding", "host": "ws.akamai-workshops.com", "items": similar}] + rec.agent_trace
    yield {"type": "result", "recommendation": rec.model_dump(mode="json")}


async def recommend(ev: Evidence) -> Recommendation:
    final: dict | None = None
    async for e in recommend_stream(ev):
        if e["type"] == "result":
            final = e["recommendation"]
    return Recommendation.model_validate(final)


def _parse_assessment(txt: str) -> AgentAssessment | None:
    try:
        start, end = txt.find("{"), txt.rfind("}")
        if start >= 0 and end > start:
            return AgentAssessment.model_validate(json.loads(txt[start:end + 1]))
    except Exception:
        return None
    return None
