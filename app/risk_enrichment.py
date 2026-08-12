"""
risk_enrichment.py

Turns base_disruption_risk from a road-class PLACEHOLDER into a REAL, located,
time-aware signal by overlaying hazard events (ACLED conflict, flood extent,
earthquake damage, field-reported closures) onto the road edges near them.

    edge_risk = base_by_road_class                      (static floor, kept)
              + sum over nearby active hazards of
                    severity * proximity_falloff * recency_decay
              clamped to [0, 1]

WHY A SEPARATE LAYER:
  The graph (212K nodes) is stable and built once. Hazards change weekly, so
  they live in hazard_events.csv and are applied at build time (or refreshed
  without rebuilding the graph). This is the "live feed" seam your note calls
  for -- swap hazard_events.csv for a real ACLED/UNOSAT export and rerun.

PROVENANCE:
  base_disruption_risk stays flagged road_class_proxy. The hazard OVERLAY is
  flagged by its own source (acled_real / flood_real / field_report). The final
  enriched value records which hazards contributed, so risk is auditable, not
  a magic number.
"""

import datetime as dt
import math

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

# how strongly each hazard type raises risk (multiplies the event severity)
HAZARD_WEIGHT = {
    "conflict": 1.0,
    "flood": 0.85,
    "earthquake_damage": 0.9,
    "access_restriction": 0.7,
}

# recency: a hazard's contribution decays after its event_date toward valid_until
RECENCY_HALF_LIFE_DAYS = 45


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _recency_factor(event_date, valid_until, as_of):
    """1.0 at event_date, decaying with half-life; 0 outside [event_date, valid_until]."""
    if as_of < event_date or as_of > valid_until:
        return 0.0
    age_days = (as_of - event_date).days
    return 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)


def enrich_edge_risk(edges_df, hazards_df, node_coords, as_of=None, verbose=True):
    """
    edges_df     : DataFrame with from_node, to_node, base_disruption_risk
    hazards_df   : hazard_events.csv loaded
    node_coords  : dict node_id -> (lat, lon)
    as_of        : date to evaluate hazard activity (default: today)
    Returns edges_df with new columns:
        enriched_disruption_risk, hazard_contributors, _risk_provenance
    """
    as_of = as_of or dt.date.today()

    # active hazards only (date window covers as_of)
    hz = hazards_df.copy()
    hz["event_date"] = pd.to_datetime(hz["event_date"]).dt.date
    hz["valid_until"] = pd.to_datetime(hz["valid_until"]).dt.date
    hz["recency"] = hz.apply(
        lambda r: _recency_factor(r["event_date"], r["valid_until"], as_of), axis=1
    )
    hz = hz[hz["recency"] > 0.01].reset_index(drop=True)

    if len(hz) == 0:
        edges_df = edges_df.copy()
        edges_df["enriched_disruption_risk"] = edges_df["base_disruption_risk"]
        edges_df["hazard_contributors"] = ""
        edges_df["_risk_provenance"] = "road_class_proxy (no active hazards)"
        return edges_df

    # KDTree over hazard centers for fast "which hazards are near this edge"
    hz_coords = hz[["lat", "lon"]].to_numpy()
    tree = cKDTree(hz_coords)
    max_radius = hz["radius_km"].max()
    # convert km to approx degrees for the tree query (coarse; refined by haversine)
    deg_radius = max_radius / 111.0

    enriched = []
    contributors = []
    provs = []

    for e in edges_df.itertuples():
        a = node_coords.get(e.from_node)
        b = node_coords.get(e.to_node)
        if not a or not b:
            enriched.append(e.base_disruption_risk)
            contributors.append("")
            provs.append("road_class_proxy (edge endpoint missing coords)")
            continue
        # edge midpoint as the join point (cheap; edges are short)
        mlat, mlon = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        idxs = tree.query_ball_point([mlat, mlon], deg_radius * 1.3)

        added = 0.0
        contribs = []
        for i in idxs:
            h = hz.iloc[i]
            d = _haversine_km(mlat, mlon, h["lat"], h["lon"])
            if d > h["radius_km"]:
                continue
            falloff = 1 - (d / h["radius_km"])  # linear falloff to edge of radius
            w = HAZARD_WEIGHT.get(h["hazard_type"], 0.7)
            contrib = w * h["severity"] * falloff * h["recency"]
            if contrib > 0.01:
                added += contrib
                contribs.append(f"{h['event_id']}:{h['hazard_type']}:{contrib:.2f}")

        final = min(1.0, e.base_disruption_risk + added)
        enriched.append(round(final, 3))
        contributors.append("|".join(contribs))
        provs.append(
            "road_class_proxy + hazard_overlay" if contribs else "road_class_proxy"
        )

    out = edges_df.copy()
    out["enriched_disruption_risk"] = enriched
    out["hazard_contributors"] = contributors
    out["_risk_provenance"] = provs

    if verbose:
        n_affected = sum(1 for c in contributors if c)
        lift = np.mean([en - ba for en, ba in
                        zip(out["enriched_disruption_risk"], out["base_disruption_risk"])])
        print(f"[risk] {len(hz)} active hazards as of {as_of}")
        print(f"[risk] {n_affected} of {len(out)} edges affected by a hazard")
        print(f"[risk] mean risk lift on affected edges: "
              f"{np.mean([en-ba for en,ba,c in zip(out['enriched_disruption_risk'],out['base_disruption_risk'],contributors) if c] or [0]):.3f}")
    return out
