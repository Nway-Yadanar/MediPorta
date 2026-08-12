# Disruption Risk — from placeholder to real signal

## The problem this solves

Previously `base_disruption_risk` was a **placeholder by road class**
(`primary`=0.12, `secondary`=0.22, `tertiary`=0.35, `track`=0.55). Real road
geometry, but the risk number reflected only *what kind* of road an edge was,
not *where it actually is* — a tertiary road through an active conflict zone
scored the same as one in a calm area.

## The fix: a hazard overlay on top of the road-class floor

```
edge_risk = base_by_road_class                 (kept as a legitimate floor)
          + Σ active nearby hazards of
                weight(type) × severity × proximity_falloff × recency_decay
          clamped to [0, 1]
```

- **`base_disruption_risk`** stays as the road-class floor — flagged
  `road_class_proxy`. A track really is riskier than a highway; that's honest.
- **`hazard_events.csv`** holds located, dated hazards (conflict / flood /
  earthquake damage / access restriction). Each contributes risk to edges within
  its radius, falling off with distance and decaying with time since the event.
- **`enriched_disruption_risk`** is the final per-edge value, with a
  `hazard_contributors` audit column recording *which* events raised it and by
  how much — so risk is explainable, not a magic number.

## Why it's a separate layer (the "live feed" seam)

The 212K-node graph is stable and built once. Hazards change weekly. So hazards
live in their own CSV and are applied at build time. To refresh risk:

```
# 1. replace hazard_events.csv with a fresh export (see sources below)
# 2. recompute enriched edges as of today
python data/apply_risk_enrichment.py

# 3. rebuild scenarios / frontend
python scripts/precompute_scenarios.py
python scripts/build_frontend.py
```

No graph rebuild, no code change. That's the seam a real live feed plugs into.

## Connecting real sources

`hazard_events.csv` is designed to match what these sources already publish, so
swapping in real data is a column-mapping exercise, not a redesign:

| hazard_type | real source | notes |
|---|---|---|
| `conflict` | **ACLED** (acleddata.com) | event lat/lon, date, event_type → severity. Free API with registration; export filtered to Myanmar + these regions. |
| `flood` | **UNOSAT** / Sentinel-1 flood extent, or Copernicus EMS | polygon extent → approximate as center + radius, or do a true polygon-in-edge test. |
| `earthquake_damage` | field reports / USGS ShakeMap | the March 2025 Sagaing quake is the concrete case. |
| `access_restriction` | Health Cluster / OCHA field reports | manually coded, dated closures. |

### The one honest caveat
The current `hazard_events.csv` is a **schema-accurate sample**, not a live
ACLED pull (flagged `*_schema_sample` in `_data_provenance`). It has the right
shape, real coordinates in the right places, and drives routing correctly — but
before a real deployment, replace it with an actual ACLED/UNOSAT export. The
code is built to consume that directly; only the CSV contents change.

## What it changes in the demo

Route near an active conflict zone (e.g. the Homalin area) and the enriched risk
lifts those edges, so the risk-weighted router either detours around them (where
a parallel road exists) or correctly reports the higher risk (where none does).
Toggle the hazard date in `apply_risk_enrichment.py` and watch which hazards are
active — recency decay means a two-month-old event weighs less than last week's.
