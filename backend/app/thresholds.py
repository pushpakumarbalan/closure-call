"""Threshold tables. Every cutoff cites where it came from (deliverable 5: threshold defensibility).

Anchors used:
- CAP fields on NWS alerts (severity / certainty / urgency) and the NWS product ladder (Advisory < Watch < Warning).
- NWS public product criteria (Wind Advisory: sustained 31-39 mph or gusts 46-57; High Wind Warning: sustained
  >= 40 or gusts >= 58; Blizzard: visibility <= 1/4 mi; Severe Thunderstorm: gusts >= 58 mph; Extreme Cold Warning
  in the central plains: wind chill <= -30 F; Cold Weather Advisory: -20 to -29 F; Heat Advisory ~105 F heat index;
  Extreme Heat Warning ~110 F+).
- NOAA NWPS official flood categories per gauge (action / minor / moderate / major).
- EPA AQI breakpoints (151 USG, 201 Unhealthy, 301 Hazardous).
- OPM Washington DC Area Dismissal and Closure Procedures: the graded status ladder (Open, Open with Delayed
  Arrival, Early Departure, Closed to the Public / Unscheduled Leave or Telework, Closed), and the principle that
  emergency (essential) employees report regardless of status.

A rule maps a signal + operator + threshold to a posture. Posture depends on *when* the decision is being made:
`pre_open` (overnight / before the reporting time) vs `in_hours` (facility is occupied).
"""
from __future__ import annotations

from .models import Posture

OPM_URL = "https://www.opm.gov/policy-data-oversight/snow-dismissal-procedures/"
NWS_CAP_URL = "https://www.weather.gov/documentation/services-web-api"
NWS_WIND_URL = "https://www.weather.gov/safety/wind-ww"
NWS_WINTER_URL = "https://www.weather.gov/safety/winter-ww"
NWS_COLD_URL = "https://www.weather.gov/safety/cold-ww"
NWS_HEAT_URL = "https://www.weather.gov/safety/heat-ww"
NWPS_URL = "https://water.noaa.gov/about/flood-categories"
AQI_URL = "https://www.airnow.gov/aqi/aqi-basics/"
NWS_SVR_URL = "https://www.weather.gov/safety/thunderstorm-ww"
NWS_FLOOD_URL = "https://www.weather.gov/safety/flood-ww"

