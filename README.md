# Closure Call

**Weather-driven facility decisions and notification.** Built at Hack Midwest 2026 (Oct 10-11, Kansas City) for the USDA AI Challenge, using the Strands Agents SDK and Akamai Cloud.

When severe weather threatens a facility, a human has to decide: open, delay, dismiss early, send everyone to telework, or close. Then every employee assigned to that building has to be told, fast, with the right instruction. Closure Call puts every input in one place, recommends a graded posture with its reasoning, drafts the notification with per-person include/exclude logic, and writes an append-only decision record so the call can be reconstructed afterward.

The human makes the decision. The system makes sure they have everything, in time, and that the right people hear about it.

## What it does (mapped to the USDA deliverables)

| # | Deliverable | Where |
|---|---|---|
| 1 | Live NWS data, not a mock | `backend/app/nws.py` - alerts by point, hourly forecast, nearest-station observations from `api.weather.gov` |
| 2 | Recommendation with reasoning | `backend/app/decision.py` - posture, every input with source + timestamp, threshold crossed and by how much, confidence, what would change it; `backend/app/agent.py` - Strands agent writes the pasteable rationale |
| 3 | Notification package | `backend/app/notify.py` - recipient list with per-employee reason, drafted email/SMS, channel routing |
| 4 | Decision record | `backend/app/records.py` - append-only SQLite with SHA-256 hash chain, replay UI |
| 5 | Threshold defensibility | `backend/app/thresholds.py` - every cutoff cites NWS criteria / CAP fields / NWPS flood categories / EPA AQI / OPM status ladder; rendered at `/thresholds` |

Supplementary signals beyond NWS: **NOAA NWPS river gauges** (official flood categories per gauge, no key) and **AirNow AQI** (key optional; falls back to NWS Air Quality Alert products). State DOT 511 feeds are per-state and keyed, so that gap is shown honestly in the UI rather than mocked.

## Architecture

```
NWS alerts / forecast / obs ─┐
NWPS river gauges ───────────┼─► pipeline.gather() ─► decision.evaluate() ──► Strands Agent (6 tools) ─► Recommendation
AirNow / NWS AQ products ────┘      (every input        (deterministic,          on Akamai Cloud inference        │
Synthetic facility + roster ─┘       timestamped)         reproducible)           challenges the engine,           ▼
                                                                                   writes the rationale)     notify.build_package()
                                                                                                                    │
                                                                                                                    ▼
                                                                                                      records.append() (hash-chained)
```

- **Backend:** Python 3.12, FastAPI, SSE streaming of the agent run, SQLite.
- **Agent:** [Strands Agents SDK](https://strandsagents.com) with `OpenAIModel` pointed at Akamai Cloud's OpenAI-compatible hosted inference. Tools are closures over the request's evidence, so the agent and the decision record see identical data. If the LLM is unreachable the deterministic rationale is used and labelled as such; the demo never depends on the model being up.
- **Frontend:** React + Vite + Leaflet. Live NWS watches/warnings/advisories WMS layer plus clickable warning polygons from the API.
- **Deploy:** single Docker image, `docker compose up` on a Linode. See `deploy/linode.sh`.

## Run locally

```bash
# backend
cd backend
cp .env.example .env            # fill in LLM_BASE_URL / LLM_API_KEY / LLM_MODEL_ID (Akamai inference handout)
uv venv .venv && source .venv/bin/activate
uv pip install -e .             # or: uv pip install "strands-agents[openai]" fastapi "uvicorn[standard]" httpx pydantic python-dotenv
uvicorn app.main:app --reload --port 8000

# frontend (dev, proxies /api to :8000)
cd frontend && pnpm install && pnpm dev
# or build once and let FastAPI serve it from frontend/dist
cd frontend && pnpm build
```

Open http://localhost:5173 (dev) or http://localhost:8000 (served build).

> macOS note: if `httpx` fails with `FileNotFoundError` on `SSL_CERT_FILE`, that env var points at a missing cert bundle in your shell; `unset SSL_CERT_FILE`.

## Deploy to Akamai Cloud

```bash
./deploy/linode.sh create            # provisions a Linode in us-ord with Docker, then deploys
./deploy/linode.sh deploy <ip>       # redeploy to an existing instance
```

## Demo flow (3 minutes, no slides)

1. Open on the US map. Live NWS warnings are on screen; say what's active right now.
2. Click the KC Service Center, **Evaluate facility now**. Watch the Strands agent call its tools and stream its reasoning on Akamai inference. Posture, confidence, thresholds crossed, "what would change this".
3. Click a live Winter Storm / Tornado / Flash Flood Warning in the feed. The facility profile is exercised against those real conditions. Posture escalates; the rationale names the alert, its CAP fields, and the OPM status.
4. **Build notification**: 26 people, who is in, who is out, and why (on detail, on leave, already teleworking, essential). SMS and email drafted.
5. Change the posture in the dropdown, type an override reason, **Approve & send**. Open **Decision record**: what was known, what was recommended, what was decided, who was told, hash-chained.
6. **Thresholds** tab: show your work.

## Repo layout

```
backend/app/
  nws.py          NWS client + signal builders
  signals.py      NWPS river gauges, AirNow, road-feed stub
  facility.py     synthetic facilities + rosters
  thresholds.py   rule tables with anchors
  decision.py     deterministic engine (posture, margins, confidence, counterfactuals)
  pipeline.py     evidence gathering
  agent.py        Strands agent + tools + streaming
  notify.py       recipients, message, channels
  records.py      append-only hash-chained record
  main.py         FastAPI
frontend/src/     React app (MapView, Panels, Records, App)
deploy/linode.sh  Akamai Cloud deploy
docs/             demo script, YC notes
```
