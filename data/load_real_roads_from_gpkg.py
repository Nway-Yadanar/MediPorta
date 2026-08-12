"""
load_real_roads_from_gpkg.py

Parses the real hotosm_mmr_roads GeoPackage DIRECTLY via Python's stdlib sqlite3
+ struct modules -- no geopandas/fiona/osmnx dependency needed. GeoPackage is
just SQLite with geometries stored as GeoPackage Binary (GPB): an 8-40 byte
header wrapping standard WKB.

Builds a real routable road graph:
  1. Pulls road segments for target regions (filtered by real adm1_name field
     already present in the dataset -- no spatial join needed)
  2. Parses WKB LineString/MultiLineString geometry into coordinate sequences
  3. Builds a graph: vertices = coordinate points (rounded, so shared endpoints
     between OSM ways snap together into real intersections), edges = segments
     between consecutive vertices, distance = real haversine length
  4. Snaps real clinic locations (from clinics.csv) onto the nearest real road
     vertex via KD-tree, adds a short local-access edge
  5. Keeps only the largest connected component (OSM extracts can have small
     disconnected fragments) so routing between any two hubs/clinics is
     guaranteed to work
  6. Writes roads_nodes.csv / roads_edges.csv in MediRoute's existing schema

Usage:
    python load_real_roads_from_gpkg.py real/roads.gpkg
"""

import struct
import sys
import sqlite3
from collections import defaultdict

import numpy as np
import pandas as pd

TARGET_REGIONS = ["Rakhine", "Sagaing", "Mandalay"]
DRIVABLE_HIGHWAY_TYPES = [
    "trunk", "trunk_link", "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "unclassified", "residential", "living_street", "track",
]

ROAD_TYPE_MAP = {
    "trunk": "primary", "trunk_link": "primary", "primary": "primary", "primary_link": "primary",
    "secondary": "secondary", "secondary_link": "secondary",
    "tertiary": "tertiary", "tertiary_link": "tertiary", "unclassified": "tertiary",
    "residential": "tertiary", "living_street": "tertiary", "track": "track",
}

BASE_RISK_BY_TYPE = {"primary": 0.12, "secondary": 0.22, "tertiary": 0.35, "track": 0.55}

COORD_PRECISION = 6  


def parse_gpb_geometry(blob: bytes):
    """
    Parses a GeoPackage Binary blob -> list of coordinate lists (one per
    LineString; MultiLineString is flattened into multiple lists).
    Returns [] for non-line geometries or empties.
    """
    if blob is None or len(blob) < 8 or blob[0:2] != b"GP":
        return []

    flags = blob[3]
    byte_order = "<" if (flags & 0x01) else ">"
    envelope_indicator = (flags >> 1) & 0x07
    envelope_bytes = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get(envelope_indicator, 0)
    offset = 8 + envelope_bytes  # WKB starts here

    return _parse_wkb(blob, offset, byte_order)


def _parse_wkb(blob: bytes, offset: int, _outer_order: str):
    wkb_order = "<" if blob[offset] == 1 else ">"
    geom_type = struct.unpack_from(wkb_order + "I", blob, offset + 1)[0]
    base_type = geom_type % 1000  # strip Z/M/ZM dimensionality flags
    pos = offset + 5

    if base_type == 2:  # LineString
        n = struct.unpack_from(wkb_order + "I", blob, pos)[0]
        pos += 4
        coords = []
        for _ in range(n):
            x, y = struct.unpack_from(wkb_order + "dd", blob, pos)
            coords.append((round(x, COORD_PRECISION), round(y, COORD_PRECISION)))
            pos += 16 if geom_type < 1000 else (24 if geom_type < 3000 else 32)
        return [coords] if len(coords) >= 2 else []

    elif base_type == 5:  # MultiLineString
        n_geoms = struct.unpack_from(wkb_order + "I", blob, pos)[0]
        pos += 4
        results = []
        for _ in range(n_geoms):
            sub_order = "<" if blob[pos] == 1 else ">"
            sub_type = struct.unpack_from(sub_order + "I", blob, pos + 1)[0]
            sub_base = sub_type % 1000
            sub_pos = pos + 5
            if sub_base == 2:
                n = struct.unpack_from(sub_order + "I", blob, sub_pos)[0]
                sub_pos += 4
                coords = []
                for _ in range(n):
                    x, y = struct.unpack_from(sub_order + "dd", blob, sub_pos)
                    coords.append((round(x, COORD_PRECISION), round(y, COORD_PRECISION)))
                    sub_pos += 16 if sub_type < 1000 else (24 if sub_type < 3000 else 32)
                if len(coords) >= 2:
                    results.append(coords)
                pos = sub_pos
            else:
                break  # unexpected nested type, stop parsing this multi-geometry
        return results

    return []


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def load_road_segments(gpkg_path: str):
    con = sqlite3.connect(gpkg_path)
    cur = con.cursor()
    placeholders = ",".join("?" * len(TARGET_REGIONS))
    highway_placeholders = ",".join("?" * len(DRIVABLE_HIGHWAY_TYPES))
    query = f"""
        SELECT geom, highway, adm1_name
        FROM roads
        WHERE adm1_name IN ({placeholders})
        AND highway IN ({highway_placeholders})
    """
    cur.execute(query, TARGET_REGIONS + DRIVABLE_HIGHWAY_TYPES)

    print("Query executed, streaming + parsing geometries...")
    edges = []  # (lon1,lat1,lon2,lat2,road_type)
    n_rows = 0
    n_parsed_fail = 0
    for geom_blob, highway, region in cur:
        n_rows += 1
        try:
            linestrings = parse_gpb_geometry(geom_blob)
        except Exception:
            n_parsed_fail += 1
            continue
        road_type = ROAD_TYPE_MAP.get(highway, "tertiary")
        for coords in linestrings:
            for i in range(len(coords) - 1):
                lon1, lat1 = coords[i]
                lon2, lat2 = coords[i + 1]
                if lon1 == lon2 and lat1 == lat2:
                    continue
                edges.append((lon1, lat1, lon2, lat2, road_type))
        if n_rows % 20000 == 0:
            print(f"  ...{n_rows} rows processed, {len(edges)} raw edges so far")

    con.close()
    print(f"Done: {n_rows} road segments read, {n_parsed_fail} failed to parse, {len(edges)} raw edges extracted")
    return edges


