"""
water_routes.py

Feature 3: Water-route support (multi-modal graph).

Adds a boat layer onto the SAME NetworkX graph the road router already uses, so
the existing risk-weighted Dijkstra handles road+boat routes with no new
algorithm. We add:

  * dock nodes            (boat_docks.geojson, Points)            [synthetic]
  * waterway edges        (waterways.geojson, LineStrings)        [synthetic]
    - travel_time from BOAT_SPEED_KMH
  * dock<->road transfer edges (a dock connects to its nearest road node)
    - carries a TRANSFER_PENALTY_HR for loading/unloading supplies
  * dock<->clinic edges for clinics within WATER_SNAP_KM of a dock
    (the "boats only connect to clinics near water" rule)

Everything added here is flagged in edge attributes with mode="water" /
mode="transfer" so cost decomposition and provenance stay honest.

PROVENANCE: all waterway geometry, dock locations, boat speed and transfer
penalty are synthetic / assumption-based (no open navigable-waterway + dock
dataset at clinic granularity for Myanmar). Flagged mode-tagged + synthetic.
"""

import json
import math

import networkx as nx
import numpy as np
from scipy.spatial import cKDTree

BOAT_SPEED_KMH = 18.0          # assumption: small river/coastal supply boat
TRANSFER_PENALTY_HR = 0.5      # 30 min load/unload at a dock transfer  [assumption]
WATER_SNAP_KM = 6.0            # a clinic is "near water" if within this of a dock
BOAT_DISRUPTION_RISK = 0.25    # baseline water disruption (weather/current) [assumption]


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def load_geojson(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def add_water_layer(G: nx.Graph, waterways_path: str, docks_path: str, clinics_df):
    """
    Mutates G in place: adds dock nodes, waterway edges, transfer edges, and
    dock<->clinic edges. Returns (dock_ids, water_clinic_ids).
    """
    waterways = load_geojson(waterways_path)
    docks = load_geojson(docks_path)

    # --- road node KDTree for snapping docks to the road network ---
    road_nodes = [
        (n, d["lat"], d["lon"])
        for n, d in G.nodes(data=True)
        if d.get("node_type") == "road_vertex"
    ]
    road_ids = [r[0] for r in road_nodes]
    road_coords = np.array([[r[1], r[2]] for r in road_nodes])
    road_tree = cKDTree(road_coords)

    # --- add dock nodes ---
    dock_ids = []
    dock_coords = []
    for feat in docks["features"]:
        did = feat["properties"]["dock_id"]
        lon, lat = feat["geometry"]["coordinates"]
        G.add_node(did, node_type="dock", lat=lat, lon=lon)
        dock_ids.append(did)
        dock_coords.append((lat, lon))

        # transfer edge: dock <-> nearest road vertex (carries the transfer penalty)
        _, idx = road_tree.query([lat, lon])
        rnode = road_ids[idx]
        rlat, rlon = road_coords[idx]
        dist = _haversine_km(lat, lon, rlat, rlon)
        G.add_edge(
            did, rnode,
            distance_km=round(dist, 3),
            travel_time_hr=round(TRANSFER_PENALTY_HR, 3),  # penalty dominates a short hop
            base_disruption_risk=0.05,
            access_risk_multiplier=1.0,
            road_type="transfer",
            mode="transfer",
            mode_cost_multiplier=6.0,
            _provenance="synthetic transfer edge (load/unload penalty)",
        )

    dock_coords = np.array(dock_coords)
    dock_tree = cKDTree(dock_coords)

    # --- add waterway edges between consecutive docks along each LineString ---
    # Each waterway lists an ordered set of dock_ids it connects.
    for feat in waterways["features"]:
        seq = feat["properties"].get("dock_sequence", [])
        for a, b in zip(seq, seq[1:]):
            if a in G and b in G:
                la, lo = G.nodes[a]["lat"], G.nodes[a]["lon"]
                lb, lob = G.nodes[b]["lat"], G.nodes[b]["lon"]
                dist = _haversine_km(la, lo, lb, lob)
                G.add_edge(
                    a, b,
                    distance_km=round(dist, 3),
                    travel_time_hr=round(dist / BOAT_SPEED_KMH, 3),
                    base_disruption_risk=BOAT_DISRUPTION_RISK,
                    access_risk_multiplier=1.0,
                    road_type="waterway",
                    mode="water",
                    mode_cost_multiplier=8.0,
                    _provenance="synthetic waterway edge (hand-drawn geometry)",
                )

    # --- dock <-> clinic edges for clinics near water ---
    water_clinic_ids = set()
    clinic_nodes = [
        (n, d["lat"], d["lon"])
        for n, d in G.nodes(data=True)
        if d.get("node_type") == "clinic"
    ]
    for cid, clat, clon in clinic_nodes:
        d_km, idx = dock_tree.query([clat, clon])
        dist = _haversine_km(clat, clon, dock_coords[idx][0], dock_coords[idx][1])
        if dist <= WATER_SNAP_KM:
            dock = dock_ids[idx]
            G.add_edge(
                cid, dock,
                distance_km=round(dist, 3),
                travel_time_hr=round(dist / BOAT_SPEED_KMH, 3),
                base_disruption_risk=BOAT_DISRUPTION_RISK,
                access_risk_multiplier=1.0,
                road_type="waterway",
                mode="water",
                mode_cost_multiplier=8.0,
                _provenance="synthetic dock<->clinic boat edge (near-water rule)",
            )
            water_clinic_ids.add(cid)

    return dock_ids, water_clinic_ids
