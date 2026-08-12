"""
apply_risk_enrichment.py

Applies the hazard overlay to the road edges and writes
roads_edges_enriched.csv (adds enriched_disruption_risk + audit columns).

This is the seam for the "live feed": refresh hazard_events.csv from a real
ACLED / UNOSAT / field-report export, rerun this, and the whole routing engine
uses updated risk -- no graph rebuild, no code change.

Usage:
    python data/apply_risk_enrichment.py            # as of today
    python data/apply_risk_enrichment.py 2026-01-15 # as of a specific date
"""

import datetime as dt
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from app.risk_enrichment import enrich_edge_risk

DATA = os.path.join(ROOT, "data")


def main():
    as_of = dt.date.today()
    if len(sys.argv) > 1:
        as_of = dt.date.fromisoformat(sys.argv[1])

    edges = pd.read_csv(os.path.join(DATA, "roads_edges.csv"))
    nodes = pd.read_csv(os.path.join(DATA, "roads_nodes.csv"))
    hazards = pd.read_csv(os.path.join(DATA, "hazard_events.csv"))
    coords = {r.node_id: (r.latitude, r.longitude) for r in nodes.itertuples()}

    out = enrich_edge_risk(edges, hazards, coords, as_of=as_of)
    dest = os.path.join(DATA, "roads_edges_enriched.csv")
    out.to_csv(dest, index=False)
    print(f"\nWrote {dest}")
    print("To use it: point the graph builder at roads_edges_enriched.csv and read "
          "enriched_disruption_risk instead of base_disruption_risk.")


if __name__ == "__main__":
    main()
