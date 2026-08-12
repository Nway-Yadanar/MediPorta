"""
generate_demand_data.py

Generates clinic_demand.csv from two real-keyed inputs:
  - clinics.csv          (real MIMU clinics, CL-0001..CL-0306)
  - medical_payloads.csv (item catalog, disease-priority real / logistics proxy)

Design (see project design spec):
  * Long format: one row per (clinic_id, item_id) pair.
  * weekly_consumption is REGION- and CASELOAD-informed, not pure noise:
    each item maps to a disease; clinics in a region where that disease is
    prioritized get higher baseline consumption, scaled by population_served.
  * Derived fields (days_of_stock_remaining, days_to_expiry, stockout_flag,
    expiry_risk_flag, priority_score) are COMPUTED here so they never drift.
  * priority_score blends urgency x item-criticality x clinic-vulnerability.

PROVENANCE: clinic_id / item_id / region->disease weighting are grounded.
All per-clinic stock, consumption, and expiry numbers are proxy_synthetic —
no open per-clinic inventory feed exists for Myanmar. Flagged accordingly.

Usage:
    python generate_demand_data.py
"""

import csv
import datetime as dt
import numpy as np
import pandas as pd

from vulnerability_bridge import get_clinic_vulnerability  # local helper below

TODAY = dt.date(2026, 8, 10)

STOCKOUT_THRESHOLD_DAYS = 5      # below this days-of-stock -> stockout_flag
EXPIRY_THRESHOLD_DAYS = 30       # below this days-to-expiry -> expiry_risk_flag

# priority_score weights (exposed so they can be defended / tuned)
W_URGENCY = 0.50
W_CRITICALITY = 0.30
W_VULNERABILITY = 0.20

# Per-item life-criticality weight (0-1). Higher = more life-critical.
# Grounded in clinical urgency: antivenom/oxytocin/OPV are time-critical;
# ORS/RDTs are important but more substitutable / less immediately fatal.
CRITICALITY = {
    "MED_ANTIVENOM": 1.00,
    "MED_OXYTOCIN": 0.95,
    "VAC_OPV": 0.90,
    "VAC_MEASLES": 0.85,
    "MED_ACT": 0.85,
    "VAC_OCV": 0.80,
    "MED_CHOLERA_KIT": 0.80,
    "VAC_PENTA": 0.78,
    "MED_DENGUE_SUP": 0.75,
    "VAC_TT": 0.70,
    "MED_ORS": 0.65,
    "MED_RDT_MAL": 0.60,
    "MED_RDT_DEN": 0.55,
}

# Regional disease weighting. Higher weight -> that item is more in-demand there.
# Grounded in WHO/Health Cluster burden: Rakhine heavier malaria/dengue/cholera;
# Sagaing heavier cholera/AWD + EPI vaccine catch-up; Mandalay (rural) mixed.
REGION_ITEM_WEIGHT = {
    "Rakhine": {
        "MED_ACT": 1.4, "MED_RDT_MAL": 1.4, "MED_DENGUE_SUP": 1.5, "MED_RDT_DEN": 1.5,
        "MED_ORS": 1.2, "MED_CHOLERA_KIT": 1.2, "VAC_OCV": 1.2,
        "VAC_MEASLES": 1.0, "VAC_OPV": 1.0, "VAC_PENTA": 1.0, "VAC_TT": 1.0,
        "MED_ANTIVENOM": 1.1, "MED_OXYTOCIN": 1.1,
    },
    "Sagaing": {
        "MED_ACT": 1.1, "MED_RDT_MAL": 1.1, "MED_DENGUE_SUP": 1.0, "MED_RDT_DEN": 1.0,
        "MED_ORS": 1.4, "MED_CHOLERA_KIT": 1.4, "VAC_OCV": 1.3,
        "VAC_MEASLES": 1.4, "VAC_OPV": 1.4, "VAC_PENTA": 1.4, "VAC_TT": 1.2,
        "MED_ANTIVENOM": 1.2, "MED_OXYTOCIN": 1.1,
    },
    "Mandalay": {
        "MED_ACT": 1.0, "MED_RDT_MAL": 1.0, "MED_DENGUE_SUP": 1.1, "MED_RDT_DEN": 1.1,
        "MED_ORS": 1.1, "MED_CHOLERA_KIT": 1.0, "VAC_OCV": 1.0,
        "VAC_MEASLES": 1.1, "VAC_OPV": 1.1, "VAC_PENTA": 1.1, "VAC_TT": 1.0,
        "MED_ANTIVENOM": 1.0, "MED_OXYTOCIN": 1.0,
    },
}

# How many distinct items each clinic stocks (drawn per clinic).
ITEMS_PER_CLINIC_RANGE = (4, 9)

