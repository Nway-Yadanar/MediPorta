"""
multi_clinic.py

Feature 1: On-the-way multi-clinic routing (corridor insertion, NOT TSP).

Given a base trip Warehouse -> primary destination -> Warehouse, we greedily
insert additional clinics that lie ALONG the corridor, accepting an insertion
only if it adds less than DETOUR_BUDGET_HR of extra cost. This is polynomial
(O(candidates x route_cost)) and scales to hundreds of clinics, unlike optimal
multi-stop ordering (factorial TSP).

Also provides the cold-chain / payload feasibility check (Feature 4): a route
is only feasible for a payload if its cumulative time stays within the item's
max_transit_hours viability window.
"""

from app.graph_engine import route

DETOUR_BUDGET_HR = 1.5   # max extra cost we'll accept to add an on-the-way clinic


def plan_multi_clinic_route(
    G, hub, primary_target, candidate_clinics, clinics_scored,
    risk_weight=1.0, equity_weight=1.0, max_stops=6,
):
    """
    Build an on-the-way milk-run: hub -> [inserted clinics...] -> primary_target.

    candidate_clinics: list of clinic_ids to consider inserting.
    Returns dict with ordered stops, per-leg costs, and total.
    """
    stops = [hub, primary_target]

    def leg_cost(a, b):
        _, cost, dist = route(G, a, b, clinics_scored, risk_weight, equity_weight)
        return cost, dist

    # current total for hub->target
    base_cost, base_dist = leg_cost(hub, primary_target)
    total_cost, total_dist = base_cost, base_dist

    remaining = list(candidate_clinics)

    while len(stops) - 1 < max_stops and remaining:
        best = None  # (added_cost, insert_index, clinic, new_leg_costs)
        for clinic in remaining:
            for i in range(len(stops) - 1):
                a, b = stops[i], stops[i + 1]
                # cost of a->b currently
                cur, _ = leg_cost(a, b)
                # cost of a->clinic->b
                c1, d1 = leg_cost(a, clinic)
                c2, d2 = leg_cost(clinic, b)
                added = (c1 + c2) - cur
                if added <= DETOUR_BUDGET_HR and (best is None or added < best[0]):
                    best = (added, i + 1, clinic, (c1, c2, d1, d2, cur))
        if best is None:
            break
        added, idx, clinic, _ = best
        stops.insert(idx, clinic)
        remaining.remove(clinic)
        total_cost += added

    # recompute clean totals along final ordered stops
    legs = []
    total_cost, total_dist = 0.0, 0.0
    for a, b in zip(stops, stops[1:]):
        path, cost, dist = route(G, a, b, clinics_scored, risk_weight, equity_weight)
        legs.append({"from": a, "to": b, "cost_hr": cost, "dist_km": dist, "path": path})
        total_cost += cost
        total_dist += dist

    return {
        "stops": stops,
        "legs": legs,
        "total_cost_hr": round(total_cost, 3),
        "total_distance_km": round(total_dist, 2),
        "n_clinics_served": len(stops) - 1,
    }


def is_payload_feasible(route_time_hr, payload_row, has_cold_chain_transport=True):
    """
    Feature 4 constraint: does this route deliver the payload within its
    viability window?

    payload_row: a dict/Series from medical_payloads.csv with
                 cold_chain (bool-ish) and max_transit_hours.
    has_cold_chain_transport: whether the vehicle/boat can hold 2-8C on this route.

    Returns (feasible: bool, reason: str).
    """
    try:
        max_hr = float(payload_row["max_transit_hours"])
    except (ValueError, TypeError):
        max_hr = 48.0 if str(payload_row.get("cold_chain")).upper() == "TRUE" else 720.0
    needs_cold = str(payload_row["cold_chain"]).upper() == "TRUE"

    if route_time_hr > max_hr:
        return False, (
            f"transit {route_time_hr:.1f}h exceeds {payload_row['item_id']} "
            f"viability window {max_hr:.0f}h"
        )
    if needs_cold and not has_cold_chain_transport:
        return False, (
            f"{payload_row['item_id']} requires 2-8C cold chain not maintainable "
            f"on this route segment"
        )
    return True, "within viability window"
