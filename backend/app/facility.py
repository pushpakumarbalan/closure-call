"""Synthetic facility model + employee roster.

One primary profile (a USDA Service Center in the KC metro) handled well, plus two more facilities so the
map and the roster logic are visibly multi-site. Nothing here is real PII.
"""
from __future__ import annotations

import random
from datetime import date

FACILITIES: list[dict] = [
    {
        "id": "usda-kc-sc",
        "name": "USDA Service Center - Kansas City (Jackson County)",
        "agency": "FSA / NRCS / RD",
        "type": "Service Center",
        "address": "3605 NE Independence Ave, Kansas City, MO",
        "state": "MO",
        "lat": 39.1113,
        "lon": -94.5318,
        "timezone": "America/Chicago",
        "hours": {"open": "07:30", "close": "16:30", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"]},
        "river_gauges": ["KCDM7"],
        "road_feed": None,
        "road_feed_hint": "MoDOT Traveler Information Map",
        "road_feed_hint_url": "https://traveler.modot.org/map/",
        "hazard_profile": ["winter", "severe_storm", "flood"],
        "notes": "Public-facing county office; walk-in producers; parking lot drains poorly in heavy rain.",
        "primary": True,
    },
    {
        "id": "usda-ars-ames",
        "name": "USDA ARS National Animal Disease Center - Ames, IA",
        "agency": "ARS",
        "type": "Research Lab",
        "address": "1920 Dayton Ave, Ames, IA",
        "state": "IA",
        "lat": 42.0458,
        "lon": -93.6372,
        "timezone": "America/Chicago",
        "hours": {"open": "07:00", "close": "17:00", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"]},
        "river_gauges": ["AMEI4"],
        "road_feed": None,
        "road_feed_hint": "Iowa 511",
        "road_feed_hint_url": "https://511ia.org/",
        "hazard_profile": ["winter", "severe_storm", "flood"],
        "notes": "Live animal care is 24/7 essential; biosecurity staff cannot telework.",
        "primary": False,
    },
    {
        "id": "usda-fs-boise",
        "name": "USDA Forest Service - Boise National Forest SO",
        "agency": "FS",
        "type": "Field Office",
        "address": "1249 S Vinnell Way, Boise, ID",
        "state": "ID",
        "lat": 43.5926,
        "lon": -116.2800,
        "timezone": "America/Boise",
        "hours": {"open": "08:00", "close": "16:30", "days": ["Mon", "Tue", "Wed", "Thu", "Fri"]},
        "river_gauges": ["BIGI1"],
        "road_feed": None,
        "road_feed_hint": "Idaho 511",
        "road_feed_hint_url": "https://511.idaho.gov/",
        "hazard_profile": ["air_quality", "winter", "heat"],
        "notes": "Wildfire smoke season; dispatch center is essential.",
        "primary": False,
    },
]

FIRST = ["Maria", "James", "Aisha", "Daniel", "Grace", "Luis", "Hannah", "Marcus", "Priya", "Ethan", "Nora", "Samuel",
         "Leah", "Omar", "Chloe", "Victor", "Ruth", "Andre", "Mei", "Caleb", "Sofia", "Isaac", "Jasmine", "Owen", "Elena"]
LAST = ["Alvarez", "Nguyen", "Okafor", "Brooks", "Kim", "Patel", "Schmidt", "Washington", "Hernandez", "Fischer",
        "Thompson", "Reyes", "Morgan", "Shah", "Bennett", "Olsen", "Carter", "Diaz", "Lindqvist", "Hughes"]

ROLES = [
    ("Facility Manager", True, False), ("Security Officer", True, False), ("Building Maintenance", True, False),
    ("County Executive Director", False, True), ("Program Technician", False, True), ("Program Technician", False, True),
    ("Program Technician", False, True), ("Soil Conservationist", False, True), ("District Conservationist", False, True),
    ("Loan Officer", False, True), ("Loan Specialist", False, True), ("Administrative Assistant", False, True),
    ("Civil Engineering Tech", False, True), ("Rangeland Specialist", False, True), ("IT Specialist", False, True),
    ("Outreach Coordinator", False, True), ("Farm Loan Manager", False, True), ("Receptionist", False, False),
    ("Animal Caretaker", True, False), ("Biosecurity Lead", True, False), ("Dispatcher", True, False),
    ("Wildlife Biologist", False, True), ("Hydrologist", False, True), ("Budget Analyst", False, True),
]


def _roster_for(fid: str, n: int, seed: int) -> list[dict]:
    rnd = random.Random(seed)
    roster = []
    for i in range(n):
        role, essential, telework_eligible = ROLES[i % len(ROLES)]
        if fid == "usda-kc-sc" and role in ("Animal Caretaker", "Biosecurity Lead", "Dispatcher"):
            role, essential, telework_eligible = "Program Technician", False, True
        if essential:  # emergency personnel are onsite or on leave; they don't telework or detail out casually
            status = rnd.choices(["onsite", "leave"], weights=[92, 8])[0]
        else:
            status = rnd.choices(["onsite", "telework_today", "on_detail", "leave"], weights=[66, 18, 9, 7])[0]
        roster.append({
            "employee_id": f"{fid}-{i+1:03d}",
            "name": f"{rnd.choice(FIRST)} {rnd.choice(LAST)}",
            "role": role,
            "assigned_facility": fid,
            "essential": essential,
            "telework_eligible": telework_eligible,
            "status_today": status,  # onsite | telework_today | on_detail | leave
            "detail_location": rnd.choice(["Regional Office - St. Louis", "Training - Fort Collins", "Field - Cass County"]) if status == "on_detail" else None,
            "accessibility_needs": rnd.random() < 0.08,
            "commute_miles": rnd.randint(3, 48),
            "channels": {"email": True, "sms": rnd.random() < 0.9, "voice": rnd.random() < 0.3},
            "shift_start": "06:00" if essential else "07:30",
        })
    return roster


ROSTERS: dict[str, list[dict]] = {
    "usda-kc-sc": _roster_for("usda-kc-sc", 26, seed=26),
    "usda-ars-ames": _roster_for("usda-ars-ames", 34, seed=34),
    "usda-fs-boise": _roster_for("usda-fs-boise", 22, seed=22),
}


def get_facility(fid: str) -> dict | None:
    return next((f for f in FACILITIES if f["id"] == fid), None)


def get_roster(fid: str) -> list[dict]:
    return ROSTERS.get(fid, [])


def roster_summary(fid: str) -> dict:
    r = get_roster(fid)
    return {
        "total": len(r),
        "essential": sum(1 for e in r if e["essential"]),
        "telework_eligible": sum(1 for e in r if e["telework_eligible"]),
        "onsite_today": sum(1 for e in r if e["status_today"] == "onsite"),
        "telework_today": sum(1 for e in r if e["status_today"] == "telework_today"),
        "on_detail": sum(1 for e in r if e["status_today"] == "on_detail"),
        "leave": sum(1 for e in r if e["status_today"] == "leave"),
        "accessibility_needs": sum(1 for e in r if e["accessibility_needs"]),
        "as_of": date.today().isoformat(),
    }
