"""
load_real_clinics.py

Converts real downloaded clinic/health-facility data (MIMU or HOTOSM GeoJSON)
into the clinics.csv schema graph_engine.py / vulnerability.py already expect.

Usage:
    1. Download one of the sources in REAL_DATA_SOURCES.md into data/real/
    2. Update SOURCE_FILE below to match the filename you downloaded
    3. python load_real_clinics.py
    4. Output: clinics.csv (overwrites the synthetic one — back it up first if
       you want to keep it for comparison demos)

Requires: geopandas, shapely  (pip install geopandas shapely)
"""

import geopandas as gpd
import pandas as pd
import numpy as np

REAL_DIR = "real"
SOURCE_FILE = f"{REAL_DIR}/health_facilities.geojson"  
SOURCE_TYPE = "mimu_hospitals"  
# Bounding box filter -> Rakhine + Sagaing only 
RAKHINE_SAGAING_BBOX = {
    "lat_min": 15.5, "lat_max": 26.5,   
    "lon_min": 92.0, "lon_max": 97.5,
}


def load_mimu_hospitals(path: str) -> pd.DataFrame:
    gdf = gpd.read_file(path)
    gdf["latitude"] = gdf.geometry.y
    gdf["longitude"] = gdf.geometry.x
    df = pd.DataFrame({
        "clinic_id": [f"CL-{i:04d}" for i in range(1, len(gdf) + 1)],
        "clinic_name": gdf.get("nmhsp_eng", gdf.get("name", "Unknown")),
        "township_pcode": gdf.get("dt_pcode", gdf.get("sr_pcode", "UNKNOWN")),
        "latitude": gdf["latitude"],
        "longitude": gdf["longitude"],
        "facility_level": gdf.get("lvlhsp_eng", "unknown"),
    })
    return df


def load_hotosm_health(path: str) -> pd.DataFrame:
    gdf = gpd.read_file(path)
    gdf = gdf[gdf.geometry.geom_type == "Point"].copy()
    gdf["latitude"] = gdf.geometry.y
    gdf["longitude"] = gdf.geometry.x

    df = pd.DataFrame({
        "clinic_id": [f"CL-{i:04d}" for i in range(1, len(gdf) + 1)],
        "clinic_name": gdf.get("name", gdf.get("name_en", "Unnamed facility")),
        "township_pcode": "UNKNOWN",  
        "latitude": gdf["latitude"],
        "longitude": gdf["longitude"],
        "facility_level": gdf.get("amenity", gdf.get("healthcare", "unknown")),
    })
    return df


def load_healthsites(path: str) -> pd.DataFrame:
    raw = pd.read_csv(path) if path.endswith(".csv") else gpd.read_file(path)
    df = pd.DataFrame({
        "clinic_id": [f"CL-{i:04d}" for i in range(1, len(raw) + 1)],
        "clinic_name": raw.get("Name", "Unnamed facility"),
        "township_pcode": "UNKNOWN",
        "latitude": raw.get("Lat"),
        "longitude": raw.get("Long"),
        "facility_level": raw.get("Nature of Facility", "unknown"),
    })
    return df


LOADERS = {
    "mimu_hospitals": load_mimu_hospitals,
    "hotosm_health": load_hotosm_health,
    "healthsites": load_healthsites,
}


def add_placeholder_operational_fields(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """
    Real datasets don't include live stock levels or DHS-style health-access rates
    at facility level. This fills those with clearly-flagged placeholder values so
    the pipeline runs end-to-end. Replace with real reporting data (SMS/ODK/DHIS2
    stock reports; township DHS/MICS rates joined by township_pcode) when available.
    """
    rng = np.random.default_rng(seed)
    n = len(df)
    df = df.copy()
    df["institutional_delivery_rate"] = rng.uniform(0.10, 0.45, n).round(3)   
    df["skilled_birth_attendance_rate"] = rng.uniform(0.08, 0.40, n).round(3)  
    df["full_vaccination_rate"] = rng.uniform(0.40, 0.85, n).round(3)         
    df["current_stock_days_remaining"] = rng.integers(0, 30, n)               
    df["population_served"] = rng.integers(500, 12000, n)                     
    df["road_access_flag"] = rng.choice(
        ["all_weather", "seasonal", "conflict_restricted"], n, p=[0.4, 0.35, 0.25]
    )  
    df["_data_provenance"] = "location=REAL, operational/health fields=PLACEHOLDER"
    return df


def main():
    if SOURCE_TYPE not in LOADERS:
        raise ValueError(f"Unknown SOURCE_TYPE '{SOURCE_TYPE}'. Choose from {list(LOADERS)}")

    print(f"Loading real clinic locations from {SOURCE_FILE} ({SOURCE_TYPE})...")
    df = LOADERS[SOURCE_TYPE](SOURCE_FILE)

    before = len(df)
    df = df[
        df.latitude.between(RAKHINE_SAGAING_BBOX["lat_min"], RAKHINE_SAGAING_BBOX["lat_max"])
        & df.longitude.between(RAKHINE_SAGAING_BBOX["lon_min"], RAKHINE_SAGAING_BBOX["lon_max"])
    ].reset_index(drop=True)
    print(f"Filtered to Rakhine/Sagaing bbox: {before} -> {len(df)} facilities")

    df = add_placeholder_operational_fields(df)
    df.to_csv("clinics.csv", index=False)
    print(f"Wrote clinics.csv with {len(df)} REAL clinic locations "
          f"(health/operational fields are placeholders — see _data_provenance column)")


if __name__ == "__main__":
    main()
