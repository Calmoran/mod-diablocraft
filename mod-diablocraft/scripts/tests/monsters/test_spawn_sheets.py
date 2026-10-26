"""diablocraft-dt7c - the spawn sheets (monster-spawning.md section 5, Part S1).

What this proves, and what it does not:

  * The generator's rules, on a small made-up roster whose answers are known by hand: which families a set can make clusters
    of (a melee or ranged member that is not solo-flagged), which monsters stand as solos, how a family override inherits the
    size's role ranges, the held-back monster having no entry, "summoner" counted as caster, and each refusal (an unknown or
    held-back member, a family weight list that is not the members' families, a range whose minimum passes its maximum, a
    recipe whose roles cannot make its bodies, a monster list out of the roster's order, an area that takes no size, percents
    outside 0 to 100). The same checks run against single-rule mutants of the generator, each of which must turn them red.
  * The data, against sources that are not the sheets: the 18 seed sets are recomputed here from gr_monster_sets.csv and the
    roster's warpath_name cells and must equal the sheet (rows still marked `source d3`); their monsters and families equal
    Appendix A of the plan; the plan's list of 18 sets; the recipes equal the plan's 3.3 table; the area defaults equal 4.7;
    the five renamed roster rows now name warpath's monsters, which exist in gr_monster_progress.csv; every monster has its
    wander of 8 and only the Savage is solo; the knob and orb seeds equal the plan's numbers, the unsourced ones are blank;
    the committed migration, mirror and report equal a fresh render; the S0 survey report's estimate reads the same figures
    it read before the spawn sheets owned them.
  * `spawn_sheets_0001.sql` is replayed twice on a disposable MySQL and read back (counts, the clusterable flags against an
    independent computation, the held-back monster's NULL entry); a migration without its DELETE is shown not to replay.
  * NOT proved: that the spawner reads them as intended (Part S2); that any figure is the right one (the designer's pass on dev).
"""
import csv
import pathlib
import re
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import fixture_db
import generate_spawn_sheets as G
import generate_rift_survey as S0
from test_account_economy_sql import MYSQL, ROOT, isolated
from test_rift_survey import module_from
from test_slot_vendors import check

MODULE = ROOT / "mod-diablocraft"
SOURCE = MODULE / "scripts/generate/monsters/generate_spawn_sheets.py"
PLAN = ROOT / "docs/proposals/monster-spawning.md"
TUN = MODULE / "data/tunables"
D3 = MODULE / "data/d3"


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


# ---- a small roster, and sheets whose answers are known by hand ---------------------------------------------------------------

ROSTER = [("Zombies", "Walking Corpse", "melee"), ("Zombies", "Decaying Cryptstalker", "melee"),
          ("Cultists", "Dark Berserker", "big/melee"), ("Cultists", "Dark Summoner", "summoner/caster"),
          ("Cultists", "Dark Archer", "ranged"), ("Swarm", "Wasp", "ranged"), ("Swarm", "Swarmling", "melee"),
          ("Ghosts", "Phantom", "caster/melee")]
SET_COLUMNS = ["set_id", "name", "weight", "nephalem", "greater", "monsters", "family_weights", "source", "d3_set", "d3_missing", "notes"]
RECIPE_COLUMNS = ["size", "family", "bodies_min", "bodies_max", "melee_min", "melee_max", "ranged_min", "ranged_max",
                  "caster_min", "caster_max", "big_min", "big_max", "notes"]
SPAWN_COLUMNS = ["monster", "family", "solo", "wander_yards", "notes"]
AREA_COLUMNS = ["tag", "anchors_min", "anchors_max", "small", "medium", "large", "notes"]


