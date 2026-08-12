# MediRoute — GeoAI Medical Support

**Reactive supply systems wait for clinics to call for resupply. The clinics in
worst condition — behind cut roads, rivers, or communication blackouts — can't
call. MediPorta treats their silence as the strongest signal of need and pushes
life-saving supplies to the clinics everyone else is blind to.**

It routes supplies to 306 real clinics across Rakhine, Sagaing, and rural
Mandalay over a 212,000-node road-and-river network, minimizing
`travel_time × (1 + λ · disruption_risk)` instead of shortest distance — then
checks whether the cargo survives the trip and prioritizes clinics that have
gone dark.

---

## How to run it

1. Clone this repository and open a terminal in the project folder.

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
   On Windows, use `venv\Scripts\activate` instead.

3. Install the requirements:
   ```bash
   pip install fastapi "uvicorn[standard]" pandas networkx scipy geopandas shapely
   ```

4. Start the server:
   ```bash
   uvicorn app.api:app --host 0.0.0.0 --port 8000
   ```

5. Wait until you see `Application startup complete`. This takes about 15–30
   seconds while the road network loads into memory.

6. Open **http://localhost:8000** in a web browser. Use `localhost`, not
   `0.0.0.0`.

The console loads with the map, the routing engine running live behind it.

---

## How to use it

1. Pick a **region** (top-left) — Rakhine, Sagaing, or Mandalay. Rakhine and
   Sagaing use rivers; Mandalay is road-only.

2. Pick a **supply hub** — the hospital the delivery starts from.

3. Pick a **destination** in the DELIVER TO dropdown, or click any clinic on the
   map and choose "Route here" — the route is computed live.

4. Choose a **payload** — the medicine or vaccine being delivered.

5. Read the **CARRYING card**: it shows the delivery time, the safe transit
   window, and whether the cargo arrives intact.

6. Flip **Scenario** to **Disruption** — a bridge is cut, and the route reroutes
   by boat (shown as a dotted blue line).

7. With a cold-chain vaccine selected during disruption, the card shows the cargo
   would spoil on the open boat and recommends loading a passive cold box to
   make the delivery viable.

8. On the right, toggle **+ Comms blackout** — clinics in blackout townships rise
   to the top of the priority queue, because they can't call for resupply.

9. On the left, scroll to **Off-grid connectivity** — those same silent clinics
   are flagged for satellite (Starlink) deployment.

---

## How it works

MediPorta runs Dijkstra's shortest-path algorithm over a multi-modal graph where
road, boat, and dock-transfer connections all live in one network — so a
truck-to-boat reroute happens naturally, with no special code. The cost of each
step isn't distance; it's travel time weighted by disruption risk, so the system
prefers safer routes over merely faster ones. Multi-clinic runs use greedy
corridor insertion rather than solving the travelling-salesman problem, which
keeps it fast. There is no black-box machine learning — every routing decision
traces back to a cost you can inspect.

On top of routing, the system checks each vaccine against a real WHO
transit-time and temperature window, boosts the priority of clinics in documented
communication blackouts, and recommends where satellite terminals should be
deployed to bring off-grid clinics back online.

---

## The API

Once the server is running, these endpoints are available:

| Endpoint | What it does |
|---|---|
| `GET /`                            | the console |
| `GET /health`                      | whether the graph has finished loading |
| `GET /regions`                     | region and hub list for the switchers |
| `GET /precomputed/{region}/{hub}`  | a pre-built scenario |
| `POST /route`                      | a live route from any origin to any clinic |

---

## Rebuilding after you change the data

If you edit the clinic, stock, telecom, or payload data, rebuild the scenarios:

```bash
python scripts/precompute_scenarios.py
python scripts/build_frontend.py
```

---

## Project layout

```
mediroute/
  app/            the routing engine, water routing, cold-chain checks, API
  data/           real clinics, roads, payloads, telecom, waterways, generators
  scripts/        precompute_scenarios.py, build_frontend.py
  demo_data/      the console the server serves, and precomputed scenarios
  requirements.txt
```

---

## Data honesty

Every data field is labelled as real or proxy. Real data includes clinic
locations (MIMU), the road network (OpenStreetMap), WHO cold-chain windows,
communication-blackout reporting (Access Now / #KeepItOn / Myanmar Shutdown
Tracker), UNOSAT flood extents, and ACLED conflict data. Proxy data — per-clinic
stock levels, hand-drawn waterway and dock geometry, boat speed, and transfer
penalties — is flagged in the files themselves. The system never presents proxy
data as real, because a platform built to make invisible clinics visible cannot
be built on invisible assumptions.

---

*AI usage: generative AI was used to help find data sources and synthetic data*
