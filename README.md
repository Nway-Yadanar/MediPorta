# MediRoute — Risk-Weighted Medical Supply Routing (Myanmar)

**Reactive supply systems wait for clinics to call. The clinics in worst shape —
behind cut roads, rivers, or comms blackouts — *can't* call. MediRoute treats
their silence as the loudest signal and pushes life-saving supplies to them.**

It routes medical supplies to **306 real clinics** in Rakhine, Sagaing, and rural
Mandalay over a **212,000-node road + river network**, minimizing
`travel_time × (1 + λ · disruption_risk)` instead of shortest distance — then
checks cold-chain feasibility, recommends fixes, and prioritizes clinics that
have gone dark.

---

## ⚡ Quick start for judges (30 seconds, no install)

**Open `demo_data/index.html` in a web browser.** Double-click it, or drag it
into a tab. Everything is embedded — it runs offline.

> The map background loads from the internet; if there's no connection the side
> panels still work fully.

Then try this 60-second flow:

1. **Region = Rakhine**, **Scenario = Normal**, **Payload = Oral rehydration salts**
   → delivery works, green ✓.
2. Flip **Scenario → Disruption** → a bridge is cut, the route reroutes to
   **boat** (blue dotted line). ORS still fine.
3. Change **Payload → Oral polio vaccine** → same boat route, now **red ✕: spoiled**
   — cold chain breaks on the open boat. A green **cold-box fix** is recommended.
4. Right panel, click **+ Comms blackout** → blackout clinics jump *up* the
   priority queue (▲). They can't call for help, so the system pushes to them.
5. Left panel, scroll to **Off-grid connectivity** → those same silent clinics
   flagged for **satellite (Starlink) deployment**.
6. Switch **Region → Mandalay** → no boats (landlocked); the engine doesn't force
   water where it doesn't belong.

That's the whole thesis: reach the clinics everyone else is blind to.

---

## 🔧 Full version with live routing (optional)

To route to **any** clinic live (not just the pre-built scenarios), run the API:

```bash
cd mediroute
python -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate
pip install fastapi "uvicorn[standard]" pandas networkx scipy geopandas shapely
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

Wait for `Application startup complete` (~15–30 s while the graph loads), then
open **http://localhost:8000** (use `localhost`, not `0.0.0.0`).

Now the **DELIVER TO** dropdown routes to any clinic on demand, and clicking a
clinic on the map → **"→ Route here"** computes it live.

---

## 🧠 How it works

- **Algorithm:** Dijkstra over a **multi-modal graph** (road + boat + dock edges
  in one network, so truck→boat failover is emergent — no special-casing), with
  a **custom risk-weighted cost function**. Multi-clinic runs use greedy
  corridor-insertion (polynomial, not TSP). **Explainable — no black-box ML.**
- **Cold-chain aware:** each vaccine has a real WHO transit-time + temperature
  window; a route is only feasible if the cargo survives it.
- **Telecom-aware triage:** clinics in documented comms-blackout townships get a
  priority boost — they can't request resupply, so the system pushes proactively.
- **Off-grid recommendation:** flags the highest-priority blackout clinics for
  satellite deployment (recommends the fix; doesn't provide the link).
- **Transferable:** one country-agnostic engine + swappable regional data packs
  (Rakhine boat / Sagaing Chindwin river / Mandalay road).

---

## 📁 Project layout
```
mediroute/
  app/            graph_engine · accessibility · water_routes · multi_clinic
                  scenario_failover · regions · api · vulnerability
  data/           real clinics (MIMU) · roads (OSM) · payloads · telecom
                  waterways/docks · generator scripts
  scripts/        precompute_scenarios.py · build_frontend.py
  demo_data/
    index.html    ← THE DEMO (open this)
    precomputed/  12 region×hub scenarios
  requirements.txt
```

## 🔄 Rebuild after changing data (developers only)
```bash
python scripts/precompute_scenarios.py   # data + graph → demo_data/precomputed/
python scripts/build_frontend.py          # → demo_data/index.html
```

## 📊 Data provenance (honesty is a design feature)
**Real:** MIMU clinic locations · OSM road network · WHO cold-chain windows ·
telecom-blackout reporting (Access Now / #KeepItOn / Myanmar Shutdown Tracker) ·
UNOSAT flood extents · ACLED conflict.
**Proxy (flagged `_data_provenance`):** per-clinic stock levels · hand-drawn
waterway/dock geometry · boat speed · transfer penalty.
Every synthetic field is labelled — the system never passes proxy data as real.

---
*AI usage declaration: Generative AI was used to scaffold and draft code in this repository.*