def valid():
    return dict(
        roster=[dict(zip(("family", "name", "role"), r)) for r in ROSTER],
        sets=[dict(set_id=1, name="A", weight=1, nephalem="yes", greater="yes", monsters="Walking Corpse; Dark Berserker; Dark Summoner",
                   family_weights="Zombies=1; Cultists=2", source="d3", d3_set=7, d3_missing="", notes=""),
              dict(set_id=2, name="B", weight=0.5, nephalem="no", greater="yes", monsters="Dark Archer; Phantom; Swarmling",
                   family_weights="Cultists=1; Ghosts=1; Swarm=0.25", source="alex", d3_set="", d3_missing="", notes="")],
        recipes=[dict(zip(RECIPE_COLUMNS, [s, "", *v, ""])) for s, v in
                 (("small", (3, 5, 2, 4, 0, 1, 0, 1, 0, 0)), ("medium", (6, 10, 4, 7, 1, 2, 0, 1, 0, 1)),
                  ("large", (12, 20, 7, 12, 2, 4, 1, 2, 1, 2)), ("patrol", (3, 6, 2, 4, 0, 1, 0, 1, 0, 1)))]
        + [dict(zip(RECIPE_COLUMNS, ["small", "Swarm", 3, 3, "", "", "", "", "", "", "", "", ""])),
           dict(zip(RECIPE_COLUMNS, ["large", "Swarm", 3, 3, 2, 3, 0, 1, 0, 1, 0, 1, ""]))],
        spawn=[dict(monster=n, family=f, solo="yes" if n == "Swarmling" else "no", wander_yards=8, notes="") for f, n, _ in ROSTER],
        areas=[dict(tag="S", anchors_min=1, anchors_max=1, small="yes", medium="no", large="no", notes=""),
               dict(tag="M", anchors_min=1, anchors_max=2, small="yes", medium="yes", large="no", notes=""),
               dict(tag="L", anchors_min=2, anchors_max=3, small="yes", medium="yes", large="yes", notes="")])


