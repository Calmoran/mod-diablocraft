"""The legendary powers framework's Cube source (diablocraft-45rx5.1; Kanai's Cube plan bead 10, docs/research/kanais-cube.md 5.2 and 5.4).

The audit on the bead: point 4 (set counting of worn pieces only) was met; 1 and 3 partly; 2, 5, 6, 7, 8 missing. This file holds the rest.

  * 1 power id as the key: a legacy twin (same d3_name and rarity as a pool row, pool_version 'no') maps to its pool id; the map is read out of the
    real base_items.csv and compared with an independent grouping of it, and the real twins of the built owners are named;
  * 2 two sources, one set: ActivePowers puts the worn first and each power id once; AddCubed merges the cubed ones into the Situation the
    readers already take, so the real readers (ElementSum, ActiveValues with its conditions and stacks) answer with no change;
  * 3 PowerValues by source: the worn read is the item's stored roll, the Cube read is the top of the range (ItemPower::Best) whatever is stored;
  * 5 Built: the table has an item-owned row of the power, a stat-only power (Sun Keeper, The Furnace) included, a set bonus, a Bottomless
    potion and an unknown id not;
  * 6 class fit: the Cube contract's one rule (RollClass::Eligible, the function the `choose` verb calls: the pool item's usable_by and
    designated_class against the class key) against the sheet; a slot exists when dc_cube_slot_item (cube_slots.csv) names it, never by a count in
    C++ (diablocraft-xrtyn: driven with the sheet as it is and with copies that add and remove a slot);
  * 7 CubeContributionId: every slot 1..255 in 256..65535, below every item contribution id (itemGuid << 16 | seq, read from dc_items_data.cpp) and clear of
    the weapon source's 1 and 2 (read from dc_stats.cpp);
  * 8 no host: no reader of a power takes an Item; the contract lists every built row's reader;
  * the production helpers are compiled (tests/item_power_cube/harness.cpp) and driven with the generated rows; a mutant of each rule fails the
    same driver;
  * source-text guards for the server half (dc_item_powers.cpp), which cannot be compiled here: they prove the calls are there, not that they run;
    the C++ is compile-checked by syntax_check.sh and the checks are in docs/test-diablocraft-45rx5.1.md.
"""
import collections
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import crafting_source  # noqa: E402
import item_powers_source  # noqa: E402
import harness_env  # noqa: E402
import generate_sql  # noqa: E402
from test_item_power_math import all_rows, read_csv  # noqa: E402  (a module, so its test classes are not run twice)

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
ROLL = SRC / "items/dc_roll_class.h"
POWERS_CPP = item_powers_source.CPP
POWERS_H = SRC / "combat/dc_item_powers.h"
HARNESS = MODULE / "tests/item_power_cube/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
CONTRACT = REPO / "docs/contracts/legendary-powers.md"

MAGEFIST, BRACERS, AQUILA, SQUIRT = "P41_Unique_Gloves_014", "P61_Unique_Bracer_105", "P4_Unique_Chest_012", "P66_Unique_Amulet_010"
SUN_KEEPER, FURNACE = "Unique_Mace_1H_011_x1", "Unique_Mace_2H_103_x1"
WASTES = "Wrath of the Wastes"
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731

ROWS = all_rows()                                  # the generated table, 16 columns
BASES = read_csv("data/d3/base_items.csv")
POTIONS = {r["d3_id"] for r in read_csv("data/d3/legendary_potions.csv")}


def best(row):
    return row[5] if row[4] in ("resource_threshold_pct", "damage_generation_cut_pct") else row[6]   # the two numbers whose lower is the better


def key(row):
    # a row listing several skills (Oathkeeper) rolls once and stores under its first name (dc_item_power_math.h RollKey, FirstSkill)
    return "power:%s:%s" % (row[3].split(";")[0], row[4])


def item_rows(owner):
    """The item-owned rows of an owner, in table order: the source of every expected string below."""
    return [r for r in ROWS if r[0] == owner and not r[1]]


def values_of(owner, source, stored=()):
    """(skill, stat, value) of an owner's non-stat rows, as the sheet reads them: the stored roll of a ranged row (a worn item without one gives
    nothing), the table's number of a fixed one, the best end of the range when the Cube reads it."""
    out = []
    for r in item_rows(owner):
        if r[2] == "stat":
            continue
        if source == "cube":
            out.append((r[3], r[4], best(r)))
        elif r[5] < r[6]:
            found = dict(stored).get(key(r))
            if found is not None:
                out.append((r[3], r[4], found))
        else:
            out.append((r[3], r[4], r[5]))
    return "".join("%s:%s=%g;" % v for v in out)


def stored_cells(pairs):
    return [len(pairs)] + [c for pair in pairs for c in pair]


