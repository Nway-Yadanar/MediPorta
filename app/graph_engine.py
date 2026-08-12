"""
graph_engine.py

Builds the risk-weighted transport graph and computes routes.

This is MediRoute's core differentiator: routing cost is NOT just distance/time.
It blends:
  - travel time (from distance)
  - road disruption risk (conflict/weather/access restriction)
  - destination clinic vulnerability (routes serving urgent clinics get a cost discount)

In production, `distance_km` + graph topology comes from OSMnx
(ox.graph_from_place / ox.graph_from_bbox) instead of the synthetic edges here —
everything downstream of "build a NetworkX graph with these edge attributes"
is unchanged.
"""

import networkx as nx
import pandas as pd

AVG_SPEED_KMH = {
    "primary": 45,
    "secondary": 30,
    "tertiary": 18,
    "track": 10,
}

ROAD_ACCESS_RISK_MULTIPLIER = {
    "all_weather": 1.0,
    "seasonal": 1.4,
    "conflict_restricted": 2.2,
}


def build_graph(nodes_df: pd.DataFrame, edges_df: pd.DataFrame, clinics_scored: pd.DataFrame) -> nx.Graph:
    G = nx.Graph()

    # vectorized node add (itertuples is ~10-50x faster than iterrows at this scale)
    G.add_nodes_from(
        (n.node_id, {"node_type": n.node_type, "lat": n.latitude, "lon": n.longitude})
        for n in nodes_df.itertuples()
    )

    # attach vulnerability score + access flag onto clinic nodes
    vuln_lookup = clinics_scored.set_index("clinic_id")[["vulnerability_score", "road_access_flag"]].to_dict("index")

    speed_map = AVG_SPEED_KMH
    risk_mult_map = ROAD_ACCESS_RISK_MULTIPLIER

    def edge_iter():
        # prefer the hazard-enriched risk column when present (real overlay);
        # fall back to the road-class placeholder otherwise
        has_enriched = "enriched_disruption_risk" in edges_df.columns
        for e in edges_df.itertuples():
            speed = speed_map.get(e.road_type, 20)
            travel_time_hr = e.distance_km / speed
            dest_info = vuln_lookup.get(e.to_node)
            access_mult = risk_mult_map.get(
                dest_info["road_access_flag"] if dest_info else "all_weather", 1.0
            )
            risk = (getattr(e, "enriched_disruption_risk", None)
                    if has_enriched else None)
            if risk is None:
                risk = e.base_disruption_risk
            yield (
                e.from_node, e.to_node,
                {
                    "distance_km": e.distance_km,
                    "travel_time_hr": round(travel_time_hr, 3),
                    "base_disruption_risk": risk,
                    "road_type": e.road_type,
                    "access_risk_multiplier": access_mult,
                },
            )

    G.add_edges_from(edge_iter())
    return G


def compute_edge_cost(edge_data: dict, dest_vulnerability: float, risk_weight: float = 1.0, equity_weight: float = 1.0) -> float:
    """
    The MediRoute cost function.

    edge_cost = travel_time
              * (1 + risk_weight * disruption_risk * access_risk_multiplier)
              * (1 - equity_weight * 0.3 * dest_vulnerability)   # discount toward high-need clinics

    risk_weight and equity_weight are the two sliders exposed in the dashboard
    ("prioritize safety" vs "prioritize reaching the neediest clinic").
    """
    travel_time = edge_data["travel_time_hr"]
    disruption = edge_data["base_disruption_risk"] * edge_data["access_risk_multiplier"]

    risk_factor = 1 + (risk_weight * disruption)
    equity_discount = max(0.1, 1 - (equity_weight * 0.3 * dest_vulnerability))  # floor so cost never hits 0/negative

    # Mode preference: boats/transfers carry an operational penalty so a road route
    # is preferred by default. Boats are only chosen when the road path is genuinely
    # unavailable or far worse (e.g. after a bridge blockage). Roads have multiplier 1.0.
    mode_mult = edge_data.get("mode_cost_multiplier", 1.0)

    return travel_time * risk_factor * equity_discount * mode_mult


def route(G: nx.Graph, source: str, target: str, clinics_scored: pd.DataFrame,
          risk_weight: float = 1.0, equity_weight: float = 1.0, naive: bool = False):
    """
    Returns (path, total_cost_hours, total_distance_km).
    If naive=True, ignores risk/equity weighting entirely (pure shortest travel-time path)
    — used for the "naive vs MediRoute" comparison demo.
    """
    vuln_lookup = clinics_scored.set_index("clinic_id")["vulnerability_score"].to_dict()

    def weight_fn(u, v, d):
        if naive:
            return d["travel_time_hr"]
        dest_vuln = vuln_lookup.get(v, vuln_lookup.get(u, 0.0))
        return compute_edge_cost(d, dest_vuln, risk_weight, equity_weight)

    path = nx.shortest_path(G, source, target, weight=weight_fn)
    total_cost = sum(
        weight_fn(path[i], path[i + 1], G.get_edge_data(path[i], path[i + 1]))
        for i in range(len(path) - 1)
    )
    total_distance = sum(
        G.get_edge_data(path[i], path[i + 1])["distance_km"]
        for i in range(len(path) - 1)
    )
    return path, round(total_cost, 3), round(total_distance, 2)


def build_priority_queue(clinics_scored: pd.DataFrame, top_n: int = 10) -> pd.DataFrame:
    """Dispatch priority queue: highest vulnerability + lowest stock first."""
    return clinics_scored.sort_values(
        ["vulnerability_score", "current_stock_days_remaining"],
        ascending=[False, True]
    ).head(top_n)[[
        "clinic_id", "clinic_name", "current_stock_days_remaining",
        "vulnerability_score", "road_access_flag"
    ]]


if __name__ == "__main__":
    import time
    from vulnerability import compute_vulnerability_scores

    clinics = pd.read_csv("../data/clinics.csv")
    nodes = pd.read_csv("../data/roads_nodes.csv")
    edges = pd.read_csv("../data/roads_edges.csv")

    scored = compute_vulnerability_scores(clinics)
    G = build_graph(nodes, edges, scored)

    print(f"Graph built: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # --- Success criteria check: detection speed ---
    t0 = time.time()
    scored_again = compute_vulnerability_scores(clinics)
    detection_ms = (time.time() - t0) * 1000
    print(f"\nStockout scoring detection time: {detection_ms:.2f} ms (target: <60,000 ms) -> {'PASS' if detection_ms < 60000 else 'FAIL'}")

    
    print("\nTop priority dispatch queue:")
    print(build_priority_queue(scored, top_n=5).to_string(index=False))

    
    source, target = "HUB-Sittwe", scored.iloc[0]["clinic_id"]  # route to most vulnerable clinic
    print(f"\nRouting from {source} to most urgent clinic {target}...")

    naive_path, naive_cost, naive_dist = route(G, source, target, scored, naive=True)
    smart_path, smart_cost, smart_dist = route(G, source, target, scored, risk_weight=1.5, equity_weight=1.2)

    print(f"\nNaive (shortest time) path : {naive_path}")
    print(f"  cost={naive_cost}h  distance={naive_dist}km")
    print(f"\nMediRoute (risk+equity weighted) path: {smart_path}")
    print(f"  cost={smart_cost}h  distance={smart_dist}km")
