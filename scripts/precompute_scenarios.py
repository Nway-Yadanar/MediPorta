"""
precompute_scenarios.py

Batch-computes every (region, hub) scenario ONCE so the API/ frontend can serve
them instantly. For each region's default + alternate hubs, computes:
  - triage (telecom-boosted) for that region's clinics
  - a multi-clinic on-the-way route from the hub
  - the region's characteristic failover scenario (boat / river / road)
  - map layers scoped to the region

Writes demo_data/precomputed/{region}__{hub}.json

Run from project root:
    python scripts/precompute_scenarios.py
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
from app.water_routes import add_water_layer
from app.multi_clinic import plan_multi_clinic_route, is_payload_feasible
from app.scenario_failover import find_bridge_edge_on_path, _road_only_view
from app.regions import REGIONS, default_hub

DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "demo_data", "precomputed")
PAYLOADS_TEST = None  


def priority_color(s):
    return "#c0392b" if s >= .75 else "#e67e22" if s >= .55 else "#f1c40f" if s >= .35 else "#27ae60"


def named_chain(G, path, names):
    out = []
    for i, n in enumerate(path):
        d = G.nodes[n]; nt = d.get("node_type", "road_vertex")
        mode = "road"
        if i > 0:
            mode = (G.get_edge_data(path[i-1], n) or {}).get("mode", "road")
        if nt in ("clinic", "dock", "township_hub") or "HUB" in str(n):
            out.append({"id": n, "name": names.get(n, n), "type": nt,
                        "mode_in": mode, "lat": d.get("lat"), "lon": d.get("lon")})
    return out


def leg_summary(G, path):
    road_t = boat_t = dist = 0.0
    for a, b in zip(path, path[1:]):
        d = G.get_edge_data(a, b)
        dist += d.get("distance_km", 0)
        if d.get("mode") == "water":
            boat_t += d.get("travel_time_hr", 0)
        else:
            road_t += d.get("travel_time_hr", 0)
    return {"road_hours": round(road_t, 2), "boat_hours": round(boat_t, 2),
            "total_hours": round(road_t + boat_t, 2), "distance_km": round(dist, 1)}


def polyline(G, path):
    return [[G.nodes[n]["lat"], G.nodes[n]["lon"]] for n in path
            if G.nodes[n].get("lat") is not None]


def pick_scenario_clinic(G, hub, region_clinics, water_clinics, want_water, road_reroute=False):
    """Find a region clinic with a real isolating road bridge; prefer near-water
    if the region has a water story. For road_reroute regions (Mandalay), instead
    pick a clinic where cutting the highest-risk edge on the path still leaves a
    road alternative -- so we demo a safe REROUTE, not a disconnection."""
    H = _road_only_view(G)
    pool = [c for c in region_clinics if c in H and nx.has_path(H, hub, c)]
    if want_water:
        pool = [c for c in pool if c in water_clinics] or pool
    hub_lat = G.nodes[hub]["lat"]; hub_lon = G.nodes[hub]["lon"]
    def near(c):
        return abs(G.nodes[c]["lat"]-hub_lat) + abs(G.nodes[c]["lon"]-hub_lon)

    if road_reroute:

        for c in sorted(pool, key=near):
            try:
                path = nx.shortest_path(H, hub, c)
            except nx.NetworkXNoPath:
                continue
            # find highest-risk edge on path
            best = None
            for a, b in zip(path, path[1:]):
                risk = (G.get_edge_data(a, b) or {}).get("base_disruption_risk", 0)
                if best is None or risk > best[1]:
                    best = ((a, b), risk)
            if best and best[1] > 0.2:
                u, v = best[0]
                H.remove_edge(u, v)
                still = nx.has_path(H, hub, c)
                H.add_edge(u, v, **G.get_edge_data(u, v))
                if still:
                    return c
        return pool[0] if pool else None

    for c in sorted(pool, key=near):
        if find_bridge_edge_on_path(G, hub, c):
            return c
    return pool[0] if pool else None


def build_region_graph(clinics):
    nodes = pd.read_csv(os.path.join(DATA, "roads_nodes.csv"))
    edges = pd.read_csv(os.path.join(DATA, "roads_edges.csv"))
    scored = compute_vulnerability_scores(clinics)
    G = build_graph(nodes, edges, scored)
    water = set()
    for rname, cfg in REGIONS.items():
        if cfg["waterways"]:
            try:
                _, wc = add_water_layer(
                    G, os.path.join(DATA, cfg["waterways"]),
                    os.path.join(DATA, cfg["docks"]), clinics)
                water |= wc
            except FileNotFoundError:
                pass
    return G, scored, water


def main():
    os.makedirs(OUT, exist_ok=True)
    clinics = pd.read_csv(os.path.join(DATA, "clinics.csv"))
    payloads = pd.read_csv(os.path.join(DATA, "medical_payloads.csv"))
    payloads = payloads.drop_duplicates("item_id", keep="first").reset_index(drop=True)
    global PAYLOADS_TEST
    if PAYLOADS_TEST is None:
        PAYLOADS_TEST = payloads["item_id"].tolist()  # all items selectable
    demand = pd.read_csv(os.path.join(DATA, "clinic_demand.csv"))
    telecom = pd.read_csv(os.path.join(DATA, "telecom_status.csv"))

    names = dict(zip(clinics["clinic_id"], clinics["clinic_name"]))
    region_of = dict(zip(clinics["clinic_id"], clinics["state_region"]))
    clinic_pcode = dict(zip(clinics["clinic_id"], clinics["township_pcode"]))
    tele = (telecom.drop_duplicates("township_pcode")
            .set_index("township_pcode")[["telecom_status", "priority_multiplier"]]
            .to_dict("index"))

    print("Building warm graph (once)...")
    G, scored, water_clinics = build_region_graph(clinics)
    print(f"  {G.number_of_nodes()} nodes, {len(water_clinics)} near-water clinics")

    # top demand row per clinic
    top_demand = (demand.sort_values("priority_score", ascending=False)
                  .groupby("clinic_id").first().reset_index())
    demand_by_clinic = {r.clinic_id: r for r in top_demand.itertuples()}

    for region, cfg in REGIONS.items():
        region_clinics = [c for c in clinics["clinic_id"] if region_of.get(c) == region]
        want_water = cfg["story"] in ("boat", "river")

        for hub in cfg["hubs"]:
            hub_id = hub["id"]
            tag = f"{region}__{hub_id}"

            # --- triage for this region, telecom-boosted ---
            triage = []
            for cid in region_clinics:
                r = demand_by_clinic.get(cid)
                if r is None:
                    continue
                tinfo = tele.get(clinic_pcode.get(cid),
                                 {"telecom_status": "normal", "priority_multiplier": 1.0})
                boosted = round(min(1.0, r.priority_score * tinfo["priority_multiplier"]), 3)
                triage.append({
                    "clinic_id": cid, "clinic_name": names.get(cid, cid),
                    "top_item": r.item_id, "days_of_stock": r.days_of_stock_remaining,
                    "base_priority": r.priority_score,
                    "telecom_status": tinfo["telecom_status"],
                    "boosted_priority": boosted,
                    "blackout": tinfo["telecom_status"] == "blackout",
                })
            base_rank = {c["clinic_id"]: i for i, c in enumerate(
                sorted(triage, key=lambda x: x["base_priority"], reverse=True))}
            triage.sort(key=lambda x: x["boosted_priority"], reverse=True)
            for i, c in enumerate(triage):
                c["rank_boosted"] = i + 1
                c["rank_base"] = base_rank[c["clinic_id"]] + 1
                c["rank_delta"] = c["rank_base"] - c["rank_boosted"]

            # --- scenario clinic ---
            is_road = cfg["story"] == "road"
            scen_clinic = cfg["scenario"].get("clinic") or pick_scenario_clinic(
                G, hub_id, region_clinics, water_clinics, want_water, road_reroute=is_road)

            payload_results = {}
            normal_route = None
            if scen_clinic and nx.has_path(G, hub_id, scen_clinic):
                # on-the-way run
                extras = [c for c in region_clinics
                          if c != scen_clinic and c != hub_id][:2]
                plan = plan_multi_clinic_route(G, hub_id, scen_clinic, extras, scored)
                normal_route = {
                    "stops": plan["stops"],
                    "stop_names": [names.get(s, s) for s in plan["stops"]],
                    "total_hours": plan["total_cost_hr"],
                    "total_km": plan["total_distance_km"],
                    "n_clinics": plan["n_clinics_served"],
                    "legs": [{"from": l["from"], "to": l["to"],
                              "waypoints": named_chain(G, l["path"], names),
                              "polyline": polyline(G, l["path"]),
                              "summary": leg_summary(G, l["path"])}
                             for l in plan["legs"]],
                }

                # failover
                if is_road:
                    Hr = _road_only_view(G)
                    try:
                        p = nx.shortest_path(Hr, hub_id, scen_clinic)
                        best = None
                        for a, b in zip(p, p[1:]):
                            rk = (G.get_edge_data(a, b) or {}).get("base_disruption_risk", 0)
                            if best is None or rk > best[1]:
                                best = ((a, b), rk)
                        bridge = frozenset(best[0]) if best else None
                    except nx.NetworkXNoPath:
                        bridge = None
                else:
                    bridge = find_bridge_edge_on_path(G, hub_id, scen_clinic)

                H = G.copy()
                if bridge:
                    u, v = tuple(bridge)
                    if H.has_edge(u, v):
                        H.remove_edge(u, v)
                try:
                    bpath, bcost, bdist = route(H, hub_id, scen_clinic, scored)
                    bchain = named_chain(H, bpath, names)
                    bsumm = leg_summary(H, bpath)
                    bline = polyline(H, bpath)
                    uses_water = any((H.get_edge_data(a, b) or {}).get("mode") == "water"
                                     for a, b in zip(bpath, bpath[1:]))
                    reachable = True
                except nx.NetworkXNoPath:
                    bchain, bsumm, bline, uses_water, reachable = [], {}, [], False, False

                for item in PAYLOADS_TEST:
                    prow = payloads.set_index("item_id").loc[item]
                    prow_dict = prow.to_dict()
                    prow_dict["item_id"] = item
                    # some items list 'product_specific' instead of a number ->
                    # default to a sensible WHO window: cold-chain 48h, ambient 720h
                    try:
                        win = int(prow["max_transit_hours"])
                    except (ValueError, TypeError):
                        win = 48 if str(prow.get("cold_chain")).upper() == "TRUE" else 720
                        prow_dict["max_transit_hours"] = win
                    hrs = bsumm.get("total_hours")
                    feasible, reason = (
                        is_payload_feasible(hrs, prow_dict,
                                            has_cold_chain_transport=not uses_water)
                        if reachable else (False, "unreachable after blockage"))
                    payload_results[item] = {
                        "item_name": prow["item_name"],
                        "cold_chain": str(prow["cold_chain"]).upper() == "TRUE",
                        "storage_temp": prow["storage_temp_c"],
                        "max_transit_hours": win,
                        "manifest": {
                            "carrying": prow["item_name"],
                            "must_arrive_within_h": win,
                            "normal_route_h": normal_route["total_hours"] if normal_route else None,
                            "blockage_route_h": hrs,
                            "normal_margin_h": (round(win - normal_route["total_hours"], 1)
                                                if normal_route else None),
                            "blockage_margin_h": round(win - hrs, 1) if hrs is not None else None,
                            "within_time_window": hrs is not None and hrs <= win,
                            "cold_chain_breaks_on_boat": (
                                str(prow["cold_chain"]).upper() == "TRUE" and uses_water),
                            "failure_mode": (
                                "cold_chain_break" if (str(prow["cold_chain"]).upper() == "TRUE"
                                    and uses_water and hrs is not None and hrs <= win)
                                else "time_exceeded" if (hrs is not None and hrs > win)
                                else "none"),
                        },
                        "blockage": {
                            "bridge_cut": tuple(bridge) if bridge else None,
                            "reachable": reachable, "reroute_uses_water": uses_water,
                            "total_cost_hr": hrs, "distance_km": bsumm.get("distance_km"),
                            "payload_feasible": feasible, "payload_reason": reason,
                            "reroute_waypoints": bchain, "reroute_summary": bsumm,
                            "reroute_polyline": bline,
                        },
                    }

            #  map layers/ region 
            tri_by_id = {t["clinic_id"]: t for t in triage}
            markers = []
            for c in clinics.itertuples():
                if region_of.get(c.clinic_id) != region:
                    continue
                t = tri_by_id.get(c.clinic_id, {})
                score = t.get("boosted_priority", 0.2)
                markers.append({
                    "id": c.clinic_id, "name": c.clinic_name,
                    "lat": c.latitude, "lon": c.longitude,
                    "priority": score, "base_priority": t.get("base_priority", 0.2),
                    "boosted_priority": score, "color": priority_color(score),
                    "telecom_status": t.get("telecom_status", "normal"),
                    "blackout": t.get("blackout", False),
                    "near_water": c.clinic_id in water_clinics,
                    "is_hub": c.clinic_id == hub_id,
                })
            docks, wlines = [], []
            if cfg["waterways"]:
                for n, d in G.nodes(data=True):
                    if d.get("node_type") == "dock":
                        # only docks within region bbox-ish (by proximity to region clinics)
                        docks.append({"id": n, "name": n, "lat": d["lat"], "lon": d["lon"]})
                for u, v, d in G.edges(data=True):
                    if d.get("mode") == "water":
                        wlines.append({"from": [G.nodes[u]["lat"], G.nodes[u]["lon"]],
                                       "to": [G.nodes[v]["lat"], G.nodes[v]["lon"]]})

            out = {
                "region": region, "hub": hub_id,
                "hub_name": hub["name"], "story": cfg["story"],
                "center": cfg["center"], "zoom": cfg["zoom"],
                "scenario_clinic": scen_clinic,
                "scenario_clinic_name": names.get(scen_clinic, scen_clinic),
                "triage": triage[:40],
                "route_normal": normal_route,
                "failover": payload_results,
                "map_layers": {"clinics": markers, "docks": docks, "waterways": wlines},
            }
            with open(os.path.join(OUT, f"{tag}.json"), "w") as f:
                json.dump(out, f, separators=(",", ":"))
            movers = sum(1 for t in triage if t["blackout"] and t["rank_delta"] > 0)
            print(f"  {tag:34s} clinics={len(markers):3d} scen={scen_clinic} "
                  f"water={'Y' if any(v['blockage']['reroute_uses_water'] for v in payload_results.values()) else 'N'} "
                  f"blackout_movers={movers}")

    print(f"\nDone. Wrote scenarios to {OUT}/")


if __name__ == "__main__":
    main()
