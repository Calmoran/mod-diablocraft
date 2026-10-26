#!/usr/bin/env python3
"""Drop the open zones' survey anchors that the core puts in another zone (diablocraft-hyoic.8; the cut diablocraft-dm9vg.16 made by hand).

    python3 mod-diablocraft/scripts/prune_open_zone_spots.py            # sheets -> sheets, migrations and report; idempotent

generate_open_zone_survey.py reads a zone from the terrain's area grid only. The core asks the WMO under a point first
(Map::GetAreaId), so a creature standing in a WMO of another zone (Dire Maul's courtyard, the Deadmines' gate, the Timbermaw
passage) is an anchor in the zone for the survey and in another zone for the zone wall. test_open_zone_spots.py runs the core's
own lookup over every anchor, bounty spot and entrance and fails on each such anchor. This script runs the same lookup, drops
those anchors, drops an area left with none, drops the routes that start at a dropped anchor, and re-counts an area that kept
some (natives is the sum of its anchors' pack sizes; the tag follows the natives). Anchor ids keep their gaps, as dm9vg.16 left
Moonglade's. Run it after every `generate_open_zone_survey.py --survey`: a survey restores what it dropped.
A bounty row's anchor that is dropped here fails generate_bounties.py (the row names the anchor), so it is re-picked then.
"""
import collections
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_open_zone_survey as O  # noqa: E402
import generate_rift_survey as S  # noqa: E402
import test_open_zone_spots as spots  # noqa: E402  the core's own lookup, cut out and compiled


def outside(binary):
    """{(zone name, anchor id)} of the anchors whose zone by the core's lookup is not their zone's."""
    key_of_name = {z["name"]: z["key"] for z in S.read_csv(S.D3 / S.OPEN_ZONES)}
    found = [p for p in spots.points() if p[2].startswith("anchor ")]
    name_of_key = {k: n for n, k in key_of_name.items()}
    got = spots.lookup_found(binary, found)
    return {(name_of_key[p[0]], p[2].split()[1]) for p, g in zip(found, got) if g[0] != p[1]}


def prune(sheets, drop, knobs):
    """The sheets without the dropped anchors, and the names of the zones that changed."""
    anchors = [a for a in sheets["rift_anchors.csv"] if (a["dungeon"], a["anchor"]) not in drop]
    natives = collections.Counter()
    for a in anchors:
        natives[(a["dungeon"], a["area"])] += int(a["pack_size"])
    changed = {name for name, _ in drop}
    areas = []
    for r in sheets["rift_areas.csv"]:
        if r["dungeon"] not in changed:
            areas.append(r)
        elif (r["dungeon"], r["area"]) in natives:
            n = natives[(r["dungeon"], r["area"])]
            areas.append(dict(r, natives=str(n), tag=S.tag_of(n, knobs) if int(r["natives"]) != n else r["tag"]))
    routes = [r for r in sheets["rift_routes.csv"] if (r["dungeon"], r["anchor"]) not in drop]
    return {"rift_areas.csv": areas, "rift_anchors.csv": anchors, "rift_routes.csv": routes}, changed


def refresh_report(sheets, names, knobs):
    """The report rows of the changed zones, re-counted from the pruned sheets (the stock counts in them stay)."""
    rows = S.read_csv(O.REPORT)
    zone_knobs = O.zone_knobs(knobs)
    for row in rows:
        if row["zone"] not in names:
            continue
        areas = [r for r in sheets["rift_areas.csv"] if r["dungeon"] == row["zone"]]
        anchors = [r for r in sheets["rift_anchors.csv"] if r["dungeon"] == row["zone"]]
        routes = [r for r in sheets["rift_routes.csv"] if r["dungeon"] == row["zone"]]
        tags = collections.Counter(a["tag"] for a in areas)
        filled, bodies, elite, solos = S.estimate(areas, anchors, routes, zone_knobs)
        clear = knobs.get("entry_clear_yards")
        row.update(native_anchors=sum(1 for a in anchors if a["native_guid"] != ""), sampled_anchors=sum(1 for a in anchors if a["native_guid"] == ""),
                   areas_s=tags["S"], areas_m=tags["M"], areas_l=tags["L"], expected_anchors=round(filled, 1), expected_bodies=round(bodies),
                   expected_elite_packs=round(elite, 1), expected_solos=round(solos, 1), anchors_with_route=len({r["anchor"] for r in routes}),
                   anchors_near_entry=sum(1 for a in anchors if float(a["entry_walk_yards"]) < clear) if clear else "")
    with O.REPORT.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(O.REPORT_COLUMNS)
        writer.writerows([[row[c] for c in O.REPORT_COLUMNS] for row in rows])


def main():
    drop = outside(spots.build())
    committed = S.read_sheets()
    pruned, changed = prune(committed, drop, S.read_knobs())
    sheets = O.with_zone_exits({**committed, **pruned})   # a dropped anchor may have been its zone's exit (yh7el)
    for name, rows in sheets.items():
        S.write_csv(S.D3 / name, S.SHEETS[name], rows)
    refresh_report(sheets, changed, S.read_knobs())
    print(f"dropped {len(drop)} anchors in {len(changed)} zones")
    S.generate()


if __name__ == "__main__":
    main()
