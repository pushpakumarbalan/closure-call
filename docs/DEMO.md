# Closure Call - 3-minute pitch script (no slides)

Rules: 3 minutes, show the prototype only, be signed in already, name the sponsor challenges out loud.
Challenges entered: **USDA AI Challenge (Closure Call)**, **Best Use of Strands Agents SDK**, **Akamai Cloud AI App**.

## Pre-flight (10 min before)

- [ ] `curl http://<host>/api/health` shows `llm_enabled: true`.
- [ ] Open the app at the US map. Confirm live NWS WWA overlay is painting and the alert feed shows warnings.
- [ ] Pick the exercise target: the most dramatic **warning with a polygon** on the map right now (Tornado > Flash Flood > Winter Storm > High Wind). Note its name. If nothing dramatic, a Winter Storm Warning zone works fine.
- [ ] Run one evaluation and one exercise ahead of time so the NWS responses are cached and the agent is warm (first call is slowest).
- [ ] Decision record has at least 2 entries so the chain is visible.
- [ ] Browser zoom ~110%, right column visible. Close other tabs.

## Script (timings cumulative)

**0:00 - The problem (20s).** *"Every USDA office in every county has a manager who, at 4am, looks at a forecast, a road map, a school announcement, and decides whether 26 people drive in. Then they have to tell the right ones. The inputs are scattered, two managers make different calls on the same storm, and afterward nobody can reconstruct why. We built Closure Call: one place for the inputs, a graded recommendation with its reasoning, the notification, and a record that survives the morning."*

**0:20 - Live data (20s).** Point at the map. *"This is live. Every polygon is a National Weather Service alert active right now, straight from api.weather.gov - no mock feed."* Name 1-2 real ones on screen.

**0:40 - Evaluate the KC facility (35s).** Click the KC Service Center, **Evaluate facility now**. While it streams: *"A Strands agent is calling six tools: NWS alerts, station observations and hourly forecast, the Missouri River gauge from NOAA's water service, air quality, the roster, and our threshold engine. The model is running on Akamai Cloud's hosted inference."* Result lands: *"Open, normal operations, 60% confidence, and it tells you why confidence isn't higher: no road feed, pre-opening decision."*

**1:15 - Exercise against a real storm (40s).** Click the chosen warning in the feed. *"Managers need to rehearse. We drop the same facility profile and roster into a live warning."* Map flies there, posture escalates. Read the posture. Scroll to **Thresholds crossed**: *"Every cutoff is anchored - this is the NWS Winter Storm Warning product mapped to OPM's 'closed to the public, unscheduled telework' status. It shows the margin, what would change the call, and a paragraph the manager can paste into an email."* Point at the rationale.

**1:55 - Notify the right people (30s).** **Build notification**. *"26 on the roster. 23 get told, 3 don't - and it says why for each one: on detail in St. Louis, on leave, already teleworking. Essential staff get voice plus SMS and a different instruction: report as scheduled. One SMS, one email, drafted."*

**2:25 - The human decides, and it's recorded (25s).** Change the dropdown one notch, type a reason (e.g. *"parking lot floods at 2 in of rain"*), **Approve & send**. Click **Open record**. *"What was known, with timestamps and sources. What was recommended. What the human decided and why. Who was told. Append-only, hash-chained - this is the deliverable an agency actually needs when it goes wrong."*

**2:50 - Close (10s).** *"Closure Call: NWS data, a Strands agent on Akamai Cloud, built for USDA's Closure Call challenge. Every multi-site operator makes this call - schools, hospitals, utilities - and today they make it alone at 4am."*

## If something breaks

- **LLM slow or down:** the app falls back to the deterministic rationale automatically and labels it. Say: *"The engine is rule-based and reproducible; the agent writes the prose."* Keep going.
- **NWS API hiccup:** responses are cached 60s; re-run. If national feed fails, the WMS overlay still paints from NOAA's map service.
- **No dramatic warning anywhere:** use a Winter Storm Warning or Flood Warning zone; the escalation to Delay/Telework still shows the whole flow.
- **Judge asks "is the roster real?"** - *"Synthetic by design; the spec says so. Real deployment reads HR/badging. The include/exclude logic is the product."*
- **Judge asks "why not just automate the decision?"** - *"The spec and OPM both say a human decides. We make the human faster, consistent, and auditable."*

## Sponsor callouts (say the names)

- "Strands Agents SDK" - the agent, its tools, structured output.
- "Akamai Cloud" - hosted inference (hackathon-chat) and the Linode the app runs on.
- "USDA Closure Call challenge" - all five deliverables.
