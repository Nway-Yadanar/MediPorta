"""
export_frontend_json.py

The glue layer between the heavy graph backend and the frontend.

Runs the scenarios ONCE and writes compact, frontend-ready JSON so the UI never
has to touch the 212K-node graph live during a demo. Produces:

  demo_data/
    triage.json         - ranked clinics with telecom-boosted priority + markers
    route_normal.json    - Grab-style named-waypoint chain for the normal run
    failover.json        - normal vs blockage, per-leg, with cold-chain verdicts
    map_layers.json      - clinic markers (priority color + blackout ring),
                           docks, waterways, for the map
    meta.json            - provenance + summary counts

Grab-style chain: we collapse the raw road-vertex path down to NAMED waypoints
only -- hub, township centers passed near, docks, and clinics -- so the UI shows
"Buthidaung -> Ah Lel Than Kyaw Landing (dock) -> [boat] -> clinic" instead of
thousands of RN-xxxx vertices.

Run from project root:
    python scripts/export_frontend_json.py
"""

import json
import os
import sys

import networkx as nx
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.vulnerability import compute_vulnerability_scores
from app.graph_engine import build_graph, route
from app.accessibility import classify_accessibility
from app.water_routes import add_water_layer, _haversine_km
from app.multi_clinic import plan_multi_clinic_route, is_payload_feasible
from app.scenario_failover import run_failover_scenario

OUT = os.path.join(ROOT, "demo_data")
HUB = "HUB-Buthidaung"
CLINIC_C = "CL-0270"          # near-water clinic with a real isolating bridge
PAYLOADS_TO_TEST = ["MED_ORS", "VAC_OPV"]  # ambient vs cold-chain


def priority_color(score):
    if score >= 0.75:
        return "#c0392b"   # red - critical
    if score >= 0.55:
        return "#e67e22"   # orange - high
    if score >= 0.35:
        return "#f1c40f"   # yellow - moderate
    return "#27ae60"       # green - ok


def named_waypoints(G, path, township_lookup):
    """
    Collapse a raw path to a readable chain of NAMED waypoints:
    hubs, docks, clinics kept as-is; long road stretches summarized as the
    township they pass through. Returns list of {name, type, mode, lat, lon}.
    """
    chain = []
    prev_mode = "road"
    for i, node in enumerate(path):
        ntype = G.nodes[node].get("node_type", "road_vertex")
        lat, lon = G.nodes[node].get("lat"), G.nodes[node].get("lon")
        mode = "road"
        if i > 0:
            ed = G.get_edge_data(path[i - 1], node) or {}
            mode = ed.get("mode", "road")
        if ntype in ("clinic", "dock", "township_hub") or "HUB" in str(node):
            label = node
            if ntype == "clinic":
                label = township_lookup.get("clinic_names", {}).get(node, node)
            chain.append({
                "id": node, "name": label, "type": ntype,
                "mode_in": mode, "lat": lat, "lon": lon,
            })
    return chain


def leg_summary(G, path):
    """Total time/dist and modal breakdown of a path."""
    road_t = boat_t = 0.0
    dist = 0.0
    for a, b in zip(path, path[1:]):
        d = G.get_edge_data(a, b)
        dist += d.get("distance_km", 0)
        if d.get("mode") == "water":
            boat_t += d.get("travel_time_hr", 0)
        else:
            road_t += d.get("travel_time_hr", 0)
    return {
        "road_hours": round(road_t, 2),
        "boat_hours": round(boat_t, 2),
        "total_hours": round(road_t + boat_t, 2),
        "distance_km": round(dist, 1),
    }