def built_owners():
    """Item-owned powers of the source sheet: data/legendary_powers.csv, the sheet the table is generated from (potions come from their own sheet)."""
    return sorted({r["owner"] for r in read_csv("data/legendary_powers.csv") if not r["pieces"]})


def twin_map():
    """Legacy id -> pool id, grouped independently of the C++: the pool row of the same name and rarity when there is exactly one."""
    pool = collections.defaultdict(list)
    for r in BASES:
        if r["pool_version"] == "yes":
            pool[(r["d3_name"], r["rarity"])].append(r["d3_id"])
    out = {}
    for r in BASES:
        found = pool[(r["d3_name"], r["rarity"])]
        out[r["d3_id"]] = found[0] if r["pool_version"] != "yes" and len(found) == 1 else r["d3_id"]
    return out


TWINS = twin_map()


def weapon_source_ids():
    found = re.search(r"WEAPON_APS_ID = (\d+), DUAL_WIELD_ID = (\d+);", (SRC / "stats/dc_stats.cpp").read_text(encoding="utf-8"))
    assert found
    return {int(found[1]), int(found[2])}


def item_id_shift():
    found = re.search(r"std::uint64_t ContributionId\(std::uint64_t itemGuid, unsigned seq\)\s*\{\s*return \(itemGuid << (\d+)\) \| seq;",
                      items_source.read("dc_items_data.cpp"))
    assert found
    return int(found[1])


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def mutate(source, old, new):
    assert source.count(old) == 1, "mutation target %r is not there exactly once" % old
    return source.replace(old, new)


SLOT_SAMPLES = (0, 1, 2, 3, 4, 255, 256)


def slot_numbers():
    """The Cube's slot numbers, from data/d3/cube_slots.csv (the world table dc_cube_slot_item is its render)."""
    return sorted({int(r["slot"]) for r in read_csv("data/d3/cube_slots.csv")})


def classes():
    return {r["d3_class"].strip().lower(): 1 << (int(r["wow_class_id"]) - 1) for r in read_csv("data/d3/class_map.csv")}


