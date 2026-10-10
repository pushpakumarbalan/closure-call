"""Closure Call API. FastAPI + SSE for the live agent run; serves the built frontend from /."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import agent as agent_mod, config, nws, records
from .decision import decision_phase
from .facility import FACILITIES, get_facility, get_roster, roster_summary
from .models import POSTURE_LABEL, NotificationPackage, Posture, Recommendation
from .notify import build_package
from .pipeline import gather
from .thresholds import ALERT_RULES, NUMERIC_RULES, OPM_LADDER, WATCH_ESCALATION

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="Closure Call", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class EvaluateRequest(BaseModel):
    facility_id: str
    lat: float | None = None
    lon: float | None = None
    drill_note: str | None = None


class NotifyRequest(BaseModel):
    recommendation: Recommendation
    decided_posture: Posture | None = None


class DecideRequest(BaseModel):
    recommendation: Recommendation
    decided_posture: Posture
    decided_by: str = "Facility Manager"
    override_reason: str | None = None
    notification: NotificationPackage | None = None


@app.get("/api/health")
async def health():
    return {"ok": True, "llm_enabled": config.LLM_ENABLED, "llm_model": config.LLM_MODEL_ID if config.LLM_ENABLED else None,
            "llm_host": config.LLM_BASE_URL.split("/")[2] if config.LLM_ENABLED else None, "airnow": bool(config.AIRNOW_API_KEY)}


@app.get("/api/facilities")
async def facilities():
    return [{**f, "roster": roster_summary(f["id"])} for f in FACILITIES]


@app.get("/api/facilities/{fid}")
async def facility(fid: str):
    f = get_facility(fid)
    if not f:
        raise HTTPException(404, "facility not found")
    phase, local_time = decision_phase(f)
    return {**f, "roster": roster_summary(fid), "phase": phase, "local_time": local_time}


@app.get("/api/facilities/{fid}/roster")
async def roster(fid: str):
    if not get_facility(fid):
        raise HTTPException(404, "facility not found")
    return get_roster(fid)


@app.get("/api/alerts/national")
async def alerts_national():
    return await nws.active_alerts_national()


@app.get("/api/alerts/point")
async def alerts_point(lat: float, lon: float):
    return await nws.active_alerts_for_point(lat, lon)


@app.get("/api/zones/centroid")
async def zone_centroid(url: str):
    c = await nws.zone_centroid(url)
    if not c:
        raise HTTPException(404, "zone geometry unavailable")
    return c


@app.get("/api/thresholds")
async def thresholds():
    return {
        "opm_ladder": [{"posture": k, "label": l, "meaning": d} for k, l, d in OPM_LADDER],
        "alert_rules": [{"event": ev, **{k: (v.value if isinstance(v, Posture) else v) for k, v in r.items()}} for ev, r in ALERT_RULES.items()],
        "watch_escalation": WATCH_ESCALATION,
        "numeric_rules": [{**{k: (v.value if isinstance(v, Posture) else v) for k, v in r.items()}} for r in NUMERIC_RULES],
        "posture_labels": {p.value: l for p, l in POSTURE_LABEL.items()},
    }


async def _evidence(req: EvaluateRequest):
    f = get_facility(req.facility_id)
    if not f:
        raise HTTPException(404, "facility not found")
    drill = req.drill_note
    if (req.lat is not None or req.lon is not None) and not drill:
        drill = f"Tabletop exercise: this facility's profile and roster are evaluated against live conditions at {req.lat:.3f}, {req.lon:.3f}."
    return await gather(f, req.lat, req.lon, drill)


@app.post("/api/evaluate")
async def evaluate(req: EvaluateRequest):
    ev = await _evidence(req)
    rec = await agent_mod.recommend(ev)
    return {"recommendation": rec.model_dump(mode="json"), "phase": ev.phase, "local_time": ev.local_time}


@app.post("/api/evaluate/stream")
async def evaluate_stream(req: EvaluateRequest):
    ev = await _evidence(req)

    async def gen():
        yield _sse({"type": "evidence", "phase": ev.phase, "local_time": ev.local_time, "inputs": [s.model_dump(mode="json") for s in ev.signals],
                    "engine_posture": ev.result["posture"].value, "alerts": ev.alerts})
        async for e in agent_mod.recommend_stream(ev):
            yield _sse(e)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"


@app.post("/api/notify")
async def notify(req: NotifyRequest):
    f = get_facility(req.recommendation.facility_id)
    if not f:
        raise HTTPException(404, "facility not found")
    phase, _ = decision_phase(f)
    pkg = build_package(req.recommendation, f, get_roster(f["id"]), phase, req.decided_posture)
    return pkg.model_dump(mode="json")


@app.post("/api/decide")
async def decide(req: DecideRequest):
    f = get_facility(req.recommendation.facility_id)
    if not f:
        raise HTTPException(404, "facility not found")
    if req.decided_posture != req.recommendation.posture and not req.override_reason:
        raise HTTPException(400, "override_reason is required when the decided posture differs from the recommendation")
    notification = req.notification
    if notification is None:
        phase, _ = decision_phase(f)
        notification = build_package(req.recommendation, f, get_roster(f["id"]), phase, req.decided_posture)
    rec = records.append(req.recommendation, req.decided_posture, req.decided_by, req.override_reason, notification)
    return rec.model_dump(mode="json")


@app.get("/api/records")
async def list_records(facility_id: str | None = None, limit: int = 50):
    return records.list_records(facility_id, limit)


@app.get("/api/records/verify")
async def verify():
    return records.verify_chain()


@app.get("/api/records/{rid}")
async def get_record(rid: str):
    r = records.get_record(rid)
    if not r:
        raise HTTPException(404, "record not found")
    return r.model_dump(mode="json")


# ---- static frontend -----------------------------------------------------------------------
if config.STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=config.STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        target = config.STATIC_DIR / path
        if path and target.exists() and target.is_file():
            return FileResponse(target)
        return FileResponse(config.STATIC_DIR / "index.html")
