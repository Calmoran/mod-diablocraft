"""Legendary rest, bead diablocraft-omfd8: Ancestors' Grace (amulet, any class), which builds N-FATAL (the `fatal` event: a hit that would take all the
Life the player has left) and its first effect, `revive_full`.

  "When receiving fatal damage, you are instead restored to 100% of maximum Life and resources. This item is destroyed in the process."
  (d3planner item_neck.js, leg_ancestorsgrace, args 0: the text has no number; the item is marked `cube: false`)
  * the table (data/legendary_powers.csv) holds ONE row: an `effect` row `revive_full` 1 fired on the new event `fatal`, fixed, no chance, cooldown or
    condition (the item is gone once it fires); the generator refuses the event and the effect half built;
  * the production rules (src/combat/dc_item_power_math.h: IsFatal and Fire on `fatal`) are compiled and driven with the generated row: a hit is fatal
    when it takes at least the Life left (never a hit of 0, never a player with no Life), the row fires on `fatal` while the amulet is worn, never in
    the bag, never on another event;
  * mutants of the rules and of the row fail the same driver; the source-text guards on the damage hook (after Nerves of Steel, for every class), the
    judgement (the hit zeroed only when the effect saved the player) and the effect (the worn item destroyed first, Life and every resource of the
    class to their maximum, no worn item no save), with their source mutants, are in test_item_power_ancestors_grace_wiring.py. The C++ is
    compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-omfd8.md.
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

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
HARNESS = MODULE / "tests/item_power_ancestors_grace/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Amulet_102_x1"
STAT = "revive_full"
EVENT = "fatal"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_planner_states_the_power_with_no_number_and_no_cube(self):
        text = (REPO / "reference/d3planner/item_neck.js").read_text(encoding="utf-8")
        item = text[text.index('id: "%s"' % OWNER):]
        item = item[:item.index("},\n\n")]
        self.assertIn('custom: {id: "leg_ancestorsgrace", name: "Revive", format: "When receiving fatal damage, you are instead restored to 100%% of '
                      'maximum Life and resources. This item is destroyed in the process.", args: 0, cube: false}', item)

    def test_one_row_revives_on_a_fatal_hit(self):
        self.assertEqual([(OWNER, 0, "effect", "", STAT, 1.0, 1.0, "", 0.0, "", 0.0, 0, EVENT, "", 100.0, 0.0)], mine())

    def test_the_owner_is_the_amulet_that_drops(self):
        item = next(r for r in read_csv(MODULE / "data/d3/base_items.csv") if r["d3_id"] == OWNER)
        self.assertEqual(("Ancestors' Grace", "neck", "Amulet", "legendary", "", "yes", "no"),
                         (item["d3_name"], item["slot"], item["type"], item["rarity"], item["designated_class"], item["pool_version"], item["craft_only"]))

    def test_the_row_has_its_source(self):
        rows = [r for r in read_csv(MODULE / "data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("leg_ancestorsgrace", rows[0]["source"])
        self.assertIn("diablocraft-omfd8", rows[0]["source"])
        self.assertTrue(rows[0]["note"])


class Generator(unittest.TestCase):
    REVIVE = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": STAT, "value_min": "1", "value_max": "1", "cond": "",
              "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": EVENT, "fire_skills": "", "chance_pct": "",
              "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, change):
        """The generator run on a copy of the module whose sheet is the real one with the owner's row replaced (None leaves it out)."""
        work = Path(tempfile.mkdtemp(prefix="ancestors-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv(MODULE / "data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + ([{**self.REVIVE, **change}] if change is not None else []))
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "the revive on another event": ({"fire_on": "kill"}, "revive_full is fired by fatal"),
            "the revive simply on": ({"fire_on": ""}, "need a fire_on event"),
            "another effect on fatal": ({"stat": "frenzy_stacks", "value_min": "5", "value_max": "5"}, "fatal fires nothing else"),
            "a ranged revive": ({"value_min": "0.5"}, "revive_full is an item"),
            "a double revive": ({"value_min": "2", "value_max": "2"}, "revive_full is an item"),
            "a zero revive": ({"value_min": "0", "value_max": "0"}, "needs 0 < value_min"),
            "a revive with a chance": ({"chance_pct": "50"}, "revive_full is an item"),
            "a revive with a cooldown": ({"icd_seconds": "5"}, "revive_full is an item"),
            "a revive under a condition": ({"cond": "enemies_hit_at_most", "cond_arg": "3"}, "enemies_hit_at_most is an effect"),
            "a revive naming a skill": ({"skill": "Bash"}, "a skill is named"),
            "a revive naming fire skills": ({"fire_skills": "Bash"}, "names skills"),
            "a revive on a set level": ({"owner": "Immortal King's Call", "pieces": "2"}, "revive_full is an item"),
            "an unknown event": ({"fire_on": "fatale"}, "fire_on is one of"),
        }
        for name, (change, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(change)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itemancestors-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words, not from the code."""
        did = "%s=1@;" % STAT
        out = [(T("row", *r), None) for r in rows]
        wear = [(T("clear"), None), (T("wears", OWNER), None)]
        # "fatal damage": the hit takes at least all the Life left; a hit of 0 and a player with no Life are not it
        for damage, health, want in ((100, 100, 1), (99, 100, 0), (101, 100, 1), (1, 1, 1), (1, 2, 0), (5000, 4999, 1), (4999, 5000, 0),
                                     (0, 100, 0), (0, 0, 0), (50, 0, 0), (4294967295, 4294967295, 1), (4294967295, 1, 1), (4294967294, 4294967295, 0)):
            out.append((T("fatal", damage, health), str(want)))
        # worn: the fatal event fires the revive, once per ask (the item's destruction is what ends it, not a cooldown)
        out += wear + [(T("now", 1000), None), (T("fire", EVENT), did), (T("now", 1000), None), (T("fire", EVENT), did)]
        # not worn, or only in the bag: nothing
        out += [(T("clear"), None), (T("now", 1000), None), (T("fire", EVENT), "")]
        out += [(T("clear"), None), (T("bag", OWNER), None), (T("now", 1000), None), (T("fire", EVENT), "")]
        # worn, the other events: nothing
        out += wear + [(T("now", 1000), None)] + [(T("fire", e), "") for e in ("hit", "cast", "taken", "kill", "kill_elite", "life_below", "tick", "image_death")]
        return out

    def drive(self, header_text, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "another_event": [r[:12] + ("kill",) + r[13:] for r in rows],
            "another_effect": [r[:4] + ("frenzy_stacks",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline bool IsFatal("):]
        body = body[:body.index("\n    }\n")]
        rules = {
            "exact_hit_survives": ("damage >= health", "damage > health"),
            "damage_alone": ("health > 0 && damage >= health", "damage > 0"),
            "dead_player_is_fatal": ("health > 0 && ", ""),
            "inverted": ("damage >= health", "damage < health"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, body.count(old), name + " does not apply once")
                want, got = self.drive(real.replace(body, body.replace(old, new)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        fire = real[real.index("inline std::vector<Fired> Fire("):]
        fire = fire[:fire.index("\n    }\n")]
        fire_rules = {
            "unworn_fires": ("!Owned(row, counts, situation, number)", "false"),
            "any_event_fires": ("row.fireOn != fireOn ||", "false ||"),
        }
        for name, (old, new) in fire_rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, fire.count(old), name + " does not apply once")
                want, got = self.drive(real.replace(body, body).replace(fire, fire.replace(old, new)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def at(text, needle):
    """Where `needle` stands in `text`; the guard fails (an assertion) when it is gone."""
    found = text.find(needle)
    assert found >= 0, "missing: " + needle
    return found


if __name__ == "__main__":
    unittest.main()
