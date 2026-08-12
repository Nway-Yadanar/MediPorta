"""
scenario_failover.py

The headline demo: adaptive road -> water failover.

NORMAL:   truck serves clinics A, B, C by road (multi-clinic on-the-way run).
BLOCKAGE: a bridge edge is cut. Clinic C becomes road-inaccessible. The system
          automatically re-routes to it via Truck -> Dock -> Boat -> Clinic C,
          AND checks whether the cargo survives the longer boat leg
          (cold-chain payload feasibility).

This ties together all four features:
  1. multi-clinic on-the-way routing
  2. accessibility classification (C flips to inaccessible under blockage)
  3. water-route fallback
  4. cold-chain payload feasibility on the boat leg
"""

import networkx as nx
import pandas as pd

from app.graph_engine import route
from app.accessibility import classify_accessibility, ROAD_INACCESSIBLE
from app.multi_clinic import plan_multi_clinic_route, is_payload_feasible


def _road_only_view(G):
    H = G.copy()
    water = [
        (u, v) for u, v, d in G.edges(data=True)
        if d.get("mode") in ("water", "transfer")
    ]
    H.remove_edges_from(water)
    return H


def find_bridge_edge_on_path(G, hub, target):
    """
    Find a 'bridge' whose removal cuts the ROAD approach to `target`, forcing a
    water fallback. We walk the road-only shortest path from the target end
    (last ~12 hops) and return the first edge whose removal disconnects target
    from hub on the road network. This guarantees the blockage actually isolates
    the clinic by road rather than just nudging the route onto a parallel road.
    """
    H = _road_only_view(G)
    if target not in H or hub not in H or not nx.has_path(H, hub, target):
        return None
    path = nx.shortest_path(H, hub, target)
    for a, b in list(zip(path, path[1:]))[-12:]:
        H.remove_edge(a, b)
        cut = not nx.has_path(H, hub, target)
        H.add_edge(a, b, **G.get_edge_data(a, b))
        if cut:
            return frozenset((a, b))
    return None


def run_failover_scenario(
    G, hub, clinic_a, clinic_b, clinic_c, clinics_scored,
    water_clinic_ids, payloads_df, payload_item_id,
    risk_weight=1.0, equity_weight=1.0,
):
    """
    Returns a dict describing NORMAL vs BLOCKAGE outcomes for the demo.
    clinic_c should be a near-water clinic so the boat fallback is available.
    """
    payload = payloads_df.set_index("item_id").loc[payload_item_id].to_dict()
    payload["item_id"] = payload_item_id

    # --- NORMAL: multi-clinic on-the-way run to A, B, C ---
    normal = plan_multi_clinic_route(
        G, hub, clinic_c, [clinic_a, clinic_b], clinics_scored,
        risk_weight, equity_weight,
    )
    normal_feasible, normal_reason = is_payload_feasible(
        normal["total_cost_hr"], payload, has_cold_chain_transport=True
    )

    # --- Identify the bridge to cut on the road path to C ---
    bridge = find_bridge_edge_on_path(G, hub, clinic_c)
    blocked = {bridge} if bridge else set()

    # --- Reclassify accessibility under the blockage ---
    reclass = classify_accessibility(
        G, clinics_scored, hub, water_clinic_ids, blocked_edges=blocked
    )
    c_status = reclass.set_index("clinic_id").loc[clinic_c, "access_status"]

    # --- BLOCKAGE: remove bridge, reroute to C (boat fallback if needed) ---
    H = G.copy()
    if bridge:
        u, v = tuple(bridge)
        if H.has_edge(u, v):
            H.remove_edge(u, v)

    try:
        boat_path, boat_cost, boat_dist = route(
            H, hub, clinic_c, clinics_scored, risk_weight, equity_weight
        )
        used_water = any(
            H.get_edge_data(a, b).get("mode") == "water"
            for a, b in zip(boat_path, boat_path[1:])
        )
        reachable = True
    except nx.NetworkXNoPath:
        boat_path, boat_cost, boat_dist, used_water, reachable = [], None, None, False, False

    # cold-chain harder to maintain on an open boat leg -> flag transport as degraded
    blockage_feasible, blockage_reason = (
        is_payload_feasible(boat_cost, payload, has_cold_chain_transport=not used_water)
        if reachable else (False, "clinic unreachable after bridge blockage")
    )

    return {
        "payload": payload_item_id,
        "payload_cold_chain": str(payload.get("cold_chain")).upper() == "TRUE",
        "normal": {
            "stops": normal["stops"],
            "total_cost_hr": normal["total_cost_hr"],
            "distance_km": normal["total_distance_km"],
            "n_clinics": normal["n_clinics_served"],
            "payload_feasible": normal_feasible,
            "payload_reason": normal_reason,
        },
        "blockage": {
            "bridge_cut": tuple(bridge) if bridge else None,
            "clinic_c_status": c_status,
            "reroute_uses_water": used_water,
            "reachable": reachable,
            "total_cost_hr": boat_cost,
            "distance_km": boat_dist,
            "payload_feasible": blockage_feasible,
            "payload_reason": blockage_reason,
        },
    }
