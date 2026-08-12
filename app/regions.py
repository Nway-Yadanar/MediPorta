"""
regions.py

The transferability layer: a country-agnostic engine + swappable regional data
packs. Each region names its candidate supply hubs (real hospitals that stock
and redistribute), its waterway files (if the region has a real water story),
and its characteristic scenario.

This is the concrete answer to "does it transfer": the engine never changes.
A region is just this config plus its data files.

HUBS are real MIMU facilities (largest-bed general hospitals), designated as
supply/distribution points. That role designation is a modeling choice
(flagged), but the facilities themselves are real and do hold stock in reality.
"""

REGIONS = {
    "Rakhine": {
        "label": "Rakhine — coastal & riverine",
        "story": "boat",
        "story_text": "Coastal state on the Mayu River. When bridges wash out, "
                      "the last leg switches to boat — but open boats can't hold "
                      "cold chain, so vaccines may not survive the reroute.",
        "center": [20.6, 92.9],
        "zoom": 8,
        "waterways": "waterways.geojson",
        "docks": "boat_docks.geojson",
        "hubs": [
            {"id": "CL-0242", "name": "Sittwe General Hospital", "bed": 500, "default": True},
            {"id": "CL-0277", "name": "Kyaukpyu General Hospital", "bed": 200},
            {"id": "CL-0294", "name": "Thandwe General Hospital", "bed": 100},
            {"id": "CL-0248", "name": "Mrauk-U Township Hospital", "bed": 100},
        ],
        
        "scenario": {"clinic": "CL-0270", "type": "bridge_to_boat"},
    },
    "Sagaing": {
        "label": "Sagaing — Chindwin river corridor",
        "story": "river",
        "story_text": "The Chindwin River threads the region; towns like Homalin "
                      "and Mawlaik are barely road-reachable. Monsoon road cuts "
                      "force river resupply along the Chindwin.",
        "center": [23.3, 95.0],
        "zoom": 7,
        "waterways": "waterways_sagaing.geojson",
        "docks": "boat_docks_sagaing.geojson",
        "hubs": [
            {"id": "CL-0047", "name": "Monywa General Hospital", "bed": 500, "default": True},
            {"id": "CL-0102", "name": "Kale General Hospital", "bed": 300},
            {"id": "CL-0012", "name": "Shwebo General Hospital", "bed": 200},
            {"id": "CL-0001", "name": "Sagaing General Hospital", "bed": 200},
        ],
        "scenario": {"clinic": None, "type": "bridge_to_boat"},  # resolved at export
    },
    "Mandalay": {
        "label": "Mandalay — road network",
        "story": "road",
        "story_text": "Largely landlocked and road-dense. No boats here — the real "
                      "story is multi-clinic road runs and access loss from the "
                      "March 2025 earthquake. The engine doesn't force boats where "
                      "they don't belong.",
        "center": [21.4, 96.0],
        "zoom": 8,
        "waterways": None,   
        "docks": None,
        "hubs": [
            {"id": "CL-0152", "name": "Pyinoolwin General Hospital", "bed": 300, "default": True},
            {"id": "CL-0227", "name": "Meiktila General Hospital", "bed": 200},
            {"id": "CL-0171", "name": "Kyaukse General Hospital", "bed": 200},
            {"id": "CL-0209", "name": "Nyaung-U General Hospital", "bed": 200},
        ],
        "scenario": {"clinic": None, "type": "road_reroute"},  # resolved at export
    },
}


def default_hub(region):
    for h in REGIONS[region]["hubs"]:
        if h.get("default"):
            return h["id"]
    return REGIONS[region]["hubs"][0]["id"]


def all_hub_ids():
    return [(r, h["id"]) for r, cfg in REGIONS.items() for h in cfg["hubs"]]
