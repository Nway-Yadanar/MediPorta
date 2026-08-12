"""
generate_telecom_status.py

Builds telecom_status.csv at TOWNSHIP level (keyed on real MIMU township_pcode),
then use it to boost triage priority for clinics that cannot call for help.

THE INSIGHT this encodes:
  Reactive supply systems wait for clinics to REQUEST resupply. The clinics that
  need help most are often in telecom-blackout zones and physically cannot make
  that request -- so they are invisible to reactive systems and get nothing.
  MediRoute treats blackout as a REASON TO PUSH: blackout clinics get a priority
  boost, because silence is not "no need", it is "cannot ask".

DATA (honest, mixed provenance):
  * A set of townships in northern Rakhine (and some Sagaing) have DOCUMENTED,
    long-running military-imposed internet/phone shutdowns, widely reported by
    access-monitoring organizations. Those are flagged status from real
    reporting.  -> _data_provenance = real_reporting
  * Everywhere else, we fall back to a CONFLICT PROXY: townships whose clinics
    carry conflict_restricted / seasonal road_access_flag are more likely to
    have degraded comms.  -> _data_provenance = conflict_proxy
  * Townships with no signal are 'normal'.  -> conflict_proxy (assumed normal)

Nothing here claims to be a coverage map. It is a transparent, defensible
blackout proxy, flagged per row.

Usage:
    python generate_telecom_status.py
"""

import csv
from collections import defaultdict

import pandas as pd

# Townships with documented, long-running shutdowns (real reporting).
# Northern Rakhine has been under the most prolonged internet restrictions in
# the country; several Sagaing townships saw shutdowns during operations.
# Matched by township NAME (case-insensitive) against MIMU township field.
KNOWN_BLACKOUT_TOWNSHIPS = {
    # Rakhine (prolonged shutdowns)
    "buthidaung": "blackout",
    "maungdaw": "blackout",
    "rathedaung": "blackout",
    "minbya": "blackout",
    "mrauk-u": "blackout",
    "ponnagyun": "blackout",
    "myebon": "blackout",
    "kyauktaw": "blackout",
    "pauktaw": "intermittent",
    "ann": "intermittent",
    # Sagaing (operation-linked shutdowns)
    "khin-u": "intermittent",
    "kani": "intermittent",
    "ye-u": "intermittent",
    "pale": "intermittent",
    "kalay": "intermittent",
}

PRIORITY_MULTIPLIER = {
    "blackout": 1.30,      # cannot call at all -> strongest push
    "intermittent": 1.15,  # unreliable -> moderate push
    "normal": 1.00,
}


def main():
    clinics = pd.read_csv("clinics.csv")

    # one row per township (PCODE), carrying region + a conflict signal.
    # We only treat CONFLICT_RESTRICTED as a comms-degradation signal -- seasonal
    # roads are a weather/access issue, not a shutdown signal. This keeps the
    # proxy DISCRIMINATING: if nearly every township came back "intermittent",
    # the layer would carry no information. Most townships should be 'normal'.
    tw = (
        clinics.groupby(["township_pcode", "township", "state_region"])
        .agg(
            n_clinics=("clinic_id", "count"),
            conflict_signal=("road_access_flag",
                             lambda s: (s == "conflict_restricted").mean() >= 0.5),
        )
        .reset_index()
    )

    rows = []
    for t in tw.itertuples():
        name = str(t.township).strip().lower()
        if name in KNOWN_BLACKOUT_TOWNSHIPS:
            status = KNOWN_BLACKOUT_TOWNSHIPS[name]
            prov = "real_reporting"
            src = "access-monitoring shutdown reporting (township-level)"
        elif t.conflict_signal:
            status = "intermittent"
            prov = "conflict_proxy"
            src = "inferred from conflict_restricted/seasonal road access"
        else:
            status = "normal"
            prov = "conflict_proxy"
            src = "assumed normal (no shutdown reporting, no conflict signal)"

        rows.append({
            "township_pcode": t.township_pcode,
            "township": t.township,
            "state_region": t.state_region,
            "n_clinics": t.n_clinics,
            "telecom_status": status,
            "priority_multiplier": PRIORITY_MULTIPLIER[status],
            "_source": src,
            "_data_provenance": prov,
        })

    out = pd.DataFrame(rows).sort_values(
        ["telecom_status", "state_region", "township"]
    )
    out.to_csv("telecom_status.csv", index=False)

    counts = out["telecom_status"].value_counts().to_dict()
    n_real = (out["_data_provenance"] == "real_reporting").sum()
    print(f"Wrote telecom_status.csv: {len(out)} townships")
    print(f"  status counts: {counts}")
    print(f"  real-reporting townships: {n_real}  (rest conflict_proxy)")
    print()
    print("Blackout/intermittent townships (the ones that can't call for help):")
    show = out[out.telecom_status != "normal"][
        ["township", "state_region", "telecom_status", "priority_multiplier", "_data_provenance"]
    ]
    print(show.to_string(index=False))


if __name__ == "__main__":
    main()
