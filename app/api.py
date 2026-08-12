"""
api.py — MediRoute hybrid backend.

Loads the 212K-node graph ONCE at startup (the only heavy operation) and keeps
it warm in memory. Serves:

  GET  /regions                  -> region configs + hubs (for the UI switcher)
  GET  /precomputed/{region}/{hub}   -> instant pre-baked scenario (demo-safe)
  GET  /triage?region=&hub=      -> telecom-boosted priority queue
  POST /route                    -> LIVE route from any origin to any clinic
                                     (proves it's really computing, not faked)
  GET  /health                   -> readiness

Design: the demo-critical money-shots are pre-computed (cannot fail); the live
endpoint is the "it's real" proof and is never on the demo-critical path.

Run:
    uvicorn app.api:app --host 0.0.0.0 --port 8000
"""

import json
import os
import sys

import networkx as nx
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.vulnerability import compute_vulnerability_scores
from app.graph_engine import build_graph, route
from app.water_routes import add_water_layer
from app.regions import REGIONS, default_hub

DATA = os.path.join(ROOT, "data")
PRECOMP = os.path.join(ROOT, "demo_data", "precomputed")

app = FastAPI(title="MediRoute API", version="1.0")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

STATE = {}  # holds graph, scored clinics, lookups — warm in memory


@app.on_event("startup")
def load_everything():
    clinics = pd.read_csv(os.path.join(DATA, "clinics.csv"))
    nodes = pd.read_csv(os.path.join(DATA, "roads_nodes.csv"))
    edges = pd.read_csv(os.path.join(DATA, "roads_edges.csv"))
    scored = compute_vulnerability_scores(clinics)
    G = build_graph(nodes, edges, scored)

    # add ALL regions' water layers (each region's waterways live in the same graph)
    water_clinics = set()
    for rname, cfg in REGIONS.items():
        if cfg["waterways"]:
            try:
                _, wc = add_water_layer(
                    G,
                    os.path.join(DATA, cfg["waterways"]),
                    os.path.join(DATA, cfg["docks"]),
                    clinics,
                )
                water_clinics |= wc
            except FileNotFoundError:
                pass

    STATE["G"] = G
    STATE["scored"] = scored
    STATE["clinics"] = clinics
    STATE["clinic_names"] = dict(zip(clinics["clinic_id"], clinics["clinic_name"]))
    STATE["clinic_coords"] = {
        r.clinic_id: (r.latitude, r.longitude) for r in clinics.itertuples()
    }
    STATE["water_clinics"] = water_clinics
    STATE["ready"] = True
    print(f"[api] warm: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, "
          f"{len(water_clinics)} near-water clinics")


@app.get("/health")
def health():
    return {"ready": STATE.get("ready", False),
            "nodes": STATE["G"].number_of_nodes() if STATE.get("ready") else 0}


@app.get("/regions")
def regions():
    return REGIONS


@app.get("/precomputed/{region}/{hub}")
def precomputed(region: str, hub: str):
    path = os.path.join(PRECOMP, f"{region}__{hub}.json")
    if not os.path.exists(path):
        raise HTTPException(404, f"no precomputed scenario for {region}/{hub}")
    with open(path) as f:
        return json.load(f)


class RouteReq(BaseModel):
    origin: str          # any node id (hub or clinic)
    target: str          # any clinic id
    risk_weight: float = 1.0
    equity_weight: float = 1.0


@app.post("/route")
def live_route(req: RouteReq):
    """LIVE computation on the warm graph — the 'it's really working' endpoint."""
    if not STATE.get("ready"):
        raise HTTPException(503, "graph still loading")
    G, scored = STATE["G"], STATE["scored"]
    if req.origin not in G or req.target not in G:
        raise HTTPException(404, "origin or target not in graph")
    try:
        path, cost, dist = route(
            G, req.origin, req.target, scored,
            req.risk_weight, req.equity_weight,
        )
    except nx.NetworkXNoPath:
        raise HTTPException(422, "no path between origin and target")

    # collapse to named waypoints + coords for the map
    names = STATE["clinic_names"]
    wp = []
    for i, n in enumerate(path):
        d = G.nodes[n]
        nt = d.get("node_type", "road_vertex")
        mode = "road"
        if i > 0:
            ed = G.get_edge_data(path[i - 1], n) or {}
            mode = ed.get("mode", "road")
        if nt in ("clinic", "dock", "township_hub") or "HUB" in str(n):
            wp.append({"id": n, "name": names.get(n, n), "type": nt,
                       "mode_in": mode, "lat": d.get("lat"), "lon": d.get("lon")})
    # full polyline (every vertex) for smooth map drawing
    line = [[G.nodes[n]["lat"], G.nodes[n]["lon"]] for n in path
            if G.nodes[n].get("lat") is not None]
    return {"origin": req.origin, "target": req.target,
            "cost_hours": cost, "distance_km": dist,
            "waypoints": wp, "polyline": line, "live": True}


# serve the frontend at /
FE = os.path.join(ROOT, "demo_data")
if os.path.isdir(FE):
    app.mount("/", StaticFiles(directory=FE, html=True), name="frontend")
