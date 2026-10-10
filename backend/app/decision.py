"""Deterministic decision engine: inputs -> graded posture with full reasoning.

The agent (agent.py) calls this as a tool and writes the plain-language rationale; the engine is the thing
that has to be reproducible for the decision record, so it never depends on the LLM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .models import POSTURE_LABEL, POSTURE_RANK, Posture, Signal, ThresholdHit
from .thresholds import ALERT_RULES, CAP_EXTREME, NUMERIC_RULES, WATCH_ESCALATION

OPS = {
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
}


def decision_phase(facility: dict, at: datetime | None = None) -> tuple[str, str]:
    """Return (phase, local_time_str). pre_open covers overnight and weekends: the question is 'what do we do at next opening'."""
    tz = ZoneInfo(facility.get("timezone", "UTC"))
    now = (at or datetime.now(timezone.utc)).astimezone(tz)
    open_h, open_m = map(int, facility["hours"]["open"].split(":"))
    close_h, close_m = map(int, facility["hours"]["close"].split(":"))
    weekday = now.strftime("%a")
    in_days = weekday in facility["hours"]["days"]
    mins = now.hour * 60 + now.minute
    if in_days and (open_h * 60 + open_m) <= mins < (close_h * 60 + close_m):
        return "in_hours", now.isoformat(timespec="minutes")
    return "pre_open", now.isoformat(timespec="minutes")


def _bump(p: Posture, phase: str) -> Posture:
    """Escalate one notch on the ladder that makes sense for the phase: early dismissal is an in-hours concept,
    delayed arrival is a pre-open concept."""
    ladder = [Posture.NORMAL, Posture.DELAY, Posture.TELEWORK, Posture.CLOSURE] if phase == "pre_open" else \
             [Posture.NORMAL, Posture.EARLY_DISMISSAL, Posture.TELEWORK, Posture.CLOSURE]
    if p not in ladder:
        ladder = sorted(POSTURE_RANK, key=POSTURE_RANK.get)
    return ladder[min(len(ladder) - 1, ladder.index(p) + 1)]


def _match_signals(signals: list[Signal], pattern: str) -> list[Signal]:
    if pattern.endswith("*"):
        return [s for s in signals if s.key.startswith(pattern[:-1])]
    return [s for s in signals if s.key == pattern]


def _margin_text(op: str, threshold: float, observed: float, unit: str | None) -> str:
    u = f" {unit}" if unit else ""
    diff = observed - threshold
    if op in (">=", ">"):
        return f"{abs(diff):.1f}{u} {'over' if diff >= 0 else 'under'} the {threshold}{u} threshold"
    return f"{abs(diff):.1f}{u} {'under' if diff <= 0 else 'over'} the {threshold}{u} threshold"


def evaluate(facility: dict, signals: list[Signal], phase: str) -> dict:
    triggered: list[ThresholdHit] = []
    near: list[ThresholdHit] = []
    hazards: set[str] = set()
    notes: list[str] = []

    # ---- alert products
    alert_sigs = [s for s in signals if s.key.startswith("nws_alert:") and isinstance(s.value, dict)]
    for s in alert_sigs:
        event = s.key.split(":", 1)[1]
        v = s.value or {}
        rule = ALERT_RULES.get(event)
        if rule:
            posture = rule[phase]
            hazards.add(rule["hazard"])
            if rule.get("note"):
                notes.append(rule["note"])
            triggered.append(ThresholdHit(
                rule_id=f"alert:{event}", hazard=rule["hazard"], signal_key=s.key,
                description=f"{event} in effect ({v.get('severity')}/{v.get('certainty')}/{v.get('urgency')})",
                operator="in_effect", threshold="warning issued", observed=f"{event} until {s.detail.get('ends') or s.detail.get('expires')}",
                margin_text=f"CAP severity {v.get('severity')}, certainty {v.get('certainty')}, urgency {v.get('urgency')}",
                posture=posture, anchor=rule["anchor"], anchor_url=rule["url"],
            ))
            if v.get("severity") == "Extreme" and v.get("urgency") == "Immediate" and v.get("certainty") == "Observed" and posture != Posture.CLOSURE:
                triggered.append(ThresholdHit(
                    rule_id=CAP_EXTREME["id"], hazard=rule["hazard"], signal_key=s.key, description=CAP_EXTREME["desc"],
                    operator="==", threshold="Extreme/Immediate/Observed", observed=f"{v.get('severity')}/{v.get('urgency')}/{v.get('certainty')}",
                    margin_text="maximal CAP triplet: escalate one notch", posture=_bump(posture, phase), anchor=CAP_EXTREME["anchor"], anchor_url=CAP_EXTREME["url"],
                ))
        elif event in WATCH_ESCALATION:
            target = WATCH_ESCALATION[event]
            trule = ALERT_RULES.get(target)
            if trule:
                hazards.add(trule["hazard"])
                near.append(ThresholdHit(
                    rule_id=f"watch:{event}", hazard=trule["hazard"], signal_key=s.key,
                    description=f"{event} in effect; would become {POSTURE_LABEL[trule[phase]]} if upgraded to {target}",
                    operator="monitor", threshold=target, observed=event, margin_text="one product tier below the threshold",
                    posture=trule[phase], anchor=f"NWS product ladder: Watch/Advisory -> Warning. {trule['anchor']}", anchor_url=trule["url"],
                ))

    # ---- numeric rules
    for rule in NUMERIC_RULES:
        for s in _match_signals(signals, rule["signal"]):
            val = s.value
            if isinstance(val, dict):
                val = val.get(rule.get("value_path", ""))
            if val is None:
                continue
            try:
                val = float(val)
            except (TypeError, ValueError):
                continue
            thr = float(rule["threshold"])
            hit = ThresholdHit(
                rule_id=rule["id"], hazard=rule["hazard"], signal_key=s.key, description=rule["desc"], operator=rule["op"], threshold=rule["threshold"],
                observed=val, margin_text=_margin_text(rule["op"], thr, val, s.unit if not isinstance(s.value, dict) else "category rank"),
                posture=rule[phase], anchor=rule["anchor"], anchor_url=rule["url"],
            )
            if OPS[rule["op"]](val, thr):
                triggered.append(hit)
                hazards.add(rule["hazard"])
            else:
                # near miss: inside the rule's `near` window (explicit per rule, else 10% of threshold, min 1 unit)
                span = float(rule.get("near", max(abs(thr) * 0.10, 1.0)))
                if abs(val - thr) <= span:
                    near.append(hit)
                    hazards.add(rule["hazard"])

    # Collapse to the most restrictive posture (but keep every trigger for the record).
    posture = Posture.NORMAL
    for h in triggered:
        if POSTURE_RANK[h.posture] > POSTURE_RANK[posture]:
            posture = h.posture
    # Dedupe lower-tier numeric rules on the same signal when a higher one fired (e.g. gust >= 58 also satisfies >= 46).
    seen: set[tuple[str, str]] = set()
    dedup: list[ThresholdHit] = []
    for h in sorted(triggered, key=lambda h: -POSTURE_RANK[h.posture]):
        k = (h.signal_key, h.hazard)
        if h.rule_id.startswith("alert:") or h.rule_id == CAP_EXTREME["id"] or k not in seen:
            dedup.append(h)
            seen.add(k)
    triggered = dedup

    # ---- confidence
    conf, reasons = _confidence(signals, triggered, phase)

    # ---- what would change the recommendation
    changes: list[str] = []
    for h in triggered:
        if h.rule_id.startswith("alert:"):
            changes.append(f"If NWS cancels or lets the {h.signal_key.split(':', 1)[1]} expire ({h.observed.split(' until ')[-1]}), this driver drops out.")
        else:
            changes.append(f"If {h.signal_key} falls back past {h.operator} {h.threshold}, the {POSTURE_LABEL[h.posture]} driver clears.")
    for h in near:
        changes.append(f"If {h.description.split(';')[0].lower()} crosses {h.operator} {h.threshold} (currently {h.observed}), recommendation rises to {POSTURE_LABEL[h.posture]}.")
    if posture == Posture.NORMAL and not near:
        changes.append("Any NWS Warning-tier product for this point would move the recommendation off Normal; Watches are tracked here as they appear.")
    if phase == "pre_open":
        changes.append("Re-evaluate 60 minutes before the earliest shift start; forecast confidence improves sharply inside 6 hours.")

    return {
        "posture": posture,
        "posture_label": POSTURE_LABEL[posture],
        "hazards": sorted(hazards),
        "triggered": triggered,
        "near_misses": near,
        "confidence": conf,
        "confidence_reasons": reasons,
        "what_would_change": changes[:8],
        "notes": list(dict.fromkeys(notes)),
    }


def _confidence(signals: list[Signal], triggered: list[ThresholdHit], phase: str) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.55
    alert_sigs = [s for s in signals if s.key.startswith("nws_alert:") and isinstance(s.value, dict)]
    if any(s.key == "nws_alert:error" for s in signals):
        score -= 0.2; reasons.append("NWS alerts feed was unavailable at evaluation time.")
    if alert_sigs:
        cert = max(s.value.get("certainty_rank", 0) for s in alert_sigs)
        if cert >= 4:
            score += 0.25; reasons.append("At least one NWS product carries certainty=Observed.")
        elif cert == 3:
            score += 0.15; reasons.append("Strongest NWS certainty is Likely.")
        else:
            score += 0.0; reasons.append("NWS certainty is Possible or lower.")
    obs = [s for s in signals if s.key.startswith("obs_")]
    if obs:
        score += 0.1; reasons.append(f"Ground truth from a nearby NWS station ({len(obs)} observed fields).")
    else:
        score -= 0.1; reasons.append("No recent station observation available; relying on forecast and alerts.")
    numeric_hits = [h for h in triggered if not h.rule_id.startswith("alert:")]
    alert_hits = [h for h in triggered if h.rule_id.startswith("alert:")]
    if numeric_hits and alert_hits:
        score += 0.1; reasons.append("Alert products and measured conditions agree.")
    if any(s.key == "roads" and s.value is None for s in signals):
        score -= 0.05; reasons.append("State DOT road feed not configured; commute impact is inferred, not observed.")
    if any(s.key.startswith("river:") and s.value is None for s in signals):
        score -= 0.05; reasons.append("A configured river gauge was unavailable.")
    if phase == "pre_open":
        reasons.append("Pre-opening decision: conditions can change before the reporting time.")
    return round(max(0.05, min(0.98, score)), 2), reasons


def deterministic_rationale(facility: dict, result: dict, signals: list[Signal], phase: str, local_time: str) -> str:
    """Template rationale used when the LLM is unavailable, and as the floor the agent must improve on."""
    p = result["posture_label"]
    when = "before opening" if phase == "pre_open" else "during operating hours"
    drivers = result["triggered"]
    if not drivers:
        return (f"As of {local_time}, no NWS warning-tier products or measured conditions at {facility['name']} cross a closure threshold, "
                f"so the recommendation is {p}. " + (f"Monitoring: {'; '.join(h.description for h in result['near_misses'][:2])}. " if result["near_misses"] else "")
                + f"Confidence {int(result['confidence']*100)}%. Re-evaluate before the earliest shift start.")
    top = drivers[0]
    others = "; ".join(f"{h.description} ({h.margin_text})" for h in drivers[1:3])
    return (f"As of {local_time} ({when}), the recommendation for {facility['name']} is {p}. The primary driver is {top.description}: "
            f"{top.margin_text}. Anchor: {top.anchor}. " + (f"Supporting inputs: {others}. " if others else "")
            + f"Confidence {int(result['confidence']*100)}% ({result['confidence_reasons'][0] if result['confidence_reasons'] else ''}). "
            + (f"{result['notes'][0]} " if result["notes"] else "")
            + "Essential personnel report as scheduled regardless of posture.")
