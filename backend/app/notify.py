"""Notification package: right people, right channel, right time, right content.

Recipient logic is explicit per employee so the manager (and the record) can see who was included and why.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .models import POSTURE_LABEL, NotificationPackage, Posture, Recipient, Recommendation

INSTRUCTIONS = {
    Posture.NORMAL: {"default": "Report as scheduled. Monitor email for updates.",
                     "essential": "Report as scheduled."},
    Posture.DELAY: {"default": "Delayed arrival: report up to 2 hours after your normal start, or request unscheduled leave/telework.",
                    "telework": "Delayed arrival in effect: you may begin telework at your normal start time instead of commuting.",
                    "essential": "Essential personnel: report at your scheduled shift start. Allow extra travel time."},
    Posture.EARLY_DISMISSAL: {"default": "Early departure: leave 2 hours before your normal end time. Do not wait for the hazard to arrive.",
                              "telework": "Early departure: finish the day via telework if you can leave now safely.",
                              "essential": "Essential personnel: remain until relieved per the continuity plan."},
    Posture.TELEWORK: {"default": "The office is closed to the public. Take unscheduled leave or telework.",
                       "telework": "The office is closed to the public. Telework for the full day; do not come in.",
                       "essential": "Essential personnel: report as scheduled. The building is open to staff only."},
    Posture.CLOSURE: {"default": "The facility is CLOSED. Do not report. Non-essential employees are excused (weather and safety leave).",
                      "telework": "The facility is CLOSED. Telework-eligible employees telework; do not report in person.",
                      "essential": "Essential personnel: report as scheduled per the continuity plan unless your supervisor contacts you."},
}


def _instruction(posture: Posture, emp: dict) -> str:
    table = INSTRUCTIONS[posture]
    if emp["essential"]:
        return table.get("essential", table["default"])
    if emp["telework_eligible"] and "telework" in table:
        return table["telework"]
    return table["default"]


def _channels(posture: Posture, emp: dict, pre_open: bool) -> list[str]:
    ch = ["email"]
    urgent = posture in (Posture.CLOSURE, Posture.TELEWORK, Posture.EARLY_DISMISSAL) or (posture == Posture.DELAY and pre_open)
    if urgent and emp["channels"].get("sms"):
        ch.append("sms")
    if posture == Posture.CLOSURE and emp["channels"].get("voice"):
        ch.append("voice")
    if emp["accessibility_needs"] and urgent:
        ch.append("voice" if "voice" not in ch else "tty")
    if emp["essential"] and urgent:
        ch.append("voice" if "voice" not in ch else "supervisor_call")
    return ch


def build_recipients(posture: Posture, roster: list[dict], pre_open: bool) -> list[Recipient]:
    out: list[Recipient] = []
    for e in roster:
        included, reason = True, ""
        if e["status_today"] == "leave":
            included, reason = False, "On approved leave today; not expected at the facility."
        elif e["status_today"] == "on_detail":
            included, reason = False, f"On detail at {e['detail_location']}; this facility's status does not apply."
        elif e["status_today"] == "telework_today" and posture in (Posture.NORMAL, Posture.DELAY, Posture.EARLY_DISMISSAL):
            included, reason = False, "Already scheduled to telework today; an arrival/departure change does not affect them."
        elif e["status_today"] == "telework_today":
            included, reason = True, "Scheduled telework today; included because the facility status changes public access and may affect tomorrow."
        elif e["essential"]:
            reason = "Essential personnel: reporting requirement does not change; must receive status and safety instruction."
        elif e["accessibility_needs"]:
            reason = "Assigned to this facility today; flagged for accessibility needs, so voice channel added."
        else:
            reason = "Assigned to this facility and expected onsite today."
        if posture == Posture.NORMAL and included and not e["essential"]:
            # Normal ops: informational email only to onsite staff; don't wake people up.
            reason += " Informational only; email channel only."
        out.append(Recipient(employee_id=e["employee_id"], name=e["name"], role=e["role"], included=included, reason=reason,
                             channels=_channels(posture, e, pre_open) if included else [], instruction=_instruction(posture, e) if included else ""))
    return out


def build_package(rec: Recommendation, facility: dict, roster: list[dict], phase: str, decided_posture: Posture | None = None) -> NotificationPackage:
    posture = decided_posture or rec.posture
    pre_open = phase == "pre_open"
    tz = ZoneInfo(facility.get("timezone", "UTC"))
    now_local = datetime.now(tz)
    stamp = now_local.strftime("%a %b %d, %I:%M %p %Z")
    recipients = build_recipients(posture, roster, pre_open)
    inc = [r for r in recipients if r.included]
    drivers = "; ".join(h.description for h in rec.triggered[:2]) or "no warning-tier hazards at this time"
    subject = f"[{facility['name'].split(' - ')[0]}] Operating status {now_local.strftime('%m/%d')}: {POSTURE_LABEL[posture]}"
    message = (
        f"OPERATING STATUS - {facility['name']}\n"
        f"Effective: {stamp}\n"
        f"Status: {POSTURE_LABEL[posture].upper()}\n\n"
        f"Why: {drivers}.\n\n"
        f"What this means for you:\n"
        f"- Non-essential staff: {INSTRUCTIONS[posture]['default']}\n"
        f"- Telework-eligible staff: {INSTRUCTIONS[posture].get('telework', INSTRUCTIONS[posture]['default'])}\n"
        f"- Essential personnel: {INSTRUCTIONS[posture].get('essential', 'Report as scheduled.')}\n\n"
        f"If you are on detail or approved leave today this message does not change your status.\n"
        f"Questions: contact your supervisor. Updates will follow if conditions change.\n\n"
        f"Decision basis (for the record): {rec.rationale}"
    )
    sms = f"{facility['name'].split(' - ')[0]} {now_local.strftime('%m/%d')}: {POSTURE_LABEL[posture]}. {INSTRUCTIONS[posture]['default'][:90]} Check email for details."
    summary: dict[str, int] = {}
    for r in inc:
        for c in r.channels:
            summary[c] = summary.get(c, 0) + 1
    return NotificationPackage(posture=posture, subject=subject, message=message, sms=sms[:160], recipients=recipients,
                               included_count=len(inc), excluded_count=len(recipients) - len(inc), channel_summary=summary)
