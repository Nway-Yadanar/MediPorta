# Real Data Sources for MediRoute — Verified Links

I verified these actually exist via search (as of Aug 2026). I could not download
them directly into this sandbox — MIMU Geonode and HDX both block automated/bot
traffic (robots.txt + bot detection), which is exactly the kind of protection
you'd want on humanitarian data. Your browser won't hit that wall. Download these,
then follow the "Bring your own data" steps below.

## 1. Clinic / Health Facility Locations (pick ONE — MIMU is most authoritative)

**MIMU Public Hospitals in Myanmar (2020)** — most authoritative, MIMU-verified
- Page: https://data.humdata.org/dataset/mimu-geonode-public-hospitals-in-myanmar
- Click "Download ... geojson" (resource id `47578a11-2a9c-4c85-b016-cfb86450927a`)
- Fields include: facility name (Myanmar + English), hospital level, bed class,
  state/region + district PCodes

**Alternative: OSM Health Facilities export (more facility types incl. rural clinics)**
- Page: https://data.humdata.org/dataset/hotosm_mmr_health_facilities
- Download `hotosm_mmr_health_facilities_points_geojson.zip`
- Better coverage of small rural clinics; less rigorously verified than MIMU

**Alternative: Myanmar-healthsites (updated monthly)**
- Page: https://data.humdata.org/dataset/myanmar-healthsites
- Simple fields: Name, Nature of Facility, Activities, Lat, Long

## 2. Road Network (pick ONE)

**MIMU Road Network** — official, but coarser (main/secondary/tertiary only)
- Page: https://data.humdata.org/dataset/mimu-geonode-myanmar-road-network
- Download the GeoJSON or Shapefile resource

**OSM Roads export (HOT)** — much denser, includes tracks/unpaved roads (critical
for last-mile routing to rural clinics — recommended for this project)
- Page: https://data.humdata.org/dataset/hotosm_mmr_roads
- Download `hotosm_mmr_roads_lines_geojson.zip`

**Full-country OSM extract (best if you want to run OSMnx offline / fastest)**
- https://download.geofabrik.de/asia/myanmar.html
- Grab `myanmar-latest.osm.pbf` (261MB) — feed directly to `osmnx.graph_from_xml()`
  or `osmium`/`osmnx` after clipping to Rakhine/Sagaing bounding box

## 3. Administrative Boundaries (for clipping to Rakhine + Sagaing, and PCode joins)

- Township boundaries: https://data.humdata.org/dataset/mimu-geonode-myanmar-township-boundaries-mimu
- State/Region boundaries: https://data.humdata.org/dataset/mimu-geonode-myanmar-state-and-region-boundaries-mimu

## 4. Health Baseline Indicators (for vulnerability scoring)

- WHO Health Indicators for Myanmar (World Bank portal mirror): https://data.humdata.org/dataset/a442696d-b9db-4a44-8198-7e5e88422058
- WHO World Health Statistics Indicators for Myanmar: https://data.humdata.org/dataset/who-data-for-myanmar
- **Caveat: these are national-level, not township-level.** For real township/state
  granularity (institutional delivery rate, SBA rate, vaccination by township), you'd
  need the Myanmar DHS 2015-16 or MICS report tables directly — those are PDF/Excel
  tables, not an API, so they need manual extraction. I can help extract from a PDF
  if you upload one.
- I confirmed the WHO GHO OData API itself is live and queryable (base:
  `https://ghoapi.azureedge.net/api/`), but it only returns **country-level**
  aggregates for Myanmar, not sub-national — useful for a national baseline
  comparison stat in your pitch, not for per-clinic scoring.

---

## Bring-your-own-data workflow

1. Download whichever files you picked above (2–4 files, a few minutes total)
2. Drop them in `mediroute/data/real/` (create the folder)
3. Run `python data/load_real_clinics.py` and `python data/load_real_roads.py`
   (scripts included in this build — see below) — these convert real files into
   the exact `clinics.csv` / `roads_nodes.csv` / `roads_edges.csv` schema the
   graph engine already expects, so **zero changes needed** in `graph_engine.py`,
   `vulnerability.py`, or `dashboard_app.py`
4. `current_stock_days_remaining` has no public real-time source (it's operational
   data no open dataset tracks) — you'll need to either simulate it realistically
   on top of real clinic locations, or use it as the one field you demo as
   "would connect to a live stock-reporting system (SMS/ODK/DHIS2) in production"

Alternatively — if downloading is a hassle mid-hackathon — just upload whichever
files you do get to our chat directly and I'll parse and convert them for you here.
