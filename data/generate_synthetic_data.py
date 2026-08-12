"""
generate_synthetic_data.py

Creates synthetic clinic + road network data for Rakhine State that mirrors
the real MIMU / HDX / WHO-UNICEF schema, so this can be swapped for real
data later with zero code changes downstream.

Run: python generate_synthetic_data.py
Outputs: clinics.csv, roads_edges.csv, roads_nodes.csv  (in this folder)
"""

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

# ---------------------------------------------------------------------------
# 1. CLINICS  (mirrors: MIMU health facility layer + WHO/UNICEF baseline data)
# ---------------------------------------------------------------------------
# Rough bounding box for Rakhine State, Myanmar
LAT_MIN, LAT_MAX = 18.0, 21.5
LON_MIN, LON_MAX = 92.2, 94.9

TOWNSHIPS = [
    "Sittwe", "Mrauk-U", "Kyauktaw", "Minbya", "Myebon",
    "Ponnagyun", "Rathedaung", "Buthidaung", "Maungdaw", "Pauktaw",
    "Kyaukpyu", "Munaung", "Ann", "Toungup", "Thandwe", "Gwa",
]

N_CLINICS = 40

clinic_ids = [f"CL-{i:03d}" for i in range(1, N_CLINICS + 1)]

clinics = pd.DataFrame({
    "clinic_id": clinic_ids,
    "clinic_name": [f"{rng.choice(TOWNSHIPS)} Rural Health Center {i}" for i in range(N_CLINICS)],
    "township_pcode": [f"MMR{rng.integers(1000, 9999)}" for _ in range(N_CLINICS)],  # mimics MIMU PCode format
    "latitude": rng.uniform(LAT_MIN, LAT_MAX, N_CLINICS).round(5),
    "longitude": rng.uniform(LON_MIN, LON_MAX, N_CLINICS).round(5),
    # Health baseline indicators (mirrors WHO/UNICEF MICS-style fields)
    "institutional_delivery_rate": rng.uniform(0.10, 0.45, N_CLINICS).round(3),
    "skilled_birth_attendance_rate": rng.uniform(0.08, 0.40, N_CLINICS).round(3),
    "full_vaccination_rate": rng.uniform(0.40, 0.85, N_CLINICS).round(3),
    # Live operational data (would come from a stock-reporting system / SMS reports)
    "current_stock_days_remaining": rng.integers(0, 30, N_CLINICS),
    "population_served": rng.integers(500, 12000, N_CLINICS),
    "road_access_flag": rng.choice(["all_weather", "seasonal", "conflict_restricted"], N_CLINICS, p=[0.4, 0.35, 0.25]),
})

clinics.to_csv("clinics.csv", index=False)

# ---------------------------------------------------------------------------
# 2. ROAD NETWORK NODES + EDGES  (mirrors: HOT/HDX OSM road extract schema)
# ---------------------------------------------------------------------------
# Simple synthetic network: a hub node per township + connections to nearby clinics
# In production this whole block is replaced by osmnx.graph_from_place(...)

hub_nodes = []
for t in TOWNSHIPS:
    hub_nodes.append({
        "node_id": f"HUB-{t}",
        "node_type": "township_hub",
        "latitude": rng.uniform(LAT_MIN, LAT_MAX),
        "longitude": rng.uniform(LON_MIN, LON_MAX),
    })

clinic_nodes = [
    {"node_id": row.clinic_id, "node_type": "clinic", "latitude": row.latitude, "longitude": row.longitude}
    for row in clinics.itertuples()
]

nodes_df = pd.DataFrame(hub_nodes + clinic_nodes)
nodes_df.to_csv("roads_nodes.csv", index=False)

# Edges: connect hubs to each other (backbone) + each clinic to its nearest hub (last mile)
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))

edges = []

# backbone: connect each hub to its 5 nearest hubs (denser mesh -> real alternate routes exist)
hub_df = pd.DataFrame(hub_nodes)
seen_pairs = set()
for i, h1 in hub_df.iterrows():
    dists = hub_df.apply(lambda h2: haversine_km(h1.latitude, h1.longitude, h2.latitude, h2.longitude), axis=1)
    nearest = dists.sort_values().index[1:6]  # skip self, take 5 nearest
    for j in nearest:
        pair = tuple(sorted((h1.node_id, hub_df.loc[j].node_id)))
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        h2 = hub_df.loc[j]
        dist_km = dists[j]
        # deliberately create a mix: some short-but-risky roads, some longer-but-safe roads,
        # so the risk-weighted router actually has a real tradeoff to make
        is_risky_shortcut = rng.random() < 0.35
        edges.append({
            "from_node": h1.node_id, "to_node": h2.node_id,
            "distance_km": round(dist_km, 2),
            "road_type": rng.choice(["primary", "secondary"], p=[0.6, 0.4]),
            "base_disruption_risk": round(rng.uniform(0.45, 0.75), 3) if is_risky_shortcut else round(rng.uniform(0.03, 0.15), 3),
        })

# last mile: connect each clinic to its 2 nearest hubs (gives routing options into the last mile too)
for c in clinic_nodes:
    dists = hub_df.apply(lambda h: haversine_km(c["latitude"], c["longitude"], h.latitude, h.longitude), axis=1)
    nearest_two = dists.sort_values().index[:2]
    for rank, j in enumerate(nearest_two):
        hub = hub_df.loc[j]
        edges.append({
            "from_node": hub.node_id, "to_node": c["node_id"],
            "distance_km": round(dists[j], 2),
            "road_type": rng.choice(["tertiary", "track"], p=[0.5, 0.5]),
            # the closer hub connection is often the riskier/rougher track; the 2nd-nearest is the safer detour
            "base_disruption_risk": round(rng.uniform(0.45, 0.70), 3) if rank == 0 else round(rng.uniform(0.10, 0.30), 3),
        })

edges_df = pd.DataFrame(edges)
edges_df.to_csv("roads_edges.csv", index=False)

print(f"Generated {len(clinics)} clinics, {len(nodes_df)} nodes, {len(edges_df)} edges.")
print("Files: clinics.csv, roads_nodes.csv, roads_edges.csv")
