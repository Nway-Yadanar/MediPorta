"""
accessibility.py

Feature 2: Road accessibility classification.

Assigns every clinic one of three statuses:
  - road_accessible      : reachable by truck under normal conditions
  - partially_accessible : truck reaches a nearby transfer point, but the last
                           leg needs a boat (near water) or is seasonally cut
  - road_inaccessible    : no viable truck path under the current scenario
                           (e.g. bridge blocked) -> needs multi-modal routing

Classification blends:
  * road_access_flag from clinics.csv (all_weather / seasonal / conflict_restricted)  [REAL-signal proxy]
  * graph reachability from the dispatch hub (does a road path exist at all?)
  * proximity to a waterway (is a boat fallback even possible?)             [synthetic geometry]

PROVENANCE: road_access_flag is a rurality-informed proxy; water proximity is
derived from hand-drawn waterways (synthetic). Statuses are decision labels
computed from those inputs, and are flagged proxy where the inputs are.
"""

import networkx as nx
import pandas as pd

ROAD_ACCESSIBLE = "road_accessible"
PARTIAL = "partially_accessible"
ROAD_INACCESSIBLE = "road_inaccessible"


def classify_accessibility(
    G: nx.Graph,
    clinics_scored: pd.DataFrame,
    hub_node: str,
    water_clinic_ids: set = None,
    blocked_edges: set = None,
) -> pd.DataFrame:
    """
    Returns clinics_scored with added columns:
      access_status, road_reachable, near_water, _access_provenance

    blocked_edges: optional set of frozenset({u,v}) edges to treat as cut
    (the monsoon / bridge-blockage scenario). Reachability is recomputed with
    those edges removed.
    """
    water_clinic_ids = water_clinic_ids or set()
    blocked_edges = blocked_edges or set()

    
    if blocked_edges:
        H = G.copy()
        for e in blocked_edges:
            u, v = tuple(e)
            if H.has_edge(u, v):
                H.remove_edge(u, v)
    else:
        H = G

    
    reachable = set(nx.node_connected_component(H, hub_node)) if hub_node in H else set()

    df = clinics_scored.copy()
    statuses, road_reach, near_water = [], [], []

    for c in df.itertuples():
        cid = c.clinic_id
        is_reachable = cid in reachable
        is_near_water = cid in water_clinic_ids
        flag = getattr(c, "road_access_flag", "all_weather")

        road_reach.append(is_reachable)
        near_water.append(is_near_water)

        if not is_reachable:
            
            statuses.append(PARTIAL if is_near_water else ROAD_INACCESSIBLE)
        elif flag == "conflict_restricted":
            
            statuses.append(PARTIAL if is_near_water else ROAD_ACCESSIBLE)
        else:
            statuses.append(ROAD_ACCESSIBLE)

    df["access_status"] = statuses
    df["road_reachable"] = road_reach
    df["near_water"] = near_water
    df["_access_provenance"] = (
        "status computed from road_access_flag (rurality proxy) + graph "
        "reachability (real topology) + water proximity (synthetic geometry)"
    )
    return df


def accessibility_summary(df: pd.DataFrame) -> dict:
    return df["access_status"].value_counts().to_dict()