# Clinics to force into a demo-worthy stockout scenario (real IDs from clinics.csv).
# CL-0002 = Min Kun Station Hospital (Sagaing) -> cold-chain vaccine scenario clinic.
DEMO_STOCKOUT_CLINICS = {"CL-0002", "CL-0006", "CL-0290"}


def region_of(state_region: str) -> str:
    return state_region if state_region in REGION_ITEM_WEIGHT else "Mandalay"


def main():
    clinics = pd.read_csv("clinics.csv")
    payloads = pd.read_csv("medical_payloads.csv")
    item_ids = payloads["item_id"].tolist()
    item_disease = dict(zip(payloads["item_id"], payloads["disease_target"]))
    shelf_life = dict(zip(payloads["item_id"], payloads["shelf_life_days"]))

    vuln = get_clinic_vulnerability(clinics)  # clinic_id -> 0..1

    rng = np.random.default_rng(20260810)
    rows = []

    # pick the ~15 demo-subset clinics: the forced-stockout ones + a spread of others
    demo_extra = set(
        clinics.sort_values("population_served", ascending=False)
        .head(12)["clinic_id"].tolist()
    )
    demo_subset_ids = DEMO_STOCKOUT_CLINICS | demo_extra

    for c in clinics.itertuples():
        region = region_of(c.state_region)
        weights = REGION_ITEM_WEIGHT[region]

        # select which items this clinic stocks, biased by regional weight
        n_items = rng.integers(*ITEMS_PER_CLINIC_RANGE)
        w = np.array([weights[i] for i in item_ids], dtype=float)
        w = w / w.sum()
        chosen = rng.choice(item_ids, size=min(n_items, len(item_ids)), replace=False, p=w)

        force_stockout = c.clinic_id in DEMO_STOCKOUT_CLINICS

        for item in chosen:
            base = weights[item]
            pop_factor = max(0.3, min(3.0, c.population_served / 800.0))
            weekly = int(round(rng.uniform(8, 30) * base * pop_factor))
            weekly = max(weekly, 3)

            if force_stockout:
                stock = int(rng.integers(0, weekly // 2 + 1))  # < ~3.5 days
            else:
                # most clinics healthy-ish; some naturally low
                days_target = rng.uniform(1.5, 35)
                stock = int(round(weekly / 7 * days_target))

            days_remaining = round(stock / (weekly / 7), 1) if weekly else 999.0

            # expiry: within shelf life; demo-stockout vaccines skew near-term
            sl = int(shelf_life[item])
            if force_stockout and item.startswith("VAC_"):
                days_to_expiry = int(rng.integers(10, 40))
            else:
                days_to_expiry = int(rng.integers(45, min(sl, 900)))
            expiry = TODAY + dt.timedelta(days=days_to_expiry)

            stockout = days_remaining < STOCKOUT_THRESHOLD_DAYS
            expiry_risk = days_to_expiry < EXPIRY_THRESHOLD_DAYS

            urgency = max(0.0, 1 - days_remaining / 30.0)
            crit = CRITICALITY.get(item, 0.6)
            v = vuln.get(c.clinic_id, 0.3)
            priority = round(
                W_URGENCY * urgency + W_CRITICALITY * crit + W_VULNERABILITY * v, 3
            )

            rows.append({
                "clinic_id": c.clinic_id,
                "item_id": item,
                "current_stock_units": stock,
                "weekly_consumption": weekly,
                "days_of_stock_remaining": days_remaining,
                "nearest_expiry_date": expiry.isoformat(),
                "days_to_expiry": days_to_expiry,
                "stockout_flag": stockout,
                "expiry_risk_flag": expiry_risk,
                "priority_score": priority,
                "demo_subset": c.clinic_id in demo_subset_ids,
                "_data_provenance": "proxy_synthetic",
            })

    out = pd.DataFrame(rows)
    out = out.sort_values(["priority_score"], ascending=False).reset_index(drop=True)
    out.to_csv("clinic_demand.csv", index=False)

    n_stockout = out["stockout_flag"].sum()
    n_expiry = out["expiry_risk_flag"].sum()
    print(f"Wrote clinic_demand.csv: {len(out)} rows across {out.clinic_id.nunique()} clinics")
    print(f"  stockout rows: {n_stockout}   expiry-risk rows: {n_expiry}")
    print(f"  demo_subset clinics: {out[out.demo_subset].clinic_id.nunique()}")
    print("\nTop 8 priority demand rows:")
    print(out.head(8)[[
        "clinic_id", "item_id", "days_of_stock_remaining",
        "days_to_expiry", "stockout_flag", "expiry_risk_flag", "priority_score"
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
