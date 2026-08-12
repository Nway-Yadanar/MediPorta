"""
load_real_roads.py

Converts a real road network (OSMnx pull, or a downloaded OSM/MIMU roads file)
into a NetworkX graph, and also exports roads_nodes.csv / roads_edges.csv in
the same schema graph_engine.py expects — so nothing downstream needs to change.

Two paths, pick whichever fits what you downloaded:

  PATH A (recommended): pull live via OSMnx directly, no download needed
      python load_real_roads.py --mode osmnx

  PATH B: use a file you already downloaded (MIMU shapefile/geojson or
  HOTOSM roads geojson)
      python load_real_roads.py --mode file --path real/roads.geojson

Requires: osmnx, geopandas, networkx, shapely
    pip install osmnx geopandas shapely networkx
"""

import argparse
import networkx as nx
import pandas as pd


def load_via_osmnx(place: str = "Rakhine State, Myanmar"):
    """
    Pulls the real, current road network directly from OpenStreetMap.
    Needs internet access (works fine on your local machine / most CI runners,
    just not in this offline sandbox).
    """
    import osmnx as ox

    print(f"Pulling live road network for '{place}' via OSMnx...")
    try:
        G = ox.graph_from_place(place, network_type="drive")
    except Exception as e:
        print(f"graph_from_place failed ({e}); falling back to bounding box.")
        # Rakhine + Sagaing rough bbox fallback
        G = ox.graph_from_bbox(bbox=(26.5, 15.5, 97.5, 92.0), network_type="drive")

    G = ox.project_graph(G, to_crs="EPSG:4326")  # keep lat/lon for our schema
    return G


def load_via_file(path: str):
    """
    Loads a downloaded roads file (GeoJSON/shapefile of LineStrings) and builds
    a routable graph from it using OSMnx's graph-from-geodataframe utilities.
    """
    import osmnx as ox
    import geopandas as gpd

    gdf = gpd.read_file(path)
    gdf = gdf[gdf.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    print(f"Loaded {len(gdf)} road segments from {path}")

    G = ox.graph_from_gdfs(
        gdf_nodes=None,  # let osmnx derive nodes from the edge geometries
        gdf_edges=gdf,
    ) if hasattr(ox, "graph_from_gdfs") else None

    if G is None:
        raise RuntimeError(
            "Your OSMnx version doesn't support graph_from_gdfs with edges-only input. "
            "Easiest fix: use --mode osmnx to pull the network directly instead."
        )
    return G


def osmnx_graph_to_mediroute_schema(G) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Converts an OSMnx MultiDiGraph into roads_nodes.csv / roads_edges.csv format
    matching what graph_engine.build_graph() expects.
    """
    nodes = []
    for node_id, data in G.nodes(data=True):
        nodes.append({
            "node_id": f"N-{node_id}",
            "node_type": "road_junction",
            "latitude": data.get("y"),
            "longitude": data.get("x"),
        })
    nodes_df = pd.DataFrame(nodes).drop_duplicates(subset="node_id")

    edges = []
    seen = set()
    for u, v, data in G.edges(data=True):
        pair = tuple(sorted((u, v)))
        if pair in seen:
            continue
        seen.add(pair)

        length_m = data.get("length", 0)
        highway = data.get("highway", "unclassified")
        if isinstance(highway, list):
            highway = highway[0]

        road_type_map = {
            "motorway": "primary", "trunk": "primary", "primary": "primary",
            "secondary": "secondary", "tertiary": "tertiary",
            "unclassified": "track", "residential": "tertiary", "track": "track",
        }
        road_type = road_type_map.get(highway, "track")

        edges.append({
            "from_node": f"N-{u}", "to_node": f"N-{v}",
            "distance_km": round(length_m / 1000, 3),
            "road_type": road_type,
            # OSM doesn't carry a disruption-risk field — this is the layer you enrich
            # with ACLED conflict data or a flood/monsoon layer for the real pipeline.
            # Default placeholder: rougher road types get a higher baseline.
            "base_disruption_risk": {"primary": 0.1, "secondary": 0.2, "tertiary": 0.35, "track": 0.5}[road_type],
        })
    edges_df = pd.DataFrame(edges)

    return nodes_df, edges_df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["osmnx", "file"], default="osmnx")
    parser.add_argument("--path", default="real/roads.geojson")
    parser.add_argument("--place", default="Rakhine State, Myanmar")
    args = parser.parse_args()

    G = load_via_osmnx(args.place) if args.mode == "osmnx" else load_via_file(args.path)

    print(f"Graph loaded: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    nodes_df, edges_df = osmnx_graph_to_mediroute_schema(G)
    nodes_df.to_csv("roads_nodes.csv", index=False)
    edges_df.to_csv("roads_edges.csv", index=False)
    print(f"Wrote roads_nodes.csv ({len(nodes_df)} rows) and roads_edges.csv ({len(edges_df)} rows)")
    print("NOTE: base_disruption_risk is a placeholder by road type — enrich with real "
          "conflict/flood data for the actual risk-weighting to mean something.")


if __name__ == "__main__":
    main()