def cases():
    out = [(T("row", *r), None) for r in ROWS]
    out += [(T("base", r["d3_id"], r["d3_name"], r["rarity"], 1 if r["pool_version"] == "yes" else 0), None) for r in BASES]
    # fixtures: a name two pool rows share maps nothing; a power with a stat row on a twin
    out += [(T("base", "Amb_A", "Ambiguous", "legendary", 1), None), (T("base", "Amb_B", "Ambiguous", "legendary", 1), None),
            (T("base", "Amb_L", "Ambiguous", "legendary", 0), None), (T("base", "Fix_Pool", "Fixture", "legendary", 1), None),
            (T("base", "Fix_Twin", "Fixture", "legendary", 0), None), (T("base", "Fix_Eth", "Fixture", "ethereal", 1), None),
            (T("row", "Fix_Pool", 0, "stat", "", "edmg", 5, 9, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0), None)]
    # 1 the key: every base id, and the rows a twin owns
    out += [(T("powerid", r["d3_id"]), TWINS[r["d3_id"]]) for r in BASES]
    out += [(T("powerid", "Amb_L"), "Amb_L"), (T("powerid", "Fix_Twin"), "Fix_Pool"), (T("powerid", "No_Such_Item"), "No_Such_Item")]
    for owner in built_owners():
        for legacy in [i for i, pool in TWINS.items() if pool == owner and i != owner]:
            want = "".join("%s:%s:%s:%s;" % (legacy, r[2], r[3], r[4]) for r in item_rows(owner))
            out.append((T("rowsof", legacy), want))
        out.append((T("rowsof", owner), "".join("%s:%s:%s:%s;" % (owner, r[2], r[3], r[4]) for r in item_rows(owner))))
    out += [(T("rowsof", "Fix_Twin"), "Fix_Twin:stat::edmg;"), (T("statsof", "Fix_Twin"), "Fix_Twin:stat::edmg;"),
            (T("statsof", "Fix_Pool"), "Fix_Pool:stat::edmg;"), (T("statsof", "Amb_L"), ""), (T("rowsof", "Amb_L"), ""),
            (T("statsof", SUN_KEEPER), "%s:stat::edmg;" % SUN_KEEPER), (T("rowsof", WASTES), "")]
    # 5 built: item-owned rows of any kind but a potion's, stat-only included; not a set bonus, not a potion, not an unknown id
    owners = set(built_owners())
    out += [(T("built", i), "1" if i in owners else "0") for i in sorted({r["d3_id"] for r in BASES} | POTIONS | {WASTES, "Nope"})]
    # 3 values by source
    for owner in sorted(owners - {SUN_KEEPER, FURNACE}):
        ranged = [(key(r), (r[5] + r[6]) / 2) for r in item_rows(owner) if r[5] < r[6]]
        low = [(key(r), r[5]) for r in item_rows(owner) if r[5] < r[6]]
        out.append((T("values", "cube", owner, *stored_cells(low)), values_of(owner, "cube")))        # the stored roll is not read
        out.append((T("values", "cube", owner, *stored_cells([])), values_of(owner, "cube")))
        out.append((T("values", "worn", owner, *stored_cells(ranged)), values_of(owner, "worn", ranged)))
        out.append((T("values", "worn", owner, *stored_cells([])), values_of(owner, "worn")))
    out += [(T("values", "cube", SUN_KEEPER, *stored_cells([])), ""), (T("values", "worn", FURNACE, *stored_cells([])), "")]
    # 2 ActivePowers: worn first, each id once, an unbuilt power dropped
    roll = [("power:fire:damage_pct", 17)]
    worn_magefist = [MAGEFIST, *stored_cells(roll)]
    worn_bracers = [BRACERS, *stored_cells([("power:Hammer of the Ancients:damage_increase_pct", 400)])]
    out += [(T("active", 1, *worn_magefist, 5, MAGEFIST, BRACERS, MAGEFIST, "Fix_Nothing", BRACERS), "%s/W/1;%s/C/2;" % (MAGEFIST, BRACERS)),
            (T("active", 0, 2, BRACERS, MAGEFIST), "%s/C/2;%s/C/1;" % (BRACERS, MAGEFIST)),
            (T("active", 2, *worn_bracers, *worn_magefist, 2, MAGEFIST, SQUIRT), "%s/W/2;%s/W/1;%s/C/2;" % (BRACERS, MAGEFIST, SQUIRT)),
            (T("active", 2, *worn_magefist, MAGEFIST, *stored_cells([("power:fire:damage_pct", 15)]), 0), "%s/W/1;" % MAGEFIST),
            (T("active", 1, SUN_KEEPER, *stored_cells([]), 1, SUN_KEEPER), "%s/W/0;" % SUN_KEEPER),
            (T("active", 0, 1, SUN_KEEPER), "%s/C/0;" % SUN_KEEPER), (T("active", 0, 2, WASTES, "Nope"), ""), (T("active", 0, 0), "")]
    # 2 merged into the situation the readers take. A Magefist roll 17 worn beside a cubed one: the worn number, not the sum, not the top
    elem = T("sum", "element", "fire", "damage_pct")
    out += [(T("clear"), None), (T("worn", MAGEFIST, 100, *stored_cells(roll)), None), (T("cubed", MAGEFIST, 500), None), (T("merge"), None),
            (elem, "17"), (T("since"), "%s=100;" % MAGEFIST)]
    out += [(T("clear"), None), (T("cubed", MAGEFIST, 500), None), (T("merge"), None), (elem, "20"), (T("since"), "%s=500;" % MAGEFIST)]
    out += [(T("clear"), None), (T("cubed", MAGEFIST, 500), None), (T("cubed", MAGEFIST, 700), None), (T("merge"), None), (elem, "20"),
            (T("since"), "%s=500;" % MAGEFIST)]
    out += [(T("clear"), None), (T("cubed", "Nope", 500), None), (T("cubed", WASTES, 500), None), (T("merge"), None), (elem, "0"), (T("since"), "")]
    out += [(T("clear"), None), (T("merge"), None), (elem, "0"), (T("since"), "")]
    # a cubed power with a condition on its own roll: Aquila Cuirass reads the top of its range, the LOWER number (90), and the worn copy first
    reduction = T("sum", "player", "", "damage_reduction_pct")
    out += [(T("clear"), None), (T("cubed", AQUILA, 0), None), (T("merge"), None)]
    out += [(T("resource", pct), None) if i % 2 == 0 else (reduction, want) for pct, want in ((92, "50"), (90, "50"), (89, "0"), (100, "50"))
            for i in (0, 1)]
    out += [(T("clear"), None), (T("worn", AQUILA, 0, *stored_cells([("power::resource_threshold_pct", 95)])), None), (T("cubed", AQUILA, 0), None),
            (T("merge"), None), (T("resource", 92), None), (reduction, "0"), (T("resource", 96), None), (reduction, "50")]
    # a cubed power that counts from the moment it was chosen: Squirt's Necklace, a stack a second
    dealt = T("sum", "player", "", "damage_dealt_pct")
    out += [(T("clear"), None), (T("cubed", SQUIRT, 1000), None), (T("merge"), None), (T("now", 5500), None), (dealt, "40"),
            (T("now", 1000), None), (dealt, "0"), (T("now", 100000), None), (dealt, "100"), (T("since"), "%s=1000;" % SQUIRT)]
    out.append((T("clear"), None))
    # 7 the contribution id space: every (slot, seq) a slot number can have, and the ones it cannot
    for slot in SLOT_SAMPLES:
        for seq in (0, 1, 127, 255, 256):
            out.append((T("cubeid", slot, seq), None))
    # 6 class fit: the one rule of the `choose` verb (usable_by and designated_class against the class key), worked out from the sheet's lists
    out += [(T("fit", "-", "-", "wizard"), "1"), (T("fit", "-", "-", "-"), "0"), (T("fit", "wizard;barbarian", "-", "barbarian"), "1"),
            (T("fit", "wizard", "-", "barbarian"), "0"), (T("fit", "-", "wizard", "barbarian"), "0"), (T("fit", "wizard", "wizard", "wizard"), "1")]
    for owner in sorted(owners):
        base = next(r for r in BASES if r["d3_id"] == owner)
        for name in classes():
            out.append((T("fit", base["usable_by"] or "-", base["designated_class"] or "-", name),
                        "1" if ((not base["usable_by"] or name in base["usable_by"].split(";")) and
                                (not base["designated_class"] or base["designated_class"] == name)) else "0"))
    # the Cube's slots: the numbers cube_slots.csv names, as it is and as copies that add a slot and drop one would be (nothing counts them in C++)
    for sheet in (slot_numbers(), slot_numbers() + [4], [n for n in slot_numbers() if n != 3], slot_numbers() + [4, 7]):
        for slot in range(0, 9):
            out.append((T("slotok", slot, *sheet), "1" if slot in sheet else "0"))
    return out


