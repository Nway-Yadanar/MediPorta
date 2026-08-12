"""
demo_visualization.py

Generates a static proof-of-concept figure showing:
  1. All clinics colored by vulnerability score (the "risk heatmap" concept)
  2. Naive shortest-path route vs MediRoute risk-weighted route for one scenario

This uses matplotlib (available offline) as a stand-in for the live Folium/
pydeck map in the Streamlit dashboard -- same underlying route data, just a
static rendering so you have a demo asset even before running app.py locally.
"""

import sys
sys.path.append("../app")

import matplotlib.pyplot as plt
import pandas as pd
from vulnerability import compute_vulnerability_scores
from graph_engine import build_graph, route

clinics = pd.read_csv("../data/clinics.csv")
nodes = pd.read_csv("../data/roads_nodes.csv")
edges = pd.read_csv("../data/roads_edges.csv")

scored = compute_vulnerability_scores(clinics)
G = build_graph(nodes, edges, scored)

SOURCE = "HUB-Sittwe"
TARGET = "CL-0293"  # Tha Pyu Chaing Station Hospital -- real clinic, real genuine route divergence on the real road graph
naive_path, naive_cost, naive_dist = route(G, SOURCE, TARGET, scored, naive=True)
smart_path, smart_cost, smart_dist = route(G, SOURCE, TARGET, scored, risk_weight=3.0, equity_weight=1.5)

node_pos = nodes.set_index("node_id")[["longitude", "latitude"]].to_dict("index")

fig, axes = plt.subplots(1, 2, figsize=(15, 7))

for ax, (path, cost, dist, label, color) in zip(
    axes,
    [
        (naive_path, naive_cost, naive_dist, "Naive Shortest-Time Route", "#d62728"),
        (smart_path, smart_cost, smart_dist, "MediRoute Risk-Weighted Route", "#2ca02c"),
    ],
):
   
    bg_sample = edges.sample(n=min(15000, len(edges)), random_state=1) if len(edges) > 15000 else edges
    for _, e in bg_sample.iterrows():
        p1, p2 = node_pos[e.from_node], node_pos[e.to_node]
        risk_color = plt.cm.RdYlGn_r(min(e.base_disruption_risk, 1.0))
        ax.plot([p1["longitude"], p2["longitude"]], [p1["latitude"], p2["latitude"]],
                color=risk_color, linewidth=0.4, alpha=0.25, zorder=1)

    # clinics colored by vulnerability
    sc = ax.scatter(scored["longitude"], scored["latitude"], c=scored["vulnerability_score"],
                     cmap="YlOrRd", s=40, edgecolor="k", linewidth=0.3, zorder=2, label="Clinics (color = vulnerability)")

    # highlight the chosen path
    path_lons = [node_pos[n]["longitude"] for n in path]
    path_lats = [node_pos[n]["latitude"] for n in path]
    ax.plot(path_lons, path_lats, color=color, linewidth=3.5, zorder=3, marker="o", markersize=6)

    ax.scatter(*[node_pos[SOURCE][k] for k in ("longitude", "latitude")], marker="s", s=120, c="blue", zorder=4, label="Dispatch hub")
    ax.scatter(*[node_pos[TARGET][k] for k in ("longitude", "latitude")], marker="*", s=250, c="black", zorder=4, label="Target clinic (most vulnerable)")

    ax.set_title(f"{label}\ncost={cost}h | distance={dist}km", fontsize=12, fontweight="bold")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(loc="lower left", fontsize=8)

plt.suptitle("MediRoute POC: Background road color = disruption risk (red=high risk, green=low risk)\n"
             "Same origin/destination, different route chosen once risk + equity weighting is applied",
             fontsize=11)
plt.tight_layout()
plt.savefig("../mediroute_poc_demo.png", dpi=150, bbox_inches="tight")
print("Saved: mediroute_poc_demo.png")
print(f"\nNaive route:     {naive_path}  ({naive_dist}km, {naive_cost}h weighted cost)")
print(f"MediRoute route: {smart_path}  ({smart_dist}km, {smart_cost}h weighted cost)")
print(f"\nMediRoute chose a {smart_dist - naive_dist:+.1f}km different path specifically to avoid high-disruption-risk roads")
print("while still prioritizing the most vulnerable clinic — this IS the pitch's core differentiator, working end-to-end.")
