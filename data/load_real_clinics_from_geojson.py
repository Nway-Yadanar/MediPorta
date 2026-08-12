"""
load_real_clinics_from_geojson.py

Parses the real MIMU health facilities GeoJSON (WFS export) directly with the
stdlib json module + pandas -- no geopandas dependency needed, since this is
plain Point geometry.

Usage:
    python load_real_clinics_from_geojson.py path/to/Hospitals.geojson

Filters to Rakhine + Sagaing by default (edit TARGET_REGIONS to change).
Writes clinics.csv in MediRoute's schema, with health/operational fields
clearly flagged as placeholders (see REAL_DATA_SOURCES.md for why).
"""

import json
import sys
import numpy as np
import pandas as pd

TARGET_REGIONS = ["Rakhine", "Sagaing", "Mandalay"]

# Mandalay Region mixes a dense urban core with genuinely rural, underserved
# townships. Since the ask is specifically "Mandalay rural areas, least medical
# access", exclude the urban core townships (large city hospitals, 500-1500 beds)
# and keep everything else -- the small Station-level facilities (16-50 beds)
# that represent real rural/hard-to-reach access gaps.
MANDALAY_URBAN_CORE_EXCLUDE = {"Chanayethazan", "Chanmyathazi", "Aungmyaythazan", "Mahaaungmyay"}


def load_mimu_geojson(path: str) -> pd.DataFrame:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for feat in data["features"]:
        props = feat["properties"]
        lon, lat = feat["geometry"]["coordinates"]
        rows.append({
            "raw_id": props.get("id_healthF"),
            "clinic_name": props.get("nmHsp_eng"),
            "clinic_name_mya": props.get("nmHsp_mya"),
            "facility_level": props.get("lvlHsp_eng"),
            "bed_class": props.get("bedClass"),
            "state_region_pcode": props.get("SR_PCODE"),
            "state_region": props.get("SR"),
            "district_pcode": props.get("DT_PCODE"),
            "district": props.get("DT"),
            "township_pcode": props.get("TS_PCODE"),
            "township": props.get("TS_en"),
            "confidence": props.get("accuraConf"),
            "latitude": lat,
            "longitude": lon,
        })
    return pd.DataFrame(rows)


def add_placeholder_operational_fields(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """
    Real dataset gives us real locations + facility level/bed class. It does NOT
    give live stock levels or DHS-style access rates at facility level (nobody
    publishes that as open data). Fill clearly-flagged placeholders so the
    pipeline runs end-to-end; replace with real reporting data when available.

    These placeholders are NOT pure random noise -- they're centered using the
    real bed_class/facility_level signal (smaller facility = more rural = worse
    baseline access, on average, in real Myanmar health system patterns), then
    given per-clinic random variation on top. This is still a placeholder (not
    real DHS/MICS data), but a defensible, real-signal-informed one rather than
    an arbitrary guess.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    df = df.copy()

    bed_numeric = pd.to_numeric(df["bed_class"], errors="coerce").fillna(16)
    # Bed class gives a REAL signal we can use directly for population_served
    df["population_served"] = (bed_numeric * rng.uniform(15, 40, n)).round().astype(int)

    # Rurality proxy from real bed_class: smaller facility -> lower baseline access rates
    rurality = 1 - np.clip(bed_numeric / bed_numeric.max(), 0, 1)  # 0=largest facility, 1=smallest
    df["institutional_delivery_rate"] = np.clip(
        rng.normal(0.40 - 0.22 * rurality, 0.06, n), 0.05, 0.60
    ).round(3)  # PLACEHOLDER, rurality-informed
    df["skilled_birth_attendance_rate"] = np.clip(
        rng.normal(0.35 - 0.20 * rurality, 0.06, n), 0.05, 0.55
    ).round(3)  # PLACEHOLDER, rurality-informed
    df["full_vaccination_rate"] = np.clip(
        rng.normal(0.80 - 0.30 * rurality, 0.07, n), 0.30, 0.90
    ).round(3)  # PLACEHOLDER, rurality-informed
    df["current_stock_days_remaining"] = rng.integers(0, 30, n)               # PLACEHOLDER
    df["road_access_flag"] = np.where(
        rurality > 0.6,
        rng.choice(["seasonal", "conflict_restricted"], n, p=[0.6, 0.4]),
        rng.choice(["all_weather", "seasonal"], n, p=[0.7, 0.3]),
    )  # PLACEHOLDER, rurality-informed
    df["_data_provenance"] = (
        "location/name/facility_level/bed_class=REAL (MIMU 2020); "
        "population_served=derived from real bed_class; "
        "health rates/stock/road_risk=PLACEHOLDER, centered using real bed_class "
        "as a rurality proxy (not literal DHS/MICS data)"
    )
    return df


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/Hospitals.geojson"
    print(f"Loading real MIMU hospital data from {path}...")
    df = load_mimu_geojson(path)
    print(f"Loaded {len(df)} real facility records (all Myanmar)")

    df_filtered = df[df["state_region"].isin(TARGET_REGIONS)].reset_index(drop=True)

    # Apply Mandalay urban-core exclusion (keep Mandalay's rural/underserved townships only)
    is_mandalay_urban_core = (
        (df_filtered["state_region"] == "Mandalay")
        & (df_filtered["township"].isin(MANDALAY_URBAN_CORE_EXCLUDE))
    )
    excluded_count = is_mandalay_urban_core.sum()
    df_filtered = df_filtered[~is_mandalay_urban_core].reset_index(drop=True)

    print(f"Filtered to {TARGET_REGIONS}: {len(df_filtered) + excluded_count} facilities")
    print(f"  Excluded {excluded_count} Mandalay urban-core facilities "
          f"({', '.join(sorted(MANDALAY_URBAN_CORE_EXCLUDE))})")
    print(f"  Kept {len(df_filtered)} facilities (Rakhine + Sagaing + Mandalay rural)")
    for region in TARGET_REGIONS:
        print(f"  {region}: {(df_filtered.state_region == region).sum()}")

    df_filtered["clinic_id"] = [f"CL-{i:04d}" for i in range(1, len(df_filtered) + 1)]
    df_filtered = add_placeholder_operational_fields(df_filtered)

    cols = [
        "clinic_id", "clinic_name", "clinic_name_mya", "facility_level", "bed_class",
        "state_region_pcode", "state_region", "district_pcode", "district",
        "township_pcode", "township", "confidence", "latitude", "longitude",
        "institutional_delivery_rate", "skilled_birth_attendance_rate",
        "full_vaccination_rate", "current_stock_days_remaining",
        "population_served", "road_access_flag", "_data_provenance",
    ]
    df_filtered[cols].to_csv("clinics.csv", index=False)
    print(f"\nWrote clinics.csv with {len(df_filtered)} REAL clinic locations for {TARGET_REGIONS}")
    print("Facility level breakdown:")
    print(df_filtered["facility_level"].value_counts().to_string())


if __name__ == "__main__":
    main()