# ---- Alert-product rules: keyed by NWS event name ------------------------------------------------
# posture: {pre_open: Posture, in_hours: Posture}; note is attached to the hit for the manager/notification.
ALERT_RULES: dict[str, dict] = {
    "Blizzard Warning": dict(hazard="winter", pre_open=Posture.CLOSURE, in_hours=Posture.EARLY_DISMISSAL,
        anchor="NWS Blizzard Warning = sustained/gusting winds >= 35 mph with visibility <= 1/4 mi for >= 3 h; OPM treats this as Closed", url=NWS_WINTER_URL,
        note="Travel is impossible or life-threatening during a blizzard; do not dismiss into the storm, time dismissal before onset."),
    "Ice Storm Warning": dict(hazard="winter", pre_open=Posture.CLOSURE, in_hours=Posture.EARLY_DISMISSAL,
        anchor="NWS Ice Storm Warning = >= 1/4 in ice accumulation; roads and power lines fail; OPM Closed", url=NWS_WINTER_URL, note=None),
    "Winter Storm Warning": dict(hazard="winter", pre_open=Posture.TELEWORK, in_hours=Posture.EARLY_DISMISSAL,
        anchor="NWS Winter Storm Warning = significant snow/ice meeting local warning criteria (EAX: >= 6 in/12 h); OPM Closed to public / unscheduled telework", url=NWS_WINTER_URL, note=None),
    "Snow Squall Warning": dict(hazard="winter", pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
        anchor="Snow squalls are short (< 1 h) but cause whiteout pileups; hold departures until it passes", url=NWS_WINTER_URL,
        note="Hold any departures until the squall passes; usually under an hour."),
    "Winter Weather Advisory": dict(hazard="winter", pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
        anchor="NWS Advisory tier = inconvenience, not life-threatening; OPM Open with Delayed Arrival", url=NWS_WINTER_URL, note=None),
    "Freezing Rain Advisory": dict(hazard="winter", pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
        anchor="Advisory tier; black-ice commute risk; OPM Delayed Arrival", url=NWS_WINTER_URL, note=None),
    "Extreme Cold Warning": dict(hazard="winter", pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
        anchor="NWS Extreme Cold Warning (central plains) = wind chill <= -30 F; frostbite in 10 min; delay so commuters travel in daylight", url=NWS_COLD_URL, note=None),
    "Wind Chill Warning": dict(hazard="winter", pre_open=Posture.DELAY, in_hours=Posture.NORMAL, anchor="Legacy name for Extreme Cold Warning", url=NWS_COLD_URL, note=None),
    "Tornado Warning": dict(hazard="severe_storm", pre_open=Posture.DELAY, in_hours=Posture.CLOSURE,
        anchor="CAP severity Extreme / urgency Immediate; NWS: take shelter now. Close to the public and shelter in place; never dismiss during the warning", url=NWS_SVR_URL,
        note="SHELTER IN PLACE. Doors closed to public. Dismiss only after the warning expires."),
    "Severe Thunderstorm Warning": dict(hazard="severe_storm", pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
        anchor="NWS Severe Thunderstorm Warning = gusts >= 58 mph and/or hail >= 1 in; CAP Severe/Immediate", url=NWS_SVR_URL,
        note="Keep staff indoors and away from windows until expiry."),
    "Extreme Wind Warning": dict(hazard="severe_storm", pre_open=Posture.CLOSURE, in_hours=Posture.CLOSURE,
        anchor="Extreme Wind Warning = sustained >= 115 mph (hurricane eyewall); CAP Extreme", url=NWS_WIND_URL, note="Shelter in place."),
    "High Wind Warning": dict(hazard="severe_storm", pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
        anchor="NWS High Wind Warning = sustained >= 40 mph for >= 1 h or gusts >= 58 mph; high-profile vehicle and tree-fall risk", url=NWS_WIND_URL, note=None),
    "Hurricane Warning": dict(hazard="severe_storm", pre_open=Posture.CLOSURE, in_hours=Posture.EARLY_DISMISSAL,
        anchor="Hurricane Warning = hurricane conditions expected within 36 h; follow local evacuation orders", url=NWS_WIND_URL, note=None),
    "Tropical Storm Warning": dict(hazard="severe_storm", pre_open=Posture.TELEWORK, in_hours=Posture.EARLY_DISMISSAL,
        anchor="Tropical Storm Warning = sustained 39-73 mph expected within 36 h", url=NWS_WIND_URL, note=None),
    "Flash Flood Warning": dict(hazard="flood", pre_open=Posture.TELEWORK, in_hours=Posture.EARLY_DISMISSAL,
        anchor="CAP Severe/Immediate; most flood deaths are in vehicles; dismiss before roads are under water (Turn Around Don't Drown)", url=NWS_FLOOD_URL, note=None),
    "Flash Flood Emergency": dict(hazard="flood", pre_open=Posture.CLOSURE, in_hours=Posture.CLOSURE,
        anchor="Rare, catastrophic tier above Flash Flood Warning; CAP Extreme", url=NWS_FLOOD_URL, note="Shelter in place on upper floors."),
    "Flood Warning": dict(hazard="flood", pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
        anchor="River Flood Warning = gauge at/above flood stage; impact depends on commute routes; pair with NWPS gauge category", url=NWS_FLOOD_URL, note=None),
    "Coastal Flood Warning": dict(hazard="flood", pre_open=Posture.DELAY, in_hours=Posture.NORMAL, anchor="Coastal inundation of roads expected", url=NWS_FLOOD_URL, note=None),
    "Extreme Heat Warning": dict(hazard="heat", pre_open=Posture.TELEWORK, in_hours=Posture.NORMAL,
        anchor="NWS Extreme Heat Warning ~ heat index >= 110 F; field and outdoor duties suspended; eligible staff telework", url=NWS_HEAT_URL, note="Suspend outdoor field work."),
    "Excessive Heat Warning": dict(hazard="heat", pre_open=Posture.TELEWORK, in_hours=Posture.NORMAL, anchor="Legacy name for Extreme Heat Warning", url=NWS_HEAT_URL, note=None),
    "Air Quality Alert": dict(hazard="air_quality", pre_open=Posture.TELEWORK, in_hours=Posture.NORMAL,
        anchor="State-issued via NWS when AQI forecast >= 101-151; sensitive groups and telework-eligible staff work from home", url=AQI_URL,
        note="Applies to telework-eligible staff; office stays open with essential staff."),
}

