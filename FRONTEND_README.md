# MediRoute Dispatch Console — Frontend

`demo_data/index.html` is a **single self-contained file** — open it in any
browser. No build step, no server. (Map tiles need internet; the dispatch
panels work offline.)

## What judges see
- **Thesis** (top left): silence-as-signal framing.
- **Scenario toggle**: Normal ↔ Bridge blocked.
- **Payload toggle**: ORS (ambient) ↔ Polio vaccine (cold-chain).
  Watch the cold-chain card flip from ✓ to ✕ on the SAME blocked-bridge reroute.
- **Route chain** (Grab-style): named waypoints with truck/transfer/boat pills.
- **Priority queue** (right) with **Stock only ↔ + Comms blackout** toggle:
  flip it and blackout clinics jump up the list with ▲rank deltas — the
  "making invisible clinics visible" moment.
- **Map**: clinics colored by priority, blackout rings, waterways, docks,
  and the live segmented route.

## Regenerating after data changes
```
python scripts/export_frontend_json.py   # backend -> demo_data/*.json
python scripts/build_frontend.py          # json -> demo_data/index.html
```

## Demo script (90 seconds)
1. "Every clinic here is real — 306 facilities in Rakhine and Sagaing."
2. Normal + ORS: truck milk-run, delivers fine.
3. Flip to Bridge blocked: route reroutes truck→dock→boat. ORS still ✓.
4. Flip payload to Polio vaccine: SAME boat route, now ✕ — cold chain breaks.
   "The system reasons about the cargo, not just the path."
5. Right panel, flip to + Comms blackout: blackout clinics leap up the queue.
   "These clinics can't call for help. Reactive systems never see them. We do."