def write_all(directory, d):
    directory = pathlib.Path(directory)
    for name, columns, key in (("monster_sets.csv", SET_COLUMNS, "sets"), ("cluster_recipes.csv", RECIPE_COLUMNS, "recipes"),
                               ("monster_spawn.csv", SPAWN_COLUMNS, "spawn"), ("area_defaults.csv", AREA_COLUMNS, "areas")):
        with open(directory / name, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(d[key])
    with open(directory / "roster.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, ["family", "name", "role", "warpath_name"], lineterminator="\n")
        writer.writeheader()
        writer.writerows([dict(r, warpath_name="none") for r in d["roster"]])


def load(mod, d, tmp):
    write_all(tmp, d)
    return mod.load(tmp, pathlib.Path(tmp) / "roster.csv")


def refused(mod, change, tmp):
    d = valid()
    change(d)
    try:
        load(mod, d, tmp)
    except mod.DataError:
        return True
    return False


def knobs_refused(mod, rows, tmp):
    path = pathlib.Path(tmp) / "rifts.csv"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["name", "d3_value", "value", "unit", "notes"])
        writer.writerows([[n, "", v, "", ""] for n, v in rows])
    try:
        mod.check_knobs(path)
    except mod.DataError:
        return True
    return False


REFUSALS = [
    ("a set member that is not on the roster", lambda d: d["sets"][0].update(monsters="Walking Corpse; Nobody", family_weights="Zombies=1")),
    ("a set member with no creature row", lambda d: d["sets"][0].update(monsters="Walking Corpse; Decaying Cryptstalker", family_weights="Zombies=1")),
    ("a monster twice in a set", lambda d: d["sets"][0].update(monsters="Walking Corpse; Walking Corpse", family_weights="Zombies=1")),
    ("a family weight missing", lambda d: d["sets"][0].update(family_weights="Zombies=1")),
    ("a family weight for a family the set does not have", lambda d: d["sets"][0].update(family_weights="Zombies=1; Cultists=1; Ghosts=1")),
    ("a negative family weight", lambda d: d["sets"][0].update(family_weights="Zombies=-1; Cultists=1")),
    ("a set source that is not d3 or alex", lambda d: d["sets"][0].update(source="me")),
    ("a mode switch that is not yes or no", lambda d: d["sets"][0].update(greater="maybe")),
    ("two sets with one id", lambda d: d["sets"][1].update(set_id=1)),
    ("a recipe range with its minimum above its maximum", lambda d: d["recipes"][0].update(melee_min=5, melee_max=4)),
    ("a recipe of no bodies", lambda d: d["recipes"][0].update(bodies_min=0)),
    ("a recipe size missing", lambda d: d.update(recipes=[r for r in d["recipes"] if r["size"] != "patrol"])),
    ("a recipe for an unknown family", lambda d: d["recipes"][-1].update(family="Nobody")),
    ("role ranges that cannot make the bodies", lambda d: d["recipes"][0].update(bodies_min=9, bodies_max=9)),
    ("a Swarm row whose inherited roles cannot make its bodies",   # the large size's role minimums sum to 6, Swarm makes 3
     lambda d: d["recipes"][-1].update(melee_min="", melee_max="", ranged_min="", ranged_max="", caster_min="", caster_max="", big_min="", big_max="")),
    ("role minimums that do not fit the bodies", lambda d: d["recipes"][0].update(melee_min=4, melee_max=4, bodies_max=3, bodies_min=3)),
    ("the monsters out of the roster's order", lambda d: d["spawn"].insert(3, d["spawn"].pop(2))),   # two Cultists swapped: the family still agrees
    ("a spawn row with the wrong family", lambda d: d["spawn"][0].update(family="Swarm")),
    ("a negative wander", lambda d: d["spawn"][0].update(wander_yards=-1)),
    ("solo that is not yes or no", lambda d: d["spawn"][0].update(solo="1")),
    ("area tags out of order", lambda d: d["areas"].reverse()),
    ("an area that takes no size", lambda d: d["areas"][0].update(small="no")),
    ("an area whose minimum is above its maximum", lambda d: d["areas"][2].update(anchors_min=4)),
]


def synthetic_checks(mod):
    with tempfile.TemporaryDirectory() as tmp:
        data = load(mod, valid(), tmp)
        a, b = data["sets"]
        assert a["clusterable"] == ["Zombies"], a["clusterable"]   # Cultists: a big and a caster, neither makes a cluster
        assert b["clusterable"] == ["Cultists"], b["clusterable"]   # the ranged archer clusters; Swarm has only the solo-flagged Swarmling
        rows = {r["set_id"]: r for r in mod.report(data)}
        assert rows[1]["solo_families"] == "Cultists" and rows[1]["solo_monsters"] == "Dark Berserker; Dark Summoner", rows[1]
        assert rows[2]["solo_families"] == "Ghosts; Swarm" and rows[2]["solo_monsters"] == "Phantom; Swarmling", rows[2]   # caster/melee is a caster
        assert rows[1]["skipped"] == "no"
        assert data["spawn"]["Dark Summoner"]["role"] == "caster" and data["spawn"]["Phantom"]["role"] == "caster"
        assert data["spawn"]["Decaying Cryptstalker"]["entry"] is None and data["spawn"]["Walking Corpse"]["entry"] == mod.models.FAMILY_ENTRY_BASE + 1
        recipes = {(r["size"], r["family"]): r for r in data["recipes"]}
        assert len(recipes) == 6
        assert recipes[("small", "Swarm")]["bodies"] == (3, 3) and recipes[("small", "Swarm")]["melee"] == (2, 4)   # blank role cells take the size's
        assert recipes[("large", "Swarm")]["melee"] == (2, 3) and recipes[("large", "Swarm")]["big"] == (0, 1)        # a filled cell wins
        assert recipes[("large", "")]["melee"] == (7, 12)
        sql = mod.render(data)
        assert sql == mod.render(load(mod, valid(), tmp))
        assert "DELETE FROM `dc_monster_spawn`;" in sql and "('Decaying Cryptstalker', NULL, 'Zombies'" in sql
        skipped = valid()
        skipped["sets"][0].update(monsters="Dark Berserker; Dark Summoner", family_weights="Cultists=1")
        assert mod.report(load(mod, skipped, tmp))[0]["skipped"] == "yes"
        for what, change in REFUSALS:
            assert refused(mod, change, tmp), "not refused: " + what
        for rows in ([("elite_chance_pct", "101")], [("elite_champion_pct", "-1")], [("elite_packs_min", "5"), ("elite_packs_max", "4")]):
            assert knobs_refused(mod, rows, tmp), rows
        assert not knobs_refused(mod, [("elite_chance_pct", "25"), ("elite_packs_min", "4"), ("elite_packs_max", "19"), ("patrol_share_pct", "")], tmp)


GENERATOR_MUTANTS = [
    ("an unknown member is accepted", 'if m not in by_name:', "if False:"),
    ("a member with no creature row is accepted", 'if by_name[m]["entry"] is None:', "if False:"),
    ("a monster twice in a set is accepted", "or len(set(members)) != len(members)", ""),
    ("family weights are not checked against the members", "if set(weights) != set(families):", "if False:"),
    ("a negative weight is accepted", "or value < 0:", ":"),
    ("a solo monster makes its family clusterable", "and not spawn[m][\"solo\"] for m in members", "for m in members"),
    ("a caster makes its family clusterable", 'CLUSTER_ROLES = ("melee", "ranged")', 'CLUSTER_ROLES = ("melee", "ranged", "caster")'),
    ("a summoner is not a caster", 'return "caster" if first == "summoner" else first', "return first"),
    ("a minimum above its maximum is accepted", "if a > b:", "if False:"),
    ("a recipe of no bodies is accepted", 'if values["bodies"][0] < 1:', "if False:"),
    ("the role ranges are not held to the bodies", 'if sum(row[r][0] for r in ROLES) > row["bodies"][1] or sum(row[r][1] for r in ROLES) < row["bodies"][0]:', "if False:"),
    ("the recipe sizes are not all required", "if set(base) != set(SIZES):", "if False:"),
    ("an override ignores the roles it fills", "(v[k] or base[size][k])", "base[size][k]"),
    ("an override does not inherit", "(v[k] or base[size][k])", "(v[k] or (0, 0))"),
    ("the monster order is not held", 'if [r["monster"] for r in rows] != [m["monster"] for m in roster]:', "if False:"),
    ("the spawn family is not checked", 'if row["family"] != m["family"]:', "if False:"),
    ("yes or no takes anything", 'if value not in ("yes", "no"):', "if False:"),
    ("the area tags are not held", 'if [r["tag"] for r in rows] != list(TAGS):', "if False:"),
    ("an area may take no size", "if not any(sizes.values()):", "if False:"),
    ("the bodies check skips the override rows", "for row in out: # every row as it", "for row in out[:len(SIZES)]: # every row as it"),
    ("a percent may pass 100", "<= float(knobs[name]) <= 100", "<= float(knobs[name])"),
    ("the elite minimum may pass the maximum", "float(low) > float(high)", "False"),
    ("a skipped set is not flagged", '"yes" if not s["clusterable"] else "no"', '"no"'),
    ("a table is not emptied first", 'f"DELETE FROM `{name}`;"]', '""]'),
    ("the held-back monster gets an entry", 'entry=None if r["name"] in models.HELD_BACK else entry[r["name"]]', 'entry=entry[r["name"]]'),
]


def test_rules_and_mutants():
    synthetic_checks(G)
    print("PASS the generator's rules on the small roster", flush=True)
    for what, old, new in GENERATOR_MUTANTS:
        mutant = module_from(SOURCE, old, new, "generate_spawn_sheets_mutant")
        try:
            synthetic_checks(mutant)
        except (AssertionError, Exception) as error:   # a mutant that raises anything else is also dead
            check(True, f"mutant killed: {what} ({type(error).__name__})")
            continue
        raise AssertionError("generator mutant survived: " + what)


# ---- the data ---------------------------------------------------------------------------------------------------------------

PLAN_SEEDS = [1, 2, 4, 6, 9, 10, 13, 15, 19, 20, 21, 23, 26, 27, 28, 29, 30, 33]   # monster-spawning.md 3.2


def plan_appendix_a():
    """{set: {(monster, family)}} from Appendix A's 'Our monsters (family)' column."""
    out = {}
    text = PLAN.read_text(encoding="utf-8").split("## Appendix A", 1)[1].split("## Appendix B", 1)[0]
    for line in text.splitlines():
        m = re.match(r"\| (\d+) \| [^|]+ \| \d+ \| \d+ \| ([^|]+) \|", line)
        if m and m[2].strip() != "none":
            out[int(m[1])] = {tuple(re.match(r"(.+) \((.+)\)", p.strip()).groups()) for p in m[2].split(";")}
    return out


def plan_recipes():
    """{size: [(min, max) x5]} from the 3.3 table: bodies, melee, ranged, caster, big."""
    text = PLAN.read_text(encoding="utf-8").split("**A recipe** is", 1)[1].split("Family override", 1)[0]
    out = {}
    for line in text.splitlines():
        m = re.match(r"\| (Small|Medium|Large|Patrol) \|(.+)\|$", line)
        if m:
            cells = [c.strip() for c in m[2].split("|")]
            out[m[1].lower()] = [tuple(map(int, re.split("–", c))) if "–" in c else (int(c), int(c)) for c in cells]
    return out


def test_data():
    roster = read(D3 / "monster_roster.csv")
    sets = read(TUN / "monster_sets.csv")
    # the seeds, recomputed from the D3 sets and the roster's warpath names
    by_warpath = {}
    for r in roster:
        by_warpath.setdefault(r["warpath_name"], []).append(r)
    expected = []
    for s in read(D3 / "gr_monster_sets.csv"):
        names = [n.strip() for n in s["monster_names"].split(";")]
        hit = [n for n in names if n in by_warpath]
        if len(hit) >= 4:
            expected.append((int(s["set_number"]), {r["name"] for n in hit for r in by_warpath[n]}))
    check([e[0] for e in expected] == PLAN_SEEDS, "the sets with four or more of our monsters are the plan's 18")
    check([int(s["d3_set"]) for s in sets] == PLAN_SEEDS and [int(s["set_id"]) for s in sets] == list(range(1, 19)), "the sheet holds the plan's 18 sets in order")
    for s, (number, members) in zip(sets, expected):
        check(s["source"] == "d3" and set(m.strip() for m in s["monsters"].split(";")) == members, f"set {number}: the sheet's monsters are D3's set cut to our roster")
    appendix = plan_appendix_a()
    family_of = {r["name"]: r["family"] for r in roster}
    for s in sets:
        got = {(m.strip(), family_of[m.strip()]) for m in s["monsters"].split(";")}
        check(got == appendix[int(s["d3_set"])], f"set {s['d3_set']}: its monsters and families are Appendix A's")
    for s in sets:
        missing = [n.strip() for n in next(x for x in read(D3 / "gr_monster_sets.csv") if x["set_number"] == s["d3_set"])["monster_names"].split(";")]
        check(s["d3_missing"] == "; ".join(n for n in missing if n not in by_warpath), f"set {s['d3_set']}: d3_missing is what the roster lacks")
        check(s["weight"] == "1" and s["nephalem"] == "yes" and s["greater"] == "yes", f"set {s['d3_set']}: weight 1, both modes on (3.2)")
    # the five renamed roster rows
    progress = {r["name"] for r in read(D3 / "gr_monster_progress.csv")}
    for name in ("Moon Clan Shaman", "Ice Clan Warrior", "Sand Wasp", "Tusked Bogan", "Shade Stalker", "Stinging Swarm"):
        row = next(r for r in roster if r["name"] == name)
        check(row["warpath_name"] == name and name in progress, f"{name}: warpath_name is warpath's own name")
    check(len(roster) == 65, "the roster still has 65 monsters")
    # the other sheets against the plan
    spawn = read(TUN / "monster_spawn.csv")
    check([r["monster"] for r in spawn] == [r["name"] for r in roster], "monster_spawn.csv lists the 65 roster monsters in order")
    check({r["wander_yards"] for r in spawn} == {"8"}, "every monster wanders 8 yards (4.15)")
    check([r["monster"] for r in spawn if r["solo"] == "yes"] == ["Savage"], "only the Savage is solo (3.4)")
    recipes = read(TUN / "cluster_recipes.csv")
    plan = plan_recipes()
    check(sorted(plan) == ["large", "medium", "patrol", "small"], "the plan's 3.3 table has four sizes")
    for r in recipes:
        if not r["family"]:
            got = [(int(r[f"{c}_min"]), int(r[f"{c}_max"])) for c in ("bodies", "melee", "ranged", "caster", "big")]
            check(got == plan[r["size"]], f"{r['size']}: the recipe is the plan's 3.3 row")
    swarm = [r for r in recipes if r["family"] == "Swarm"]
    check([r["size"] for r in swarm] == ["small", "medium", "large", "patrol"] and all(r["bodies_min"] == r["bodies_max"] == "3" for r in swarm),
          "Swarm is exactly 3 at every size (3.3)")
    check(all([r[c] for c in ("melee_min", "melee_max", "ranged_min", "ranged_max", "caster_min", "caster_max", "big_min", "big_max")] == ["2", "2", "1", "1", "0", "0", "0", "0"] for r in swarm),
          "every Swarm cluster is 2 Swarmlings (melee) + 1 Wasp (ranged) at every size (q-1008-15)")
    check(len(recipes) == 8, "eight recipe rows: four sizes and Swarm's four")
    areas = read(TUN / "area_defaults.csv")
    check([(r["tag"], r["anchors_min"], r["anchors_max"], r["small"], r["medium"], r["large"]) for r in areas] ==
          [("S", "1", "1", "yes", "no", "no"), ("M", "1", "2", "yes", "yes", "no"), ("L", "2", "3", "yes", "yes", "yes")], "the area defaults are 4.7 (a)")
    rifts = {r["name"]: r["value"] for r in read(TUN / "rifts.csv")}
    published = {r["name"]: r["d3_value"] for r in read(TUN / "rifts.csv")}
    seeds = dict(elite_chance_pct="25", elite_packs_min="4", elite_packs_max="19", elite_champion_pct="50", solo_share_pct="10",
                 cluster_radius_small_yards="5", patrol_share_pct="20", patrol_record_step_yards="4", nr_orb_champion_count="3", nr_orb_rare_count="4", nr_orb_points="6.5")
    for name, value in seeds.items():
        check(rifts[name] == value, f"rifts.csv {name} is the plan's {value}")
    # warpath's Greater Rift orb numbers are what D3 published (README: d3_value, with the source in the notes); the designer's value stays blank
    # for the counts, and is 1% of the bar for the orb's points (card q-1008-11, diablocraft-xgms)
    for name, value, alex in (("gr_orb_champion_count", "3", ""), ("gr_orb_rare_count", "4", ""), ("gr_orb_points", "7.5", "6.5")):
        row = next(r for r in read(TUN / "rifts.csv") if r["name"] == name)
        check(row["d3_value"] == value and row["value"] == alex and "warpath.eu" in row["notes"], f"rifts.csv {name} is D3's {value} in d3_value, with warpath in the notes")
        check(published[name] == value, f"{name} d3_value")
    for name in ("entry_clear_yards", "floor_body_cap", "cluster_min_spacing_yards"):
        check(rifts[name] == "", f"rifts.csv {name} is blank: the plan gives no number")
    # the open zones' spacing and area cap are the designer's (2026-10-16, card q-1016-24, diablocraft-71kk3); floor_body_cap stays blank as the brake
    for name, value in (("open_zone_spacing_yards", "40"), ("open_zone_area_max_yards", "120")):
        check(rifts[name] == value, f"rifts.csv {name} is the designer's {value} (q-1016-24)")
    # the Nephalem orb's look is the designer's pick from the orb row on dev (2026-10-16, diablocraft-ivtf5): the Flame Sphere, small and lifted
    for name, value in (("nr_orb_display_id", "9701"), ("nr_orb_scale", "0.15"), ("nr_orb_lift_yards", "0.6")):
        check(rifts[name] == value, f"rifts.csv {name} is {value}, the Nephalem orb pick")
    plan_text = PLAN.read_text(encoding="utf-8")
    check("about 4 (The Forge of Souls, 46) and about 19 (The Nexus, 242)" in plan_text, "the plan states the elite minimum 4 and maximum 19")
    # the generator on the committed sheets
    G.check_knobs()
    data = G.load()
    sql = G.render(data)
    check((MODULE / "data/sql/db-world/updates" / G.NAME).read_text(encoding="utf-8") == sql, "the committed migration equals a fresh render")
    check((MODULE / "data/generated" / G.NAME).read_text(encoding="utf-8") == sql, "its data/generated mirror equals it")
    with tempfile.TemporaryDirectory() as tmp:
        G.write_report(G.report(data), pathlib.Path(tmp) / "r.csv")
        check((pathlib.Path(tmp) / "r.csv").read_bytes() == G.REPORT.read_bytes(), "the committed report equals a fresh one")
    rows = {r["set_id"]: r for r in G.report(data)}
    check(rows[1]["clusterable_families"] == "Skeletons", "set 1 clusters Skeletons only")
    check(rows[1]["solo_families"] == "Cultists; Reapers" and "Punisher" in rows[1]["solo_monsters"], "set 1's Reapers (just the Punisher) stand as solos (3.2)")
    check(all(r["skipped"] == "no" for r in rows.values()), "no seed set is skipped")
    # the S0 report's estimate reads the figures it used to read from rift_survey.csv
    knobs = S0.read_knobs()
    frozen = dict(density_s_min=1, density_s_max=1, density_m_min=1, density_m_max=2, density_l_min=2, density_l_max=3, size_small_min=3,
                  size_small_max=5, size_medium_min=6, size_medium_max=10, size_large_min=12, size_large_max=20, elite_chance_pct=25, solo_share_pct=10)
    check(all(knobs[k] == v for k, v in frozen.items()) and knobs["entry_clear_yards"] is None, "the survey report's estimate reads the same figures as before")
    check(not any(r["name"].startswith(("density_", "size_")) or r["name"] in ("elite_chance_pct", "solo_share_pct", "entry_clear_yards")
                  for r in read(TUN / "rift_survey.csv")), "rift_survey.csv no longer holds a figure the spawn sheets own")


# ---- the replay -------------------------------------------------------------------------------------------------------------

def test_mysql(port):
    command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root", "--batch",
               "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

    def sql(text, database=None):
        done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                              capture_output=True, encoding="utf-8")
        if done.returncode:
            raise RuntimeError(done.stderr)
        return done.stdout.rstrip("\n")

    text = (MODULE / "data/sql/db-world/updates" / G.NAME).read_text(encoding="utf-8")
    data = G.load()
    sql("CREATE DATABASE spawn_sheets CHARACTER SET utf8mb4;")
    sql(text, "spawn_sheets")
    sql(text, "spawn_sheets")
    count = lambda table: sql(f"SELECT COUNT(*) FROM `{table}`", "spawn_sheets")
    check(count("dc_monster_set") == "18" and count("dc_monster_spawn") == "65" and count("dc_area_default") == "3", "twice applied: 18 sets, 65 monsters, 3 tags")
    check(count("dc_cluster_recipe") == "8", "twice applied: 8 recipes")
    check(count("dc_monster_set_member") == str(sum(len(s["members"]) for s in data["sets"])), "twice applied: every set member read back")
    check(count("dc_monster_set_family") == str(sum(len(s["families"]) for s in data["sets"])), "twice applied: every set family read back")
    check(sql("SELECT COUNT(*) FROM dc_monster_set_member m LEFT JOIN dc_monster_spawn s ON s.monster=m.monster WHERE s.entry IS NULL", "spawn_sheets") == "0",
          "every set member is a monster with an entry")
    check(sql("SELECT monster FROM dc_monster_spawn WHERE entry IS NULL", "spawn_sheets") == "Decaying Cryptstalker", "only the held-back monster has no entry")
    check(sql("SELECT monster FROM dc_monster_spawn WHERE solo=1", "spawn_sheets") == "Savage", "Savage is the solo")
    # the clusterable flag, recomputed in SQL from the roles and the solo flag
    flagged = sql("SELECT COUNT(*) FROM dc_monster_set_family f WHERE f.clusterable = (EXISTS (SELECT 1 FROM dc_monster_set_member m JOIN dc_monster_spawn s ON s.monster=m.monster "
                  "WHERE m.set_id=f.set_id AND s.family=f.family AND s.role IN ('melee','ranged') AND s.solo=0))", "spawn_sheets")
    check(flagged == count("dc_monster_set_family"), "the clusterable flag equals melee or ranged and not solo, recomputed in SQL")
    check(sql("SELECT bodies_min, bodies_max FROM dc_cluster_recipe WHERE size='large' AND family='Swarm'", "spawn_sheets") == "3\t3", "Swarm's large recipe reads back as 3 to 3")
    check(sql("SELECT melee_min, melee_max FROM dc_cluster_recipe WHERE size='small' AND family='Swarm'", "spawn_sheets") == "2\t2", "Swarm's small recipe reads back as exactly 2 melee (q-1008-15)")
    check(sql("SELECT COUNT(*) FROM dc_cluster_recipe WHERE melee_min+ranged_min+caster_min+big_min > bodies_max "
              "OR melee_max+ranged_max+caster_max+big_max < bodies_min", "spawn_sheets") == "0", "every recipe row, Swarm's included, can make its bodies (recomputed in SQL)")
    sql("CREATE DATABASE spawn_mutant CHARACTER SET utf8mb4;")
    mutant = re.sub(r"^DELETE FROM `dc_monster_spawn`;$", "", text, count=1, flags=re.M)
    check(mutant != text, "the mutant removed the spawn DELETE")
    sql(mutant, "spawn_mutant")
    try:
        sql(mutant, "spawn_mutant")
    except RuntimeError:
        check(True, "mutant killed: without its DELETE the migration does not replay")
    else:
        raise AssertionError("a migration that keeps its old rows replayed")
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_rules_and_mutants()
    test_data()
    isolated(test_mysql)