def ids_verdict(lines):
    """The cube ids as properties (the contract's), not as a formula: 'ok' when every valid one is in 256..65535, distinct, clear of the weapon
    source and below the first item contribution id, and every invalid one is 0."""
    got = {}
    for (slot, seq), value in zip([(s, q) for s in SLOT_SAMPLES for q in (0, 1, 127, 255, 256)], lines):
        got[(slot, seq)] = int(value)
    valid = {k: v for k, v in got.items() if 1 <= k[0] <= 255 and k[1] <= 255}
    first_item = 1 << item_id_shift()
    return (all(256 <= v < first_item and v <= 65535 for v in valid.values()), len(set(valid.values())) == len(valid),
            not (set(valid.values()) & weapon_source_ids()), all(v == 0 for k, v in got.items() if k not in valid), len(valid))


IDS_OK = (True, True, True, True, 5 * 4)   # five valid sampled slots (1 to 4 and 255) x four valid sampled seqs (seq 256 is not one)


def build(math_text, name, roll_text=None):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    files = {"items/dc_roll_class.h": roll_text if roll_text is not None else ROLL.read_text(encoding="utf-8"), "combat/dc_item_power_math.h": math_text}
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
    work = Path(tempfile.mkdtemp(prefix="cube-%s-" % name, dir=str(SCRATCH)))
    return work, binary


def drive(math_text, name, roll_text=None):
    """(wanted, got): the answers of every case with an expectation, then the cube id verdict."""
    todo = cases()
    work, binary = build(math_text, name, roll_text)
    try:
        (work / "cases.txt").write_text("\n".join(line for line, _ in todo) + "\n", encoding="utf-8")
        run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        if run.returncode:
            raise AssertionError("harness failed (%s):\n%s" % (run.returncode, run.stderr[-2000:]))
        answers = run.stdout.split("\n")[:-1]
    finally:
        shutil.rmtree(work, ignore_errors=True)
    printing = [(line, want) for line, want in todo if line.split("\t")[0] in
                ("powerid", "built", "values", "rowsof", "statsof", "active", "sum", "since", "cubeid", "fit", "slotok")]
    assert len(printing) == len(answers), (len(printing), len(answers))
    wanted, got, ids = [], [], []
    for (line, want), answer in zip(printing, answers):
        if line.startswith("cubeid"):
            ids.append(answer)
        else:
            wanted.append(want)
            got.append(answer)
    return wanted + [IDS_OK], got + [ids_verdict(ids)]