def build_graph_from_edges(raw_edges):
    """Builds node/edge tables from raw (lon1,lat1,lon2,lat2,road_type) tuples,
    snapping shared coordinates together as intersection nodes, THEN simplifies
    by contracting chains of degree-2 "pass-through" points (points that just
    trace a road's curve, not real intersections) into single edges -- the
    same technique OSMnx uses. Raw OSM extracts have a vertex for every curve
    point; without this, the graph is 10-20x too large to route on live."""
    node_coord_to_id = {}
    node_list = []

    def get_node_id(lon, lat):
        key = (lon, lat)
        if key not in node_coord_to_id:
            node_coord_to_id[key] = f"RN-{len(node_list)}"
            node_list.append((node_coord_to_id[key], lat, lon))
        return node_coord_to_id[key]

    adj = defaultdict(dict)  
    seen_edge_keys = set()
    for lon1, lat1, lon2, lat2, road_type in raw_edges:
        n1 = get_node_id(lon1, lat1)
        n2 = get_node_id(lon2, lat2)
        key = frozenset((n1, n2))
        if key in seen_edge_keys or n1 == n2:
            continue
        seen_edge_keys.add(key)
        dist = haversine_km(lat1, lon1, lat2, lon2)
        if dist == 0:
            continue
        adj[n1][n2] = (dist, road_type)
        adj[n2][n1] = (dist, road_type)

    print(f"Pre-simplification: {len(node_list)} raw vertices, {len(seen_edge_keys)} raw segments")
    print("Simplifying (contracting degree-2 pass-through points into real intersections)...")

    degree = {n: len(neighbors) for n, neighbors in adj.items()}
    intersections = {n for n, d in degree.items() if d != 2}

    visited_edges = set()
    simplified = []  # (n1, n2, total_dist, road_type)

    for start in intersections:
        for first_neighbor in list(adj[start].keys()):
            edge_key = frozenset((start, first_neighbor))
            if edge_key in visited_edges:
                continue
            visited_edges.add(edge_key)
            path_dist, road_type = adj[start][first_neighbor]
            prev, curr = start, first_neighbor
            steps = 0
            while degree.get(curr) == 2 and steps < 100000:
                neighbors = list(adj[curr].keys())
                nxt = neighbors[0] if neighbors[0] != prev else neighbors[1]
                nxt_edge_key = frozenset((curr, nxt))
                if nxt_edge_key in visited_edges:
                    break
                visited_edges.add(nxt_edge_key)
                d, rt = adj[curr][nxt]
                path_dist += d
                prev, curr = curr, nxt
                steps += 1
            end = curr
            if end != start:
                simplified.append((start, end, path_dist, road_type))

    print(f"Post-simplification: {len(intersections)} real intersection/endpoint nodes, {len(simplified)} edges")

    keep_node_ids = set()
    edge_rows = []
    for n1, n2, dist, road_type in simplified:
        keep_node_ids.add(n1)
        keep_node_ids.add(n2)
        edge_rows.append({
            "from_node": n1, "to_node": n2,
            "distance_km": round(dist, 4),
            "road_type": road_type,
            "base_disruption_risk": BASE_RISK_BY_TYPE[road_type],
        })

    nodes_df = pd.DataFrame(
        [(nid, lat, lon) for nid, lat, lon in node_list if nid in keep_node_ids],
        columns=["node_id", "latitude", "longitude"],
    )
    nodes_df["node_type"] = "road_vertex"
    edges_df = pd.DataFrame(edge_rows)
    return nodes_df, edges_df


