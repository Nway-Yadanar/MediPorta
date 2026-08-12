"""
connect_real_clinics_to_roads.py

Builds a routable road network connected to the REAL clinic locations from
clinics.csv (207 real facilities from MIMU). This is a bridge step: hub
positions are derived from real township clusters (so backbone distances are
real), but backbone road GEOMETRY/risk is still a placeholder mesh -- replace
with the actual hotosm_mmr_roads GPKG once you've got it loaded via
load_real_roads.py.

Run this AFTER load_real_clinics_from_geojson.py (needs clinics.csv to exist).

Usage: python connect_real_clinics_to_roads.py
Outputs: roads_nodes.csv, roads_edges.csv (overwrites, connected to real clinics)
"""

import numpy as np
import pandas as pd

rng = np.random.default_rng(7)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def main():
    clinics = pd.read_csv("clinics.csv")
    print(f"Building road network for {len(clinics)} real clinics across "
          f"{clinics.township.nunique()} townships...")

    hubs = clinics.groupby("township").agg(
        latitude=("latitude", "mean"),
        longitude=("longitude", "mean"),
        state_region=("state_region", "first"),
    ).reset_index()
    hubs["node_id"] = "HUB-" + hubs["township"].str.replace(" ", "_")

    nodes = [
        {"node_id": h.node_id, "node_type": "township_hub", "latitude": h.latitude, "longitude": h.longitude}
        for h in hubs.itertuples()
    ]
    nodes += [
        {"node_id": c.clinic_id, "node_type": "clinic", "latitude": c.latitude, "longitude": c.longitude}
        for c in clinics.itertuples()
    ]
    nodes_df = pd.DataFrame(nodes)

    # connect each hub to its 5 nearest hubs (real distances, placeholder risk)
    edges = []
    seen_pairs = set()
    for i, h1 in hubs.iterrows():
        dists = hubs.apply(lambda h2: haversine_km(h1.latitude, h1.longitude, h2.latitude, h2.longitude), axis=1)
        nearest = dists.sort_values().index[1:6]
        for j in nearest:
            pair = tuple(sorted((h1.node_id, hubs.loc[j].node_id)))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            is_risky = rng.random() < 0.3
            edges.append({
                "from_node": h1.node_id, "to_node": hubs.loc[j].node_id,
                "distance_km": round(dists[j], 2),
                "road_type": rng.choice(["primary", "secondary"], p=[0.6, 0.4]),
                "base_disruption_risk": round(rng.uniform(0.45, 0.75), 3) if is_risky else round(rng.uniform(0.03, 0.15), 3),
            })

    # connect each real clinic to its own township hub + 1 nearby hub
    for c in clinics.itertuples():
        own_hub = hubs[hubs.township == c.township].iloc[0]
        edges.append({
            "from_node": own_hub.node_id, "to_node": c.clinic_id,
            "distance_km": round(haversine_km(c.latitude, c.longitude, own_hub.latitude, own_hub.longitude) + 2, 2),  # +2km local road buffer
            "road_type": rng.choice(["tertiary", "track"], p=[0.5, 0.5]),
            "base_disruption_risk": round(rng.uniform(0.45, 0.70), 3),
        })
        # second connection to nearest OTHER hub 
        other_hubs = hubs[hubs.township != c.township].copy()
        other_hubs["dist"] = other_hubs.apply(
            lambda h: haversine_km(c.latitude, c.longitude, h.latitude, h.longitude), axis=1
        )
        nearest_other = other_hubs.nsmallest(1, "dist").iloc[0]
        edges.append({
            "from_node": nearest_other.node_id, "to_node": c.clinic_id,
            "distance_km": round(nearest_other.dist + 2, 2),
            "road_type": rng.choice(["tertiary", "track"], p=[0.5, 0.5]),
            "base_disruption_risk": round(rng.uniform(0.10, 0.30), 3),
        })

    edges_df = pd.DataFrame(edges)
    nodes_df.to_csv("roads_nodes.csv", index=False)
    edges_df.to_csv("roads_edges.csv", index=False)

    print(f"Wrote roads_nodes.csv ({len(nodes_df)} nodes: {len(hubs)} real township hubs + {len(clinics)} real clinics)")
    print(f"Wrote roads_edges.csv ({len(edges_df)} edges)")
    print("\nNOTE: hub positions + backbone distances are now REAL (derived from actual")
    print("clinic township clusters). Road GEOMETRY and disruption_risk are still a")
    print("placeholder mesh -- swap in via load_real_roads.py once you have the real")
    print("hotosm_mmr_roads GPKG file.")


if __name__ == "__main__":
    main()