class Sources(unittest.TestCase):
    def test_the_production_helpers_agree_with_the_sheets(self):
        wanted, got = drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(wanted), 2000)
        self.assertEqual(wanted, got)

    def test_the_twins_of_the_built_owners_are_real_and_named(self):
        # the audit counted 16 twins of 21 owners; measured on this tree: every legacy twin of a built owner, with its pool row, in the sheet
        twins = {legacy: pool for legacy, pool in TWINS.items() if pool != legacy and pool in built_owners()}
        owners_with_twin = set(twins.values())
        self.assertIn("Unique_Gloves_014_x1", twins)                       # Magefist, the bead's example
        self.assertEqual(MAGEFIST, twins["Unique_Gloves_014_x1"])
        self.assertTrue(owners_with_twin <= set(built_owners()))
        for pool in owners_with_twin:                                     # one pool row per name, checked
            name = next(r["d3_name"] for r in BASES if r["d3_id"] == pool)
            self.assertEqual([pool], [r["d3_id"] for r in BASES if r["d3_name"] == name and r["pool_version"] == "yes"])
        for legacy in twins:
            row = next(r for r in BASES if r["d3_id"] == legacy)
            pool = next(r for r in BASES if r["d3_id"] == twins[legacy])
            self.assertEqual(("no", pool["d3_name"], pool["rarity"], pool["slot"]), (row["pool_version"], row["d3_name"], row["rarity"], row["slot"]))
        # an ethereal pool row is not the twin of a legendary legacy row of its name
        for r in BASES:
            if r["pool_version"] != "yes" and r["rarity"] == "legendary":
                eth = [p for p in BASES if p["d3_name"] == r["d3_name"] and p["pool_version"] == "yes" and p["rarity"] == "ethereal"]
                if eth:
                    self.assertEqual(r["d3_id"], TWINS[r["d3_id"]])

    def test_the_potion_and_set_owners_are_not_item_powers(self):
        self.assertTrue(POTIONS)
        self.assertFalse(POTIONS & set(built_owners()))
        self.assertTrue(any(r[0] == WASTES and r[1] for r in ROWS))
        self.assertEqual({r[0] for r in ROWS if not r[1] and r[2] != "potion"}, set(built_owners()))        # the generated table is the sheet
        self.assertIn(SUN_KEEPER, built_owners())
        self.assertIn(FURNACE, built_owners())

    def test_the_contribution_id_space_is_clear_of_the_other_sources(self):
        self.assertEqual(16, item_id_shift())                               # itemGuid << 16 | seq, and an item guid is never 0
        self.assertEqual({1, 2}, weapon_source_ids())
        self.assertLess(max(weapon_source_ids()), 256)

    def test_class_fit_rule_is_the_choose_verbs_lists(self):
        # the sheet says who wears each built owner; the two playable classes tell the cases something
        owners = built_owners()
        fits = [(o, c) for o in owners for c in classes()
                for r in [next(b for b in BASES if b["d3_id"] == o)]
                if (not r["usable_by"] or c in r["usable_by"].split(";")) and (not r["designated_class"] or r["designated_class"] == c)]
        self.assertTrue(any(c == "wizard" for _, c in fits) and any(c == "barbarian" for _, c in fits))
        self.assertLess(len(fits), len(owners) * len(classes()))          # some power is closed to a class, so the rule is not a constant

    def test_the_mutants_fail_the_same_driver(self):
        math = MATH.read_text(encoding="utf-8")
        wanted, _ = drive(math, "baseline")
        worn_loop = "for (Active const& power : worn)\n            if (!Has(out, power.id))\n                out.push_back(power);\n        "
        cube_loop = ("for (std::string const& id : cubed)\n            if (!Has(out, id) && Built(rows, id))\n"
                     "                out.push_back({id, Source::Cube, PowerValues(rows, id, Source::Cube, {})});\n        ")
        mutants = {
            # 3 the Cube reads the top of the range
            "cube_reads_the_stored_roll": mutate(math, "if (source == Source::Worn)\n            return WornValues(rows, powerId, stored);",
                                                 "if (true)\n            return WornValues(rows, powerId, stored);"),
            "cube_reads_the_bottom": mutate(math, "out.push_back({row.skill, row.stat, Best(row), powerId, !Rolls(row)});",
                                            "out.push_back({row.skill, row.stat, row.min, powerId, !Rolls(row)});"),
            "worn_reads_the_top": mutate(math, "if (source == Source::Worn)\n            return WornValues(rows, powerId, stored);",
                                         "if (source == Source::Worn)\n            return PowerValues(rows, powerId, Source::Cube, stored);"),
            # 2 worn first, each id once, built only
            "worn_is_not_first": mutate(math, worn_loop + cube_loop, cube_loop + worn_loop),
            "a_cubed_copy_of_a_worn_power_counts_again": mutate(math, "if (!Has(out, id) && Built(rows, id))", "if (Built(rows, id))"),
            "a_worn_copy_counts_twice": mutate(math, "if (!Has(out, power.id))", "if (true)"),
            "an_unbuilt_cube_choice_counts": mutate(math, "if (!Has(out, id) && Built(rows, id))", "if (!Has(out, id))"),
            "the_cube_is_not_merged_into_the_situation": mutate(math, "situation.itemValues[power.id] = power.values;", ""),
            "the_cubed_power_has_no_moment": mutate(math, "situation.wornSince[power.id] = SinceOf(cubed, power.id);", ""),
            "the_cubed_power_takes_the_choice_moment_of_nothing": mutate(math, "situation.wornSince[power.id] = SinceOf(cubed, power.id);",
                                                                         "situation.wornSince[power.id] = 0;"),
            "a_cubed_copy_replaces_the_worn_one": mutate(math, "if (power.source == Source::Cube)", "if (true)"),
            # 1 the key
            "a_twin_is_not_mapped": mutate(math, "return found == ids.end() ? d3Id : found->second;", "return d3Id;"),
            "a_twin_ignores_the_rarity": mutate(math, "std::make_pair(item.name, item.rarity)", "std::make_pair(item.name, std::string())"),
            "an_ambiguous_name_maps_to_the_first": mutate(math, "found->second.size() == 1", "!found->second.empty()"),
            "the_rows_keep_the_pool_owner": mutate(math, "row.owner = owner;", ""),
            "the_rows_are_not_mapped": mutate(math, "std::string const powerId = PowerId(ids, d3Id);", "std::string const powerId = d3Id;"),
            "the_stats_are_not_mapped": mutate(math, "ItemStats(rows, PowerId(ids, d3Id))", "ItemStats(rows, d3Id)"),
            # 5 built
            "a_set_bonus_is_built": mutate(math, "row.owner == powerId && !row.pieces && row.kind != \"potion\"", "row.owner == powerId && row.kind != \"potion\""),
            "a_stat_only_power_is_unbuilt": mutate(math, "row.owner == powerId && !row.pieces && row.kind != \"potion\"",
                                                   "row.owner == powerId && !row.pieces && row.kind != \"potion\" && row.kind != \"stat\""),
            "a_potion_is_built": mutate(math, "row.owner == powerId && !row.pieces && row.kind != \"potion\"", "row.owner == powerId && !row.pieces"),
            # 7 the id space
            "slot_zero_is_a_slot": mutate(math, "if (slot < 1 || slot > CubeSlotLimit", "if (slot > CubeSlotLimit"),
            "a_256th_slot_has_an_id": mutate(math, "slot > CubeSlotLimit", "slot > CubeSlotLimit + 1"),
            "the_slots_are_three": mutate(math, "return std::find(slots.begin(), slots.end(), slot) != slots.end();", "return slot >= 1 && slot <= 3;"),
            "every_slot_exists": mutate(math, "return std::find(slots.begin(), slots.end(), slot) != slots.end();", "return true;"),
            "the_slot_shift_is_too_small": mutate(math, "return (slot << 8) | seq;", "return (slot << 4) | seq;"),
            "the_slot_shift_is_item_wide": mutate(math, "return (slot << 8) | seq;", "return (slot << 16) | seq;"),
            "a_seq_overflows_its_slot": mutate(math, "seq > 255", "seq > 256"),
            # 6 class fit
        }
        for name, mutant in mutants.items():
            self.assertNotEqual(math, mutant, "the %s mutation no longer applies" % name)
            _, got = drive(mutant, name)
            self.assertNotEqual(wanted, got, "mutant %s passed" % name)
        # the class rule is RollClass::Eligible, the function `choose` also calls: a change to it must show in the sheet's lists
        roll = ROLL.read_text(encoding="utf-8")
        for name, a, b in (("the_designated_class_is_ignored", "(designated.empty() || designated == rollClass)", "true"),
                           ("the_usable_list_is_ignored", "(usableBy.empty() || Lists(usableBy, rollClass))", "true"),
                           ("an_empty_class_fits", "!rollClass.empty() && ", "")):
            self.assertEqual(1, roll.count(a), name + " no longer applies")
            _, got = drive(math, name, roll.replace(a, b))
            self.assertNotEqual(wanted, got, "mutant %s passed" % name)


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cpp = POWERS_CPP.read_text(encoding="utf-8")
        cls.header = POWERS_H.read_text(encoding="utf-8")
        cls.math = MATH.read_text(encoding="utf-8")

    def test_the_twin_map_is_read_from_the_base_items_and_keys_the_owners(self):
        data = definition("Table const& Data()", self.cpp)
        self.assertIn("SELECT entry, d3_id, d3_name, rarity, pool_version, usable_by, designated_class FROM dc_base_item", data)
        self.assertIn("ItemPower::PowerIds(items)", data)
        self.assertIn("loaded.owners[entry] = powerId;", data)
        self.assertIn("ItemPower::Built(loaded.rows, powerId)", data)                       # the stat-only powers are owners too
        self.assertIn("loaded.sweep.insert(entry);", data)                                   # the login sweep still reads the rolling ones only
        self.assertIn("return Data().sweep.count(entry) != 0;", definition("bool HasItemPower(std::uint32_t entry)", self.cpp))
        self.assertIn("return ItemPower::RowsOf(Data().rows, Data().ids, d3Id);", definition("std::vector<ItemPower::Row> ItemRows(", self.cpp))
        self.assertIn("return ItemPower::StatsOf(Data().rows, Data().ids, d3Id);", definition("std::vector<ItemPower::Row> ItemStats(", self.cpp))

    def test_the_cube_list_is_merged_where_every_reader_takes_the_situation(self):
        start = self.cpp.index("ItemPower::Situation SituationOf(")
        situation = self.cpp[start:self.cpp.index("\n        }\n", start)]                         # the signature has a default argument `{}`
        self.assertIn("ItemPower::AddCubed(situation, Data().rows, CubedOf(guid));", situation)
        self.assertLess(situation.index("situation.itemValues[value.owner].push_back(value);"), situation.index("ItemPower::AddCubed("))   # worn first
        # a chosen power puts the player in play: Seen and Fire skip a player with no clock and no count
        setter = definition("bool CubeSet(Player* player", self.cpp)
        self.assertIn("clocks[guid];", setter)
        for line in ("!ItemPower::CubeSlotExists(Data().cubeSlots, slot)", "!Built(powerId)", "!ClassMayChoose(player, powerId)"):
            self.assertIn(line, setter)
        self.assertIn("CubeChanged(player);", setter)
        self.assertIn("CubeChanged(player);", definition("void CubeClear(Player* player", self.cpp))
        changed = definition("void CubeChanged(Player* player)", self.cpp)
        self.assertEqual(["Immunize(player);", "CostAuras(player);", "DropStacks(player);"], re.findall(r"\w+\(player\);", changed))
        self.assertIn("cubes.erase(player->GetGUID().GetRawValue());", definition("void OnPlayerLogout(Player* player) override", self.cpp))

    def test_the_cube_never_counts_as_a_worn_piece(self):
        # point 4: the set counts come from the worn equipment slots only
        worn = definition("std::vector<ItemPower::Piece> Worn(Player* player", self.cpp)
        self.assertIn("GetItemByPos(INVENTORY_SLOT_BAG_0, slot)", worn)
        self.assertNotIn("cube", worn.lower())
        self.assertNotIn("cube", definition("unsigned SetCount(Player const* player", self.cpp).lower())
        refresh = definition("void Refresh(Player* player, Item* changed", self.cpp)
        self.assertEqual(0, refresh.lower().count("cube"))

    def test_the_stacking_buffs_follow_the_powers_in_play(self):
        drop = definition("void DropStacks(Player* player)", self.cpp)
        self.assertIn("clocks[player->GetGUID().GetRawValue()].wornSince", drop)
        self.assertIn("for (ItemPower::Cubed const& one : CubedOf(player->GetGUID().GetRawValue()))\n                    on.insert(one.id);", drop)

    def test_the_choice_functions_are_declared_for_the_archive(self):
        for line in ("bool CubeSet(Player*, unsigned slot, std::string const& powerId);", "void CubeClear(Player*, unsigned slot);",
                     "std::vector<std::string> Cubed(Player const*);", "std::vector<ItemPower::Active> ActivePowers(Player const*);",
                     "bool Built(std::string const& powerId);", "bool ClassMayChoose(Player const*, std::string const& powerId);",
                     "std::string PowerIdOf(std::string const& d3Id);"):
            self.assertIn(line, self.header)
        fit = definition("bool ClassMayChoose(Player const* player", self.cpp)
        self.assertIn("RollClass::Eligible(found->second.first, found->second.second, Items::ClassKeyOf(player->getClass()))", fit)
        self.assertNotIn("AllowableClass", fit)                       # the mask is not our rule: `choose` reads usable_by and designated_class

    def test_the_slots_and_the_class_rule_are_the_choose_verbs(self):
        # diablocraft-xrtyn: the Cube contract's rules, shared and not copied: one class function, one slot table
        crafting = crafting_source.read("dc_cube.cpp")
        choose = definition("void ChooseCubePower(Player* player", crafting)
        self.assertIn("RollClass::Eligible(", choose)
        self.assertIn("Items::ClassKeyOf(player->getClass())", choose)
        self.assertIn("FROM dc_cube_slot_item", definition("std::vector<Window::CubeSlot> CubeSlots(Player* player", crafting))
        math = MATH.read_text(encoding="utf-8")
        self.assertNotIn("AllowableClass", math)
        self.assertIn('WorldDatabase.Query("SELECT DISTINCT slot FROM dc_cube_slot_item ORDER BY slot")', self.cpp)
        self.assertNotRegex(self.cpp + math, r"\bCubeSlots\b")        # no count of slots in the framework
        self.assertNotRegex(self.cpp + math, r"slot\s*(>|<=)\s*3\b")

    def test_no_reader_of_a_power_takes_the_host_item(self):
        # kanais-cube.md 5.4: nothing a cubed power reads may need the host item's object. The only functions of the header that see an
        # item are the equip hook (Refresh) and the roller's table reads; every reader takes a Player (or nothing).
        decls = [l.strip() for l in self.header.splitlines() if re.match(r"\s+[\w:<>,\s&*]+\(.*\);", l)]
        with_item = [l for l in decls if re.search(r"\bItem\b|\bInstance\b", l)]
        self.assertEqual(["void Refresh(Player*, Item* changed, bool equipping, DC::Items::Instance const& instance);"],
                         [re.sub(r"\s+", " ", l) for l in with_item])
        self.assertNotRegex(self.math, r"\bItem\*|\bItem const\*|\bItem&")                      # the pure half has no item object either
        self.assertNotIn("changed", definition("ItemPower::Situation Seen(Player const* player)", self.cpp))

    def test_the_contract_names_every_built_rows_reader(self):
        text = CONTRACT.read_text(encoding="utf-8")
        start = text.index("## The Cube source")
        section = text[start:text.index("\n## ", start + 4)]
        self.assertIn("no host", section.lower())
        for owner in built_owners():
            self.assertIn(owner, section, owner)
        stats = {(r["kind"], r["stat"]) for r in read_csv("data/legendary_powers.csv") if not r["pieces"] and r["stat"]}
        for _, stat in stats:
            self.assertIn(stat, section, stat)
        for name in ("CubeSet", "CubeClear", "Cubed", "ActivePowers", "Built", "ClassMayChoose", "PowerIdOf", "CubeContributionId", "AddCubed"):
            self.assertIn(name, section, name)

    def test_the_server_mutants_fail_the_guards(self):
        # the server half cannot be compiled here, so each line the guards pin is dropped in memory and some guard above must notice
        checks = [getattr(self, name) for name in sorted(dir(self)) if name.startswith("test_") and name != "test_the_server_mutants_fail_the_guards"]
        cpp, header = self.cpp, self.header
        no = lambda old, new: (mutate(cpp, old, new), header)  # noqa: E731
        mutants = {
            "the_cube_is_not_merged": no("ItemPower::AddCubed(situation, Data().rows, CubedOf(guid));", ""),
            "an_unbuilt_power_can_be_chosen": no(" || !Built(powerId)", ""),
            "the_class_is_not_asked": no(" || !ClassMayChoose(player, powerId)", ""),
            "the_chosen_power_is_not_in_play": no("clocks[guid]; //", "//"),
            "a_change_redoes_nothing": no("CubeChanged(player);\n        return true;", "return true;"),
            "a_change_leaves_the_cost_auras": no("            Immunize(player);\n            CostAuras(player);\n            DropStacks(player);\n",
                                                 "            Immunize(player);\n            DropStacks(player);\n"),
            "the_cube_survives_logout": no("                cubes.erase(player->GetGUID().GetRawValue());\n", ""),
            "a_twin_owns_nothing": no("loaded.owners[entry] = powerId;", "loaded.owners[entry] = entries[at].second;"),
            "the_stat_only_powers_are_not_owners": no("if (!ItemPower::Built(loaded.rows, powerId))", "if (loaded.sweep.count(entry) == 0 && !loaded.owners.count(entry) && false)"),
            "the_cubed_buffs_are_dropped": no("                for (ItemPower::Cubed const& one : CubedOf(player->GetGUID().GetRawValue()))\n                    on.insert(one.id);\n", ""),
            "the_sweep_reads_the_owners": no("return Data().sweep.count(entry) != 0;", "return Data().owners.count(entry) != 0;"),
            "the_roller_gets_no_twin_rows": no("return ItemPower::RowsOf(Data().rows, Data().ids, d3Id);", "return ItemPower::RowsOf(Data().rows, {}, d3Id);"),
            "the_cube_counts_as_worn_pieces": no("counts[guid] = now;", "counts[guid] = now; cubes.clear();"),
            "the_class_rule_is_our_own": no("RollClass::Eligible(found->second.first, found->second.second, Items::ClassKeyOf(player->getClass()))", "true"),
            "the_slots_are_three_again": no("!ItemPower::CubeSlotExists(Data().cubeSlots, slot)", "slot < 1 || slot > 3"),
            "a_reader_takes_the_host": (cpp, mutate(header, "bool Built(std::string const& powerId);", "bool Built(std::string const& powerId, Item* host);")),
        }
        for name, (mutated, head) in mutants.items():
            self.cpp, self.header = mutated, head
            try:
                caught = False
                for check in checks:
                    try:
                        check()
                    except (AssertionError, ValueError):
                        caught = True
                        break
            finally:
                del self.cpp, self.header
            self.assertTrue(caught, "server mutant %s passed every guard" % name)


if __name__ == "__main__":
    unittest.main()
