"""
demo_features.py

End-to-end demonstration of the four new MediRoute features on the REAL graph:
  1. Multi-clinic on-the-way routing
  2. Road accessibility classification
  3. Water-route support
  4. Cold-chain payload feasibility  (+ the headline failover scenario)

Run from the mediroute/ project root:
    python scripts/demo_features.py
"""

import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.vulnerability import compute_vulnerability_scores
from app.graph_engine import build_graph
from app.accessibility import classify_accessibility, accessibility_summary
from app.water_routes import add_water_layer
from app.multi_clinic import plan_multi_clinic_route
from app.scenario_failover import run_failover_scenario


def main():
    data = os.path.join(ROOT, "data")
    clinics = pd.read_csv(os.path.join(data, "clinics.csv"))
    nodes = pd.read_csv(os.path.join(data, "roads_nodes.csv"))
    edges = pd.read_csv(os.path.join(data, "roads_edges.csv"))
    payloads = pd.read_csv(os.path.join(data, "medical_payloads.csv"))

    scored = compute_vulnerability_scores(clinics)
    G = build_graph(nodes, edges, scored)
    print(f"[graph] {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # add water layer 
    docks, water_clinics = add_water_layer(
        G,
        os.path.join(data, "waterways.geojson"),
        os.path.join(data, "boat_docks.geojson"),
        clinics,
    )
    print(f"[water] added {len(docks)} docks; {len(water_clinics)} clinics near water: "
          f"{sorted(water_clinics)}")

    
    hub = "HUB-Buthidaung"   # a real township hub in coastal Rakhine
    access = classify_accessibility(G, scored, hub, water_clinics)
    print(f"[access] normal-condition status counts: {accessibility_summary(access)}")

   
    clinic_c = "CL-0270"
    others = [c for c in sorted(water_clinics) if c != clinic_c]
    a, b = others[0], others[1]
    plan = plan_multi_clinic_route(G, hub, clinic_c, [a, b], scored)
    print(f"[multi] on-the-way run served {plan['n_clinics_served']} clinics: {plan['stops']}")
    print(f"        total {plan['total_cost_hr']}h / {plan['total_distance_km']}km")

    
    for item in ["MED_ORS", "VAC_OPV"]:
        result = run_failover_scenario(
            G, hub, a, b, clinic_c, scored, water_clinics, payloads, item
        )
        n, bl = result["normal"], result["blockage"]
        print(f"\n[failover] payload={item} (cold_chain={result['payload_cold_chain']})")
        print(f"  NORMAL  : {n['n_clinics']} clinics by road, {n['total_cost_hr']}h  "
              f"payload_feasible={n['payload_feasible']}")
        print(f"  BLOCKAGE: bridge cut {bl['bridge_cut']}")
        print(f"            clinic C ({clinic_c}) status -> {bl['clinic_c_status']}")
        print(f"            reroute reachable={bl['reachable']}, uses_water={bl['reroute_uses_water']}, "
              f"cost={bl['total_cost_hr']}h")
        print(f"            payload_feasible={bl['payload_feasible']} ({bl['payload_reason']})")


if __name__ == "__main__":
    main()