# Watches and lesser products are tracked as "monitor" near-misses so the manager sees what could escalate.
WATCH_ESCALATION: dict[str, str] = {
    "Tornado Watch": "Tornado Warning", "Severe Thunderstorm Watch": "Severe Thunderstorm Warning",
    "Winter Storm Watch": "Winter Storm Warning", "Flash Flood Watch": "Flash Flood Warning", "Flood Watch": "Flood Warning",
    "High Wind Watch": "High Wind Warning", "Extreme Cold Watch": "Extreme Cold Warning", "Extreme Heat Watch": "Extreme Heat Warning",
    "Hurricane Watch": "Hurricane Warning", "Tropical Storm Watch": "Tropical Storm Warning", "Wind Advisory": "High Wind Warning",
    "Flood Advisory": "Flood Warning", "Cold Weather Advisory": "Extreme Cold Warning", "Heat Advisory": "Extreme Heat Warning",
    "Red Flag Warning": "Air Quality Alert", "Fire Weather Watch": "Red Flag Warning",
}

# ---- Numeric rules: (signal_key, operator, threshold) -> posture --------------------------------
# `value_path` lets us reach into dict-valued signals (river gauges).
NUMERIC_RULES: list[dict] = [
    dict(id="wind_warning_obs", near=8, hazard="severe_storm", signal="obs_wind_mph", op=">=", threshold=40, pre_open=Posture.TELEWORK, in_hours=Posture.NORMAL,
         desc="Observed sustained wind at High Wind Warning criterion", anchor="NWS High Wind Warning: sustained >= 40 mph", url=NWS_WIND_URL),
    dict(id="gust_severe_obs", near=10, hazard="severe_storm", signal="obs_gust_mph", op=">=", threshold=58, pre_open=Posture.TELEWORK, in_hours=Posture.NORMAL,
         desc="Observed gust at severe criterion", anchor="NWS severe thunderstorm / High Wind Warning gust criterion: >= 58 mph", url=NWS_WIND_URL),
    dict(id="wind_advisory_obs", near=6, hazard="severe_storm", signal="obs_wind_mph", op=">=", threshold=31, pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
         desc="Observed sustained wind at Wind Advisory criterion", anchor="NWS Wind Advisory: sustained 31-39 mph", url=NWS_WIND_URL),
    dict(id="gust_advisory_obs", near=8, hazard="severe_storm", signal="obs_gust_mph", op=">=", threshold=46, pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
         desc="Observed gust at Wind Advisory criterion", anchor="NWS Wind Advisory: gusts 46-57 mph", url=NWS_WIND_URL),
    dict(id="fcst_wind_warning", near=8, hazard="severe_storm", signal="fcst_wind_max_mph", op=">=", threshold=40, pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
         desc="Forecast wind reaches High Wind Warning criterion in next 12 h", anchor="NWS High Wind Warning: sustained >= 40 mph", url=NWS_WIND_URL),
    dict(id="windchill_extreme_obs", near=8, hazard="winter", signal="obs_wind_chill_f", op="<=", threshold=-30, pre_open=Posture.TELEWORK, in_hours=Posture.NORMAL,
         desc="Observed wind chill at Extreme Cold Warning criterion", anchor="NWS (central plains) Extreme Cold Warning: wind chill <= -30 F", url=NWS_COLD_URL),
    dict(id="windchill_advisory_obs", near=8, hazard="winter", signal="obs_wind_chill_f", op="<=", threshold=-20, pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
         desc="Observed wind chill at Cold Weather Advisory criterion", anchor="NWS (central plains) Cold Weather Advisory: wind chill -20 to -29 F", url=NWS_COLD_URL),
    dict(id="visibility_blizzard_obs", near=0.75, hazard="winter", signal="obs_visibility_mi", op="<=", threshold=0.25, pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
         desc="Observed visibility at blizzard criterion", anchor="NWS Blizzard criterion: visibility <= 1/4 mi", url=NWS_WINTER_URL),
    dict(id="fcst_wintry_commute", near=2, hazard="winter", signal="fcst_wintry_hours", op=">=", threshold=6, pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
         desc="Wintry precipitation forecast across most of the commute window", anchor="6 of next 12 forecast hours wintry = both commutes affected; OPM Delayed Arrival", url=OPM_URL),
    dict(id="heat_extreme_obs", near=6, hazard="heat", signal="obs_heat_index_f", op=">=", threshold=110, pre_open=Posture.TELEWORK, in_hours=Posture.NORMAL,
         desc="Observed heat index at Extreme Heat Warning criterion", anchor="NWS Extreme Heat Warning ~ heat index >= 110 F", url=NWS_HEAT_URL),
    dict(id="heat_advisory_obs", near=6, hazard="heat", signal="obs_heat_index_f", op=">=", threshold=105, pre_open=Posture.NORMAL, in_hours=Posture.NORMAL,
         desc="Observed heat index at Heat Advisory criterion (monitor; suspend outdoor work)", anchor="NWS Heat Advisory ~ heat index >= 105 F", url=NWS_HEAT_URL),
    dict(id="river_major", near=1, hazard="flood", signal="river:*", value_path="worst_rank", op=">=", threshold=4, pre_open=Posture.CLOSURE, in_hours=Posture.EARLY_DISMISSAL,
         desc="River gauge at MAJOR flood category (observed or forecast)", anchor="NOAA NWPS official flood category: major = extensive inundation, evacuations", url=NWPS_URL),
    dict(id="river_moderate", near=1, hazard="flood", signal="river:*", value_path="worst_rank", op=">=", threshold=3, pre_open=Posture.TELEWORK, in_hours=Posture.NORMAL,
         desc="River gauge at MODERATE flood category (observed or forecast)", anchor="NOAA NWPS: moderate = some inundation of structures and roads near stream", url=NWPS_URL),
    dict(id="river_minor", near=1, hazard="flood", signal="river:*", value_path="worst_rank", op=">=", threshold=2, pre_open=Posture.DELAY, in_hours=Posture.NORMAL,
         desc="River gauge at MINOR flood category (observed or forecast)", anchor="NOAA NWPS: minor = minimal property threat, some public roads flooded", url=NWPS_URL),
    dict(id="aqi_hazardous", near=40, hazard="air_quality", signal="aqi", op=">=", threshold=301, pre_open=Posture.CLOSURE, in_hours=Posture.EARLY_DISMISSAL,
         desc="AQI Hazardous", anchor="EPA AQI >= 301 Hazardous: everyone should avoid all outdoor exertion", url=AQI_URL),
    dict(id="aqi_unhealthy", near=30, hazard="air_quality", signal="aqi", op=">=", threshold=201, pre_open=Posture.TELEWORK, in_hours=Posture.NORMAL,
         desc="AQI Very Unhealthy", anchor="EPA AQI >= 201 Very Unhealthy: health alert for everyone", url=AQI_URL),
    dict(id="aqi_usg", near=30, hazard="air_quality", signal="aqi", op=">=", threshold=151, pre_open=Posture.TELEWORK, in_hours=Posture.NORMAL,
         desc="AQI Unhealthy (sensitive groups and telework-eligible staff work from home)", anchor="EPA AQI >= 151 Unhealthy", url=AQI_URL),
]

# Combination rule: an alert whose CAP triplet is maximal is a reason to escalate one notch regardless of product.
CAP_EXTREME = dict(id="cap_extreme_immediate_observed", hazard="any",
    desc="CAP severity Extreme + urgency Immediate + certainty Observed on any product",
    anchor="CAP (OASIS Common Alerting Protocol) fields carried on every NWS alert; the maximal triplet is the strongest signal NWS can send", url=NWS_CAP_URL)

OPM_LADDER = [
    ("normal", "Open", "Employees are expected to report to the office on time."),
    ("delay", "Open with Delayed Arrival", "Employees should plan to arrive no more than N hours later than normal, with unscheduled leave/telework available."),
    ("early_dismissal", "Open with Early Departure", "Employees should depart N hours earlier than normal departure time."),
    ("telework", "Closed to the Public / Unscheduled Leave or Telework", "Telework-eligible employees work from home; others take unscheduled leave; emergency employees report."),
    ("closure", "Closed", "Facility is closed. Only designated emergency employees report."),
]