def keep_largest_component(nodes_df, edges_df):
    """Union-find to keep only the largest connected component -- guarantees
    any two hubs/clinics we later snap onto the network can actually route
    between each other."""
    parent = {n: n for n in nodes_df.node_id}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for row in edges_df.itertuples():
        union(row.from_node, row.to_node)

    comp_sizes = defaultdict(int)
    for n in parent:
        comp_sizes[find(n)] += 1
    largest_root = max(comp_sizes, key=comp_sizes.get)
    keep_nodes = {n for n in parent if find(n) == largest_root}

    print(f"Connected components: {len(comp_sizes)}, largest has {len(keep_nodes)}/{len(nodes_df)} nodes "
          f"({100*len(keep_nodes)/len(nodes_df):.1f}%)")

    nodes_kept = nodes_df[nodes_df.node_id.isin(keep_nodes)].reset_index(drop=True)
    edges_kept = edges_df[
        edges_df.from_node.isin(keep_nodes) & edges_df.to_node.isin(keep_nodes)
    ].reset_index(drop=True)
    return nodes_kept, edges_kept


def snap_clinics_and_hubs(nodes_df, edges_df, clinics_df):
    """Adds real clinic locations + township hubs (centroid of clinics per
    township) as graph nodes, connected via a short local-access edge to the
    nearest real road vertex (KD-tree nearest neighbor)."""
    from scipy.spatial import cKDTree

    road_coords = nodes_df[["latitude", "longitude"]].to_numpy()
    tree = cKDTree(road_coords)

    hubs = clinics_df.groupby("township").agg(
        latitude=("latitude", "mean"), longitude=("longitude", "mean")
    ).reset_index()
    hubs["node_id"] = "HUB-" + hubs["township"].str.replace(" ", "_")

    new_nodes = []
    new_edges = []

    for h in hubs.itertuples():
        _, idx = tree.query([h.latitude, h.longitude])
        nearest = nodes_df.iloc[idx]
        dist = haversine_km(h.latitude, h.longitude, nearest.latitude, nearest.longitude)
        new_nodes.append({"node_id": h.node_id, "node_type": "township_hub", "latitude": h.latitude, "longitude": h.longitude})
        new_edges.append({
            "from_node": h.node_id, "to_node": nearest.node_id,
            "distance_km": round(dist, 3), "road_type": "tertiary", "base_disruption_risk": 0.2,
        })

    for c in clinics_df.itertuples():
        _, idx = tree.query([c.latitude, c.longitude])
        nearest = nodes_df.iloc[idx]
        dist = haversine_km(c.latitude, c.longitude, nearest.latitude, nearest.longitude)
        new_nodes.append({"node_id": c.clinic_id, "node_type": "clinic", "latitude": c.latitude, "longitude": c.longitude})
        new_edges.append({
            "from_node": c.clinic_id, "to_node": nearest.node_id,
            "distance_km": round(dist, 3), "road_type": "track", "base_disruption_risk": 0.5,
        })

    nodes_out = pd.concat([nodes_df, pd.DataFrame(new_nodes)], ignore_index=True)
    edges_out = pd.concat([edges_df, pd.DataFrame(new_edges)], ignore_index=True)
    return nodes_out, edges_out


def main():
    gpkg_path = sys.argv[1] if len(sys.argv) > 1 else "real/roads.gpkg"

    raw_edges = load_road_segments(gpkg_path)
    nodes_df, edges_df = build_graph_from_edges(raw_edges)
    print(f"Raw graph: {len(nodes_df)} nodes, {len(edges_df)} edges")

    nodes_df, edges_df = keep_largest_component(nodes_df, edges_df)

    clinics_df = pd.read_csv("clinics.csv")
    nodes_df, edges_df = snap_clinics_and_hubs(nodes_df, edges_df, clinics_df)

    nodes_df.to_csv("roads_nodes.csv", index=False)
    edges_df.to_csv("roads_edges.csv", index=False)
    print(f"\nFinal graph: {len(nodes_df)} nodes, {len(edges_df)} edges")
    print("Wrote roads_nodes.csv, roads_edges.csv -- REAL road geometry from OSM, "
          "real clinic/hub locations. base_disruption_risk is still a placeholder "
          "by road class (see BASE_RISK_BY_TYPE) -- no open dataset publishes real "
          "conflict/flood risk per road segment.")


if __name__ == "__main__":
    main()