def main():
    os.makedirs(OUT, exist_ok=True)
    data = os.path.join(ROOT, "data")

    clinics = pd.read_csv(os.path.join(data, "clinics.csv"))
    nodes = pd.read_csv(os.path.join(data, "roads_nodes.csv"))
    edges = pd.read_csv(os.path.join(data, "roads_edges.csv"))
    payloads = pd.read_csv(os.path.join(data, "medical_payloads.csv"))
    demand = pd.read_csv(os.path.join(data, "clinic_demand.csv"))
    telecom = pd.read_csv(os.path.join(data, "telecom_status.csv"))

    scored = compute_vulnerability_scores(clinics)
    G = build_graph(nodes, edges, scored)
    docks, water_clinics = add_water_layer(
        G,
        os.path.join(data, "waterways.geojson"),
        os.path.join(data, "boat_docks.geojson"),
        clinics,
    )

    clinic_names = dict(zip(clinics["clinic_id"], clinics["clinic_name"]))
    township_lookup = {"clinic_names": clinic_names}

    #  telecom
    tele_by_pcode = (
        telecom.drop_duplicates("township_pcode")
        .set_index("township_pcode")[["telecom_status", "priority_multiplier"]]
        .to_dict("index")
    )
    clinic_tele = clinics.set_index("clinic_id")["township_pcode"].to_dict()

    # top demand row per clinic 
    top_demand = (
        demand.sort_values("priority_score", ascending=False)
        .groupby("clinic_id").first().reset_index()
    )

    triage = []
    for r in top_demand.itertuples():
        pcode = clinic_tele.get(r.clinic_id)
        tinfo = tele_by_pcode.get(pcode, {"telecom_status": "normal", "priority_multiplier": 1.0})
        boosted = round(min(1.0, r.priority_score * tinfo["priority_multiplier"]), 3)
        triage.append({
            "clinic_id": r.clinic_id,
            "clinic_name": clinic_names.get(r.clinic_id, r.clinic_id),
            "top_item": r.item_id,
            "days_of_stock": r.days_of_stock_remaining,
            "base_priority": r.priority_score,
            "telecom_status": tinfo["telecom_status"],
            "telecom_multiplier": tinfo["priority_multiplier"],
            "boosted_priority": boosted,
            "blackout": tinfo["telecom_status"] == "blackout",
        })
    triage.sort(key=lambda x: x["boosted_priority"], reverse=True)

    # rank movement  by telecom boost 
    base_rank = {c["clinic_id"]: i for i, c in enumerate(
        sorted(triage, key=lambda x: x["base_priority"], reverse=True))}
    for i, c in enumerate(triage):
        c["rank_boosted"] = i + 1
        c["rank_base"] = base_rank[c["clinic_id"]] + 1
        c["rank_delta"] = c["rank_base"] - c["rank_boosted"]  # +ve = moved up

    with open(os.path.join(OUT, "triage.json"), "w") as f:
        json.dump(triage[:40], f, indent=2)

    #  normal multi-clinic route (Grab-style) 
    others = [c for c in sorted(water_clinics) if c != CLINIC_C][:2]
    plan = plan_multi_clinic_route(G, HUB, CLINIC_C, others, scored)
    normal_chain = []
    for leg in plan["legs"]:
        seg = named_waypoints(G, leg["path"], township_lookup)
        summ = leg_summary(G, leg["path"])
        normal_chain.append({
            "from": leg["from"], "to": leg["to"],
            "waypoints": seg, "summary": summ,
        })
    with open(os.path.join(OUT, "route_normal.json"), "w") as f:
        json.dump({
            "stops": plan["stops"],
            "stop_names": [clinic_names.get(s, s) for s in plan["stops"]],
            "legs": normal_chain,
            "total_hours": plan["total_cost_hr"],
            "total_km": plan["total_distance_km"],
            "n_clinics": plan["n_clinics_served"],
        }, f, indent=2)

    # failover
    fail_out = {}
    for item in PAYLOADS_TO_TEST:
        res = run_failover_scenario(
            G, HUB, others[0], others[1], CLINIC_C, scored,
            water_clinics, payloads, item,
        )
        prow = payloads.set_index("item_id").loc[item]
        # build the readable blockage reroute chain
        H = G.copy()
        bridge = res["blockage"]["bridge_cut"]
        if bridge:
            u, v = bridge
            if H.has_edge(u, v):
                H.remove_edge(u, v)
        try:
            bpath, bcost, bdist = route(H, HUB, CLINIC_C, scored)
            bchain = named_waypoints(H, bpath, township_lookup)
            bsumm = leg_summary(H, bpath)
        except nx.NetworkXNoPath:
            bchain, bsumm = [], {}
        fail_out[item] = {
            "item_name": prow["item_name"],
            "cold_chain": str(prow["cold_chain"]).upper() == "TRUE",
            "max_transit_hours": int(prow["max_transit_hours"]),
            "storage_temp": prow["storage_temp_c"],
            "manifest": {
                "carrying": prow["item_name"],
                "must_arrive_within_h": int(prow["max_transit_hours"]),
                "normal_route_h": res["normal"]["total_cost_hr"],
                "blockage_route_h": bsumm.get("total_hours"),
                "normal_margin_h": round(int(prow["max_transit_hours"]) - res["normal"]["total_cost_hr"], 1),
                "blockage_margin_h": (round(int(prow["max_transit_hours"]) - bsumm["total_hours"], 1)
                                       if bsumm.get("total_hours") is not None else None),
                "within_time_window": (bsumm.get("total_hours") is not None
                                        and bsumm["total_hours"] <= int(prow["max_transit_hours"])),
                "cold_chain_breaks_on_boat": (str(prow["cold_chain"]).upper() == "TRUE"
                                               and res["blockage"]["reroute_uses_water"]),
                "failure_mode": (
                    "cold_chain_break" if (str(prow["cold_chain"]).upper() == "TRUE"
                                            and res["blockage"]["reroute_uses_water"]
                                            and bsumm.get("total_hours") is not None
                                            and bsumm["total_hours"] <= int(prow["max_transit_hours"]))
                    else "time_exceeded" if (bsumm.get("total_hours") is not None
                                              and bsumm["total_hours"] > int(prow["max_transit_hours"]))
                    else "none"
                ),
            },
            "normal": res["normal"],
            "blockage": {
                **res["blockage"],
                "reroute_waypoints": bchain,
                "reroute_summary": bsumm,
            },
        }
    with open(os.path.join(OUT, "failover.json"), "w") as f:
        json.dump(fail_out, f, indent=2)

    # map 
    tri_by_id = {t["clinic_id"]: t for t in triage}
    clinic_markers = []
    for c in clinics.itertuples():
        t = tri_by_id.get(c.clinic_id, {})
        score = t.get("boosted_priority", 0.2)
        clinic_markers.append({
            "id": c.clinic_id, "name": c.clinic_name,
            "lat": c.latitude, "lon": c.longitude,
            "priority": score, "color": priority_color(score),
            "telecom_status": t.get("telecom_status", "normal"),
            "blackout": t.get("blackout", False),
            "near_water": c.clinic_id in water_clinics,
        })
    dock_pts = [
        {"id": n, "lat": d["lat"], "lon": d["lon"], "name": n}
        for n, d in G.nodes(data=True) if d.get("node_type") == "dock"
    ]
    waterway_lines = []
    for u, v, d in G.edges(data=True):
        if d.get("mode") == "water":
            waterway_lines.append({
                "from": [G.nodes[u]["lat"], G.nodes[u]["lon"]],
                "to": [G.nodes[v]["lat"], G.nodes[v]["lon"]],
            })
    with open(os.path.join(OUT, "map_layers.json"), "w") as f:
        json.dump({
            "clinics": clinic_markers,
            "docks": dock_pts,
            "waterways": waterway_lines,
        }, f, indent=2)

   
    tele_counts = telecom["telecom_status"].value_counts().to_dict()
    n_blackout_clinics = sum(1 for t in triage if t.get("blackout"))
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump({
            "hub": HUB,
            "n_clinics": len(clinics),
            "n_near_water": len(water_clinics),
            "telecom_counts": tele_counts,
            "n_blackout_clinics": n_blackout_clinics,
            "n_townships_blackout": int((telecom["telecom_status"] == "blackout").sum()),
            "provenance": {
                "real": "clinic locations/IDs, road topology, disease->region "
                        "priorities, WHO cold-chain windows, blackout township "
                        "reporting, clinic stock/demand",
                "proxy_synthetic": "waterway geometry, dock locations, boat speed, "
                        "transfer penalty, per-segment cold-chain capability, "
                        "conflict-proxy telecom",
            },
        }, f, indent=2)

    print(f"Exported frontend JSON to {OUT}/")
    for fn in ["triage.json", "route_normal.json", "failover.json", "map_layers.json", "meta.json"]:
        p = os.path.join(OUT, fn)
        print(f"  {fn:20s} {os.path.getsize(p):>7d} bytes")

    movers = [t for t in triage if t["blackout"] and t["rank_delta"] > 0][:5]
    print("\nTelecom standout beat -- blackout clinics that moved UP in priority:")
    for m in movers:
        print(f"  {m['clinic_id']} {m['clinic_name'][:28]:28s} "
              f"#{m['rank_base']} -> #{m['rank_boosted']} (+{m['rank_delta']})  "
              f"[{m['telecom_status']}]")


if __name__ == "__main__":
    main()
