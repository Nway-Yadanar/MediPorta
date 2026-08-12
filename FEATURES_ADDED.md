# MediRoute — New Features (multi-clinic, accessibility, water, cold-chain)

Four features added on top of the existing risk-weighted routing engine, plus
the demand dataset that drives triage. All new code uses the same stack
(networkx + scipy + pandas, stdlib only) and the same `CL-XXXX` clinic keys.

## What was added

### Data
- `data/medical_payloads.csv` — 13-item catalog (malaria, dengue, cholera/AWD,
  EPI vaccines, snakebite antivenom, maternal) with cold-chain, storage temp,
  VVM class, and `max_transit_hours` viability window per item.
  Disease→region priorities are grounded in WHO/Health Cluster burden data;
  logistics figures are `who_range_proxy`.
- `data/clinic_demand.csv` — long format, one row per (clinic, item). 1,858 rows
  across all 306 clinics. Region-weighted consumption; computed
  `days_of_stock_remaining`, `days_to_expiry`, `stockout_flag`,
  `expiry_risk_flag`, and a blended `priority_score`. All numeric fields
  `proxy_synthetic` (no open per-clinic inventory feed for Myanmar).
- `data/generate_demand_data.py` — regenerates the above from clinics +
  payloads. Edit the weights/thresholds at the top to tune.
- `data/waterways.geojson`, `data/boat_docks.geojson` — hand-drawn Mayu River /
  coastal corridor and docks near real Maungdaw/Buthidaung/Rathedaung clinics.
  Flagged SYNTHETIC.

### App modules
- `app/accessibility.py` — Feature 2. Classifies each clinic
  `road_accessible` / `partially_accessible` / `road_inaccessible` from
  road_access_flag + graph reachability + water proximity. Scenario-aware
  (accepts `blocked_edges`).
- `app/water_routes.py` — Feature 3. Adds dock nodes, boat edges, and
  dock↔road / dock↔clinic transfer edges (with load/unload penalty) into the
  SAME graph, so the existing Dijkstra handles multi-modal routes.
- `app/multi_clinic.py` — Feature 1 (corridor insertion, polynomial not TSP) +
  Feature 4 (`is_payload_feasible` cold-chain / transit-window check).
- `app/scenario_failover.py` — the headline demo tying all four together.

### Demo
- `scripts/demo_features.py` — runs the whole thing on the real 212K-node graph.

## The headline result

Same bridge blockage, two payloads:
- `MED_ORS` (ambient): reroutes truck→dock→boat→clinic. **Feasible.**
- `VAC_OPV` (cold-chain vaccine): same boat reroute. **Not feasible** — cold
  chain can't be held on the open boat leg.

The system reasons about both the path and the cargo.

## Run it
```
cd mediroute
python data/generate_demand_data.py     # (re)build demand data
python scripts/demo_features.py          # run the four-feature demo
```

## Provenance (unchanged discipline)
Real: clinic locations/IDs, road topology, disease→region priorities, WHO
cold-chain concepts. Proxy/synthetic: per-clinic stock & consumption, waterway
geometry, dock locations, boat speed, transfer penalty, per-segment cold-chain
capability. Every proxy field is flagged in-file. Swap to real feeds later
without changing the routing logic.
