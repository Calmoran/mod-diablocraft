"""Legendary 052, bead diablocraft-zqlje: Ahavarion, Spear of Lycander (staff, any class), the pieces N-CTF and N-PYLON.

  "Chance on killing a demon to gain a random Shrine effect."
  * the words are d3planner's (item_twohand.js, leg_ahvarion, args 0: no number) and the catalogue's. The Power file
    (ItemPassive_Unique_Ring_672_x1.pow, docs/research/legendary-pow-data.csv) has one number, SF_0 Chance % = 0.005, in a unit it does not state;
    the CHANCE is therefore the combat tunable ahavarion_chance_pct, the value the designer's 10 (card q-1016-20; a blank would read 0:
    the power does nothing until he sets it). The shrine's seconds are the shrine rows' own (shrine_<kind>_seconds);
  * the table holds ONE `effect` row, `random_shrine` 1 on `kill` under the condition `target_creature_type` = demon (N-CTF: the condition is data,
    its types the row's cond_skills, so a later item names others); the generator refuses a bad one; the generated SQL and the committed migration
    are what the generator renders, and the migration is the newest full table;
  * the creature type names are the core's CreatureType enum (SharedDefines.h) by number; the kinds a random shrine can be are the buff sheet's
    shrines (data/pylon_buffs.csv), the pylons never, and every one of them has the seconds its Give needs; the Bandit Shrine (data/d3/pylons.csv)
    gives no buff on the player and is not a kind;
  * the production rules (dc_item_power_math.h Fire and CreatureTypeName, dc_pylon_math.h RandomShrine) are compiled and driven with the generated
    rows; mutants fail the same driver;
  * source-text guards hold the executor (outside the lock, the tunable, the hit's coefficient), the killed creature handed to the event, its type
    read before the lock, the enum assertion and the shrine call; mutants fail them. The C++ is compile-checked by syntax_check.sh; the in-game
    steps are in docs/test-diablocraft-zqlje.md.
"""
import csv
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402
import generate_tunables  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
PYLON_MATH = SRC / "combat/dc_pylon_math.h"
HARNESS = MODULE / "tests/item_power_ahavarion/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Staff_101_x1"
OTHER = "Unique_Gloves_003_x1"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
WANT_ROW = (OWNER, 0, "effect", "", "random_shrine", 1.0, 1.0, "target_creature_type", 0.0, "demon", 0.0, 0, "kill", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv_path(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def read_csv(name):
    return read_csv_path(MODULE / name)


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def core_creature_types():
    """{number: lower-case name} out of the core's own CreatureType enum."""
    text = (REPO / "azerothcore-wotlk/src/server/shared/SharedDefines.h").read_text(encoding="utf-8")
    body = text[text.index("enum CreatureType\n"):]
    body = body[:body.index("};")]
    return {int(m[2]): m[1].lower() for m in re.finditer(r"CREATURE_TYPE_(\w+)\s*=\s*(\d+)", body)}


def shrine_kinds():
    """The buff sheet's shrines, in sheet (Kind) order."""
    return [r["kind"] for r in read_csv("data/pylon_buffs.csv") if r["group"] == "shrine"]


def mutate(source, old, new):
    assert source.count(old) == 1, "mutation target %r is not there exactly once" % old
    return source.replace(old, new)


class Table(unittest.TestCase):
    def test_the_words_are_the_planners_and_the_item_is_a_pool_legendary(self):
        text = (REPO / "reference/d3planner/item_twohand.js").read_text(encoding="utf-8")
        start = text.index('id: "%s"' % OWNER)
        item = text[start:text.index("},\n", text.index("preset", start))]
        self.assertIn('id: "leg_ahvarion"', item)
        self.assertIn('format: "Chance on killing a demon to gain a random Shrine effect.", args: 0', item)
        row = next(r for r in read_csv_path(REPO / "docs/research/legendary-catalogue.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Chance on killing a demon to gain a random Shrine effect.", "K3", "any"), (row["power_text"], row["kind"], row["class"]))
        base = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Ahavarion, Spear of Lycander", "legendary", "yes"), (base["d3_name"], base["rarity"], base["pool_version"]))

    def test_the_chance_is_alexs_ten_percent(self):
        pow_row = next(r for r in read_csv_path(REPO / "docs/research/legendary-pow-data.csv") if "Unique_Staff_101_x1" in "".join(r.values()))
        self.assertIn("SF_0 Chance % = 0.005", "".join(pow_row.values()))   # the only number the source has, with no unit
        row = next(r for r in read_csv("data/tunables/combat.csv") if r["name"] == "ahavarion_chance_pct")
        self.assertEqual(("", "10", "percent"), (row["d3_value"], row["value"], row["unit"]))   # card q-1016-20
        for need in ("Ahavarion", "SF_0 Chance % = 0.005", "q-1016-20"):
            self.assertIn(need, row["notes"])
        migration = (MODULE / "data/sql/db-world/updates" / generate_tunables.CURRENT_MIGRATION).read_text(encoding="utf-8")
        self.assertIn("('combat', 'ahavarion_chance_pct', NULL, 10.0, 'percent', ", migration)
        self.assertEqual(migration, (MODULE / "data/generated" / generate_tunables.CURRENT_MIGRATION).read_text(encoding="utf-8"))

    def test_one_effect_row_on_the_kill_of_a_demon(self):
        self.assertEqual([WANT_ROW], mine())

    def test_the_row_carries_no_chance_and_has_its_source(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertEqual(("", "", ""), (rows[0]["chance_pct"], rows[0]["icd_seconds"], rows[0]["fire_skills"]))
        for need in ("item_twohand.js", "leg_ahvarion", "ItemPassive_Unique_Ring_672_x1.pow", "ahavarion_chance_pct", "pylons.csv", "diablocraft-zqlje"):
            self.assertIn(need, rows[0]["source"])
        self.assertTrue(rows[0]["note"])

    def test_the_kinds_a_random_shrine_can_be_are_the_shrines_with_a_buff(self):
        d3 = read_csv("data/d3/pylons.csv")
        d3_shrines = {r["name"].replace(" Shrine", "").lower() for r in d3 if r["type"] == "shrine"}
        kinds = shrine_kinds()
        self.assertEqual(6, len(kinds))
        # every buff-sheet shrine is a D3 shrine; the one D3 shrine left over spawns goblins and gives the player no buff
        self.assertEqual({"bandit"}, d3_shrines - set(kinds))
        self.assertIn("Treasure Goblins", next(r for r in d3 if r["name"] == "Bandit Shrine")["effect_text"])
        names = re.search(r"Names\[KindCount\] = \{([^}]*)\}", PYLON_MATH.read_text(encoding="utf-8"))[1]
        self.assertEqual([k["kind"] for k in read_csv("data/pylon_buffs.csv")], re.findall(r'"(\w+)"', names))
        sheet = {r["name"]: r for r in read_csv("data/tunables/combat.csv")}
        for kind in kinds:
            with self.subTest(kind):
                seconds = sheet["shrine_%s_seconds" % kind]
                self.assertGreater(float(seconds["value"] or seconds["d3_value"]), 0)   # Give refuses a kind with no seconds

    def test_the_generator_refuses_a_bad_row(self):
        base = next(r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER)
        refused = {
            "a cast": dict(base, fire_on="cast", fire_skills="Bash"),
            "a hit": dict(base, fire_on="hit"),
            "the taken event": dict(base, fire_on="taken"),
            "skills named": dict(base, fire_skills="Bash"),
            "a chance of its own in the row": dict(base, chance_pct="50"),
            "an internal cooldown in the row": dict(base, icd_seconds="60"),
            "a range of shrines": dict(base, value_min="1", value_max="2"),
            "a part shrine": dict(base, value_min="1.5", value_max="1.5"),
            "no shrine": dict(base, value_min="0", value_max="0"),
            "a skill": dict(base, skill="Bash"),
            "another condition": dict(base, cond="triggered", cond_arg="3", cond_skills=""),
            "a type the core has not": dict(base, cond_skills="demonic"),
            "a skill as the type": dict(base, cond_skills="Bash"),
            "no type": dict(base, cond_skills=""),
            "a cond_arg on the type": dict(base, cond_arg="5"),
            "the type on a cast": dict(base, fire_on="cast", fire_skills="Bash", stat="cooldown_cut_seconds", value_min="1", value_max="1"),
            "the type on a skill row": dict(base, kind="skill", skill="Bash", stat="damage_increase_pct", fire_on=""),
        }
        for name, row in refused.items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.rows_of([row])
        for name, row in {"the base": base, "any kill, no type": dict(base, cond="", cond_skills=""), "two types": dict(base, cond_skills="undead;demon"),
                          "an elite kill": dict(base, fire_on="kill_elite")}.items():
            with self.subTest("accepts " + name):
                self.assertEqual(1, len(self.rows_of([row])))

    @staticmethod
    def rows_of(sheet_rows):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(SCRATCH)) as folder:
            module = Path(folder)
            (module / "data/d3").mkdir(parents=True)
            for name in ("base_items.csv", "affix_pools.csv", "legendary_potions.csv", *sorted(p.name for p in (MODULE / "data/d3").glob("*_skills.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_skill_values.csv")),
                         *sorted(p.name for p in (MODULE / "data/d3").glob("*_runes.csv"))):
                shutil.copy(MODULE / "data/d3" / name, module / "data/d3" / name)
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", module / "data/legendary_power_buffs.csv")
            with (module / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(sheet_rows[0]))
                writer.writeheader()
                writer.writerows(sheet_rows)
            return [row for row in generator.rows(module) if row[2] != "potion"]

    def test_the_generator_and_the_header_name_the_core_creature_types(self):
        core = core_creature_types()
        self.assertEqual(13, len(core))
        self.assertEqual(tuple(core[n] for n in sorted(core)), generator.CREATURE_TYPES)
        listed = re.search(r"CreatureTypes\[\] = \{([^}]*)\}", MATH.read_text(encoding="utf-8"))[1]
        self.assertEqual([""] + [core[n] for n in sorted(core)], re.findall(r'"(\w*)"', listed))


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, math, pylon_math, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": math, "combat/dc_pylon_math.h": pylon_math}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files, includes=[SRC, SRC / "combat"])
        work = Path(tempfile.mkdtemp(prefix="itemahavarion-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words, the core's enum and the shrine sheet, not from the code."""
        core = core_creature_types()
        kinds = shrine_kinds()
        out = [(T("row", *r), None) for r in rows]
        # a twin row of another item that names two types: the filter is data, not "demon" in code
        twin = list(rows[0]) if rows else None
        if twin:
            twin[0], twin[9] = OTHER, "undead;demon"
            out += [(T("row", *twin), None)]
        clear = [(T("clear"), None)]
        # fires on the kill of a demon, only with the item worn; the executor rolls the chance, so Fire never does
        out += clear + [(T("now", 1000), None), (T("fire", "kill", "", 1, 0, "demon"), "")]                       # not worn
        out += clear + [(T("now", 1000), None), (T("wears", OWNER, 0), None)]
        for number in range(0, 15):
            name = core.get(number, "")
            want = "random_shrine=1;" if name == "demon" else ""
            out += [(T("fire", "kill", "", 1, 0, name or "-"), want)]
            out += [(T("ctype", number), name)]
        for scale, draw in ((1, 0), (0.13, 99.99), (0, 50)):
            out += [(T("fire", "kill", "", scale, draw, "demon"), "random_shrine=1;")]
        out += [(T("fire", "kill", "", 1, 0, "-"), ""),                                                          # no enemy at all
                (T("fire", "kill", "", 1, 0, "Demon"), "")]                                                        # names are the lower-case ones
        for event in ("kill_elite", "cast", "hit", "taken", "hit_spender", "hit_generator", "image_death", "tick", ""):
            out += [(T("fire", event, "Bash", 1, 0, "demon"), "")]
        # the twin item names two types and fires for each; the staff alone fires for a demon only
        out += clear + [(T("now", 2000), None), (T("wears", OTHER, 0), None)]
        for name in core.values():
            out += [(T("fire", "kill", "", 1, 0, name), "random_shrine=1;" if name in ("undead", "demon") else "")]
        out += clear + [(T("now", 2000), None), (T("wears", OWNER, 0), None), (T("wears", OTHER, 0), None),
                        (T("fire", "kill", "", 1, 0, "demon"), "random_shrine=1;random_shrine=1;"),
                        (T("fire", "kill", "", 1, 0, "undead"), "random_shrine=1;")]
        # the shrine a draw picks: the sheet's shrines in order, evenly, the last for a draw of 1 or more, the first for a draw of 0 or less
        count = len(kinds)
        for roll in (0, 0.0001, 0.1, 0.1666, 0.1667, 0.2, 0.3333, 0.34, 0.5, 0.6667, 0.7, 0.8333, 0.84, 0.9, 0.9999, 1.0, 2.5, -0.5):
            at = 0 if roll <= 0 else min(int(roll * count), count - 1)
            out += [(T("shrine", roll), "%s 0" % kinds[at])]
        out += [(T("shrines"), "%d %d %s" % (count, count, "".join(k + "," for k in sorted(kinds))))]
        # the chance: the percent times the coefficient falls when the draw is under it; blank reads 0 (never), 100 always
        out += [(T("rolls", 1, 0, 0), "0"), (T("rolls", 1, 0, -1), "0"), (T("rolls", 1, 100, 99.99), "1"), (T("rolls", 1, 100, 100), "0"),
                (T("rolls", 1, 50, 49.99), "1"), (T("rolls", 1, 50, 50), "0"), (T("rolls", 1, 0.5, 0.49), "1"), (T("rolls", 1, 0.5, 0.5), "0"),
                (T("rolls", 0, 100, -1), "0")]
        return out

    def drive(self, rows, name, math=None, pylon_math=None):
        cases = self.cases(rows)
        work, binary = self.build(math or MATH.read_text(encoding="utf-8"), pylon_math or PYLON_MATH.read_text(encoding="utf-8"), name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            want = [w for _, w in cases if w is not None]
            return want, (run.stdout.split("\n")[:-1] if run.returncode == 0 else ["crashed: %s" % run.returncode])
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item(self):
        want, got = self.drive(mine(), "real")
        self.assertGreater(len(want), 60)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "the_wrong_event": [r[:12] + ("kill_elite",) + r[13:] for r in rows],
            "no_type_filter": [r[:7] + ("",) + r[8:9] + ("",) + r[10:] for r in rows],
            "the_wrong_type": [r[:9] + ("undead",) + r[10:] for r in rows],
            "the_wrong_effect": [r[:4] + ("resource_refund",) + r[5:] for r in rows],
            "two_shrines": [r[:5] + (2.0, 2.0) + r[7:] for r in rows],
            "a_chance_in_the_row": [r[:14] + (50.0,) + r[15:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        power = MATH.read_text(encoding="utf-8")
        pylons = PYLON_MATH.read_text(encoding="utf-8")
        cond = 'if (row.cond == "target_creature_type" && !CreatureTypeIs(row, situation.targetType))'
        is_type = "return !type.empty() && std::find(row.condSkills.begin(), row.condSkills.end(), type) != row.condSkills.end();"
        pick = "unsigned const at = roll > 0 ? static_cast<unsigned>(roll * ShrineCount) : 0;"
        header_mutants = {
            "the_type_never_asked": dict(math=mutate(power, cond, 'if (false)')),
            "the_type_always_ok": dict(math=mutate(power, cond, 'if (row.cond == "target_creature_type" && false)')),
            "the_type_asked_the_wrong_way": dict(math=mutate(power, cond, cond.replace("&& !CreatureTypeIs", "&& CreatureTypeIs"))),
            "only_the_first_type": dict(math=mutate(power, is_type, "return !type.empty() && !row.condSkills.empty() && row.condSkills.front() == type;")),
            "a_blank_type_is_every_type": dict(math=mutate(power, is_type, "return type.empty() || std::find(row.condSkills.begin(), row.condSkills.end(), type) != row.condSkills.end();")),
            "demon_misnamed": dict(math=mutate(power, '"demon"', '"daemon"')),
            "undead_misnamed": dict(math=mutate(power, '"undead"', '"undying"')),
            "the_names_off_by_one": dict(math=mutate(power, 'return type < std::size(CreatureTypes) ? CreatureTypes[type] : "";', 'return type + 1 < std::size(CreatureTypes) ? CreatureTypes[type + 1] : "";')),
            "a_number_past_the_end_named": dict(math=mutate(power, "type < std::size(CreatureTypes) ?", "type <= std::size(CreatureTypes) ?")),
            "the_event_ignored": dict(math=mutate(power, "if (row.fireOn != fireOn || !Owned(row, counts, situation, number))", "if (!Owned(row, counts, situation, number))")),
            "the_pick_always_the_first": dict(pylon_math=mutate(pylons, pick, "unsigned const at = 0;")),
            "the_pick_over_every_kind": dict(pylon_math=mutate(pylons, pick, "unsigned const at = roll > 0 ? static_cast<unsigned>(roll * KindCount) : 0;")),
            "pylons_in_the_pick": dict(pylon_math=mutate(pylons, "while (first < KindCount && IsPylon(static_cast<Kind>(first)))", "while (false)")),
            "the_pick_not_clamped": dict(pylon_math=mutate(pylons, "(at < ShrineCount ? at : ShrineCount - 1)", "at")),
            "a_negative_draw_not_the_first": dict(pylon_math=mutate(pylons, "roll > 0 ?", "roll != 0 ?")),
        }
        for name, changed in header_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(rows, name, **changed)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
