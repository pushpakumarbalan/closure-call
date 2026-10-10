# Closure Call - YC W27 application notes

Deadline: **Nov 2, 2026, 8pm PT**. Working notes, written during Hack Midwest (Oct 10-11, 2026). Keep the application answers short; YC reads thousands.

## One-liner candidates

- The decision layer for weather-driven operations.
- Everbridge is the pager. We are the brain that decides, explains, and keeps the record.
- When weather hits, we tell multi-site operators what to do, who to tell, and why - in time.

## Company description (50 words)

Closure Call helps organizations with many physical sites decide, in minutes, whether to open, delay, dismiss, or close each one when severe weather hits - and notify exactly the right people. It fuses NWS data with site rosters, recommends a graded posture with cited reasoning, and keeps an audit-grade record.

## What are you building / why now

Every organization with buildings and shift workers makes the same 4am call: school districts, hospital systems, utilities, logistics yards, construction GCs, retail chains, and every federal and state agency. Today it is one person, a weather app, a road map, and a group text. Decisions are inconsistent across sites, slow, and unreconstructable afterward. Mass-notification vendors (Everbridge, AlertMedia, Rave, Regroup) send the message but do not help make the decision; weather-intelligence vendors (Tomorrow.io, DTN, Baron) sell forecasts to enterprises but do not know the roster or the building. Nobody owns the decision itself.

Why now: NWS alerts carry structured CAP fields and are free; NOAA water and air data are open; roster data lives in HRIS/badging APIs; and LLM agents can now read all of it and write a defensible paragraph a manager will actually send. Three years ago the "reasoning" step required a human analyst.

## RFS alignment (Fall 2026)

- **New Operating Systems for the Physical World** (Charlie Warren): 80% of the workforce is deskless; we route a decision to the humans it affects, with the agent as a third worker type.
- **Data for the Real World** (Tindle/Hu): we turn physical-world sensor feeds into a controlled operational decision; weather is the RFS's own example.
- **The Future of American Defense** (Secretary Driscoll): installations face the same closure decision daily; a federal agency is our first design partner.
- **Multiplayer AI** (Epstein): a closure decision is inherently multi-person (facility manager, regional lead, HR, comms). Shared agent session is the natural v2.

## Essential-advice alignment

- *Launch now / 90-10:* one facility type, three hazards, real NWS data, shipped in 24 hours.
- *Do things that don't scale:* onboard the first 10 facility managers by hand; sit with them at 4am; build their threshold table with them.
- *10 customers who love you > 1000 who like you:* district operations directors and hospital emergency managers have a burning problem, not a passing annoyance.
- *Avoid long negotiated deals with big customers:* USDA is the wedge and the credibility, not the first revenue. First paying customers should be mid-size: a 20-school district, a 6-hospital system, a regional utility with 40 service centers.
- *Startups can only solve one problem well:* the decision + notification + record. Not forecasting. Not generic alerting.

## Traction to claim (fill in after the hackathon)

- Hack Midwest 2026 results: [USDA challenge placement], [Strands], [Akamai], [Best in Show / Most Impactful].
- Letters of recommendation from the USDA CTO and CDO (prize) - quote one line.
- Conversations started with USDA leadership about a pilot (be precise: who, what was said, next step and date).
- Working product: live NWS ingest, agent recommendation, notification package, append-only record. Deployed on Akamai Cloud.
- Any school district / hospital / utility conversations started before Nov 2 - aim for 10 user interviews in October; put the three best quotes in the application.

## Business model (first guess, say it's a guess)

Per-site per-year subscription. Comparable: Everbridge is priced per contact; weather-intel vendors price per site or per enterprise. A 30-site customer at $1,500-3,000/site/year is $45-90k ACV; the labor and liability cost of one wrong closure call is far higher. Land with the decision layer; expand into the notification send (replace or sit on top of the incumbent) and the compliance record.

## What's hard / what we'll be wrong about

- Thresholds are local and political. The product must make it easy for each customer to own their table and show their work; we ship anchors, not answers.
- Government sales are slow. We will not wait on them; USDA is credibility, mid-market is revenue.
- Liability framing: we recommend, humans decide, the record protects the decider. Say this plainly.
- The "notification send" is a commodity; the decision and the record are the moat (every decision we record is training data for the next one at that site).

## Founders section prompts

- Why you: [hackathon-built, in KC, deskless-work exposure, whatever is actually true].
- How long have you been working on this: since Oct 10, 2026 (say so; 40% of YC companies apply with just an idea).
- Who are your competitors and what do you understand that they don't: incumbents sell forecasts or messages; the customer's problem is the decision in between, and the record afterward.

## Application video (1 min) outline

1. 10s: the 4am problem, in one sentence.
2. 30s: screen capture of the live demo - alert on the map, agent streams, posture + rationale, notification, record.
3. 15s: who it's for and who we're talking to.
4. 5s: why us.
