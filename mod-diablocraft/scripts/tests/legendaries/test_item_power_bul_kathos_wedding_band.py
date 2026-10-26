"""Legendary rest, bead diablocraft-942kn: Bul-Kathos's Wedding Band (ring, any class), which builds N-CLOCK (the `tick` event: a row fired once
per its icd_seconds while the item is worn) and its first effect, `drain_life`.

  "You drain life from enemies around you." (d3planner item_finger.js, leg_bulkathossweddingband, args 0: the text has no number)
  * the numbers are the item's Power file's (docs/research/legendary-pow-data.csv, ItemPassive_Unique_Ring_020_x1.pow): SF_0 life drain % per target
    0.005 is the row's 0.5 (x100), SF_2 pulse interval 1 is its icd_seconds; SF_5 damage area 8, SF_1 Max X Weapon Damage Per Target 20 and SF_3
    max drain HP per pulse 0.01 are the combat tunables bul_kathos_drain_radius_yards, _max_weapon_damage and _max_heal_pct (x100), each its D3 value;
  * the table (data/legendary_powers.csv) holds ONE row: an `effect` row `drain_life` 0.5 fired on the new event `tick` every 1 second; the generated
    SQL and the migration are what the generator renders; the generator refuses the clock and the drain half built;
  * the production rules (src/combat/dc_item_power_math.h: Fire on `tick` with the row's internal cooldown as the period, DrainPulse) are compiled
    and driven with the generated row: once a second while worn (the end exact), never in the bag, never on another event; each enemy loses 0.5% of
    its maximum Life at most 20 x the weapon damage, the player gains what was drained at most 1% of its own maximum Life;
  * mutants of the rules and of the row fail the same driver, and source mutants fail the guards on the clock's hook, the effect's dispatch and the
    drain (only in combat, the stock "Drain Life" record, the tunables, the hit dealt as it stands, the heal). The C++ is compile-checked by
    syntax_check.sh and the in-game steps are in docs/test-diablocraft-942kn.md.
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
HARNESS = MODULE / "tests/item_power_bul_kathos_wedding_band/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "Unique_Ring_020_x1"
STAT = "drain_life"
EVENT = "tick"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def pow_numbers():
    """{SF label: value} of the ring's Power file, as the decoder wrote them."""
    row = next(r for r in read_csv(REPO / "docs/research/legendary-pow-data.csv") if r["linked_by"] == "item " + OWNER)
    assert row["power_file"] == "ItemPassive_Unique_Ring_020_x1.pow", row
    return {m[1]: float(m[2]) for m in re.finditer(r"SF_\d+ ([^=;]+?) = ([\d.]+)", row["script_formulas"])}


def tunables():
    return {r["name"]: r for r in read_csv(MODULE / "data/tunables/combat.csv") if r["name"].startswith("bul_kathos_drain_")}


class Table(unittest.TestCase):
    def test_the_planner_has_no_number_and_the_power_file_has_them(self):
        text = (REPO / "reference/d3planner/item_finger.js").read_text(encoding="utf-8")
        item = text[text.index('id: "%s"' % OWNER):]
        item = item[:item.index("},\n\n")]
        self.assertIn('custom: {id: "leg_bulkathossweddingband", name: "Drain Life", format: "You drain life from enemies around you.", args: 0}', item)
        self.assertEqual({"life drain % per target": 0.005, "Max X Weapon Damage Per Target": 20.0, "pulse interval": 1.0,
                          "max drain HP per pulse": 0.01, "damage area": 8.0}, pow_numbers())

    def test_one_row_drains_on_the_clock(self):
        sf = pow_numbers()
        pct = sf["life drain % per target"] * 100
        self.assertEqual([(OWNER, 0, "effect", "", STAT, pct, pct, "", 0.0, "", 0.0, 0, EVENT, "", 100.0, sf["pulse interval"])], mine())

    def test_the_tunables_are_the_power_files_numbers(self):
        sf = pow_numbers()
        rows = tunables()
        self.assertEqual({"bul_kathos_drain_radius_yards": sf["damage area"], "bul_kathos_drain_max_weapon_damage": sf["Max X Weapon Damage Per Target"],
                          "bul_kathos_drain_max_heal_pct": sf["max drain HP per pulse"] * 100},
                         {name: float(r["d3_value"]) for name, r in rows.items()})
        for name, r in rows.items():
            self.assertEqual("", r["value"], name + " is D3's number, not a tuned one")
            self.assertIn("ItemPassive_Unique_Ring_020_x1.pow", r["notes"])
            self.assertIn("diablocraft-942kn", r["notes"])


class Generator(unittest.TestCase):
    DRAIN = {"owner": OWNER, "pieces": "", "kind": "effect", "skill": "", "stat": STAT, "value_min": "0.5", "value_max": "0.5", "cond": "",
             "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": EVENT, "fire_skills": "", "chance_pct": "",
             "icd_seconds": "1", "source": "s", "note": "n"}

    def render_with(self, change):
        """The generator run on a copy of the module whose sheet is the real one with the owner's row replaced (None leaves it out)."""
        work = Path(tempfile.mkdtemp(prefix="bulkathos-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv(MODULE / "data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + ([{**self.DRAIN, **change}] if change is not None else []))
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_row_passes(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_it_cannot_carry(self):
        refused = {
            "a clock with no period": ({"icd_seconds": ""}, "tick is the clock"),
            "a clock with a zero period": ({"icd_seconds": "0"}, "tick is the clock"),
            "a clock that rolls": ({"chance_pct": "50"}, "tick is the clock"),
            "a clock opening a window": ({"kind": "player", "stat": "damage_reduction_pct", "value_min": "10", "value_max": "10", "cond": "triggered",
                                          "cond_arg": "3"}, "tick is the clock"),
            "a clock naming skills": ({"fire_skills": "Bash"}, "only a cast, a hit"),
            "the drain on another event": ({"fire_on": "kill", "icd_seconds": ""}, "drain_life"),
            "the drain simply on": ({"fire_on": "", "icd_seconds": ""}, "need a fire_on event"),
            "a ranged drain": ({"value_min": "0.4"}, "drain_life"),
            "a zero drain": ({"value_min": "0", "value_max": "0"}, "drain_life"),
            "a drain above 100": ({"value_min": "101", "value_max": "101"}, "drain_life"),
            "a drain on a set level": ({"owner": "Immortal King's Call", "pieces": "2"}, "drain_life"),
            "a drain naming a skill": ({"skill": "Bash"}, "a skill is named"),
            "an unknown effect": ({"stat": "drain_lifex"}, "an effect stat is one of"),
            "an unknown event": ({"fire_on": "tock"}, "fire_on is one of"),
        }
        for name, (change, why) in refused.items():
            with self.subTest(case=name):
                with self.assertRaisesRegex(ValueError, why):
                    self.render_with(change)


def expected_pulse(enemies, pct, weapon, cap, player, heal_pct):
    """The drain worked out from the Power file's words: each enemy's share of its Life up to the cap, the player's heal up to its share."""
    taken = [min(most * pct / 100, cap * weapon) for most in enemies]
    return "".join(g(x) + ";" for x in taken) + "|" + g(min(sum(taken), player * heal_pct / 100))


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"combat/dc_item_power_math.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="itembulkathos-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the Power file's numbers, not from the code."""
        sf = pow_numbers()
        pct, period = sf["life drain % per target"] * 100, int(sf["pulse interval"] * 1000)
        cap, heal = sf["Max X Weapon Damage Per Target"], sf["max drain HP per pulse"] * 100
        did = "%s=%s@;" % (STAT, g(pct))
        out = [(T("row", *r), None) for r in rows]
        wear = [(T("clear"), None), (T("wears", OWNER), None)]
        # not worn, or only in the bag: the clock fires nothing
        out += [(T("clear"), None), (T("now", 5000), None), (T("fire", EVENT), "")]
        out += [(T("clear"), None), (T("bag", OWNER), None), (T("now", 5000), None), (T("fire", EVENT), "")]
        # worn: at once, then once per pulse interval, the end exact; asking in between fires nothing and does not restart the wait
        out += wear + [(T("now", 1000), None), (T("fire", EVENT), did)]
        for k in (1, 2, 3):
            out += [(T("now", 1000 + k * period - 1), None), (T("fire", EVENT), ""), (T("now", 1000 + k * period - 1), None), (T("fire", EVENT), ""),
                    (T("now", 1000 + k * period), None), (T("fire", EVENT), did)]
        # a late ask fires once, and the next period counts from it
        out += [(T("now", 1000 + 3 * period + 2500), None), (T("fire", EVENT), did), (T("now", 1000 + 4 * period + 2499), None), (T("fire", EVENT), ""),
                (T("now", 1000 + 4 * period + 2500), None), (T("fire", EVENT), did)]
        # the clock is its own: another event never drains
        out += wear + [(T("now", 1000), None)] + [(T("fire", e), "") for e in ("hit", "cast", "taken", "kill", "kill_elite", "life_below")]
        # the pulse: each enemy's share of its maximum Life up to cap x the weapon's damage, the heal the sum up to the player's share
        for enemies, weapon, player in (([1000.0], 100.0, 10000.0), ([1000.0, 1e6, 1e9], 100.0, 10000.0), ([4e5, 4e5 + 1, 3.9e5], 100.0, 1e6),
                                        ([2e6, 2e6], 50.0, 1e5), ([123456.0], 7.5, 5e4), ([5e9, 1e3, 7e7, 2.5e8], 1234.0, 3.3e6)):
            out.append((T("drain", pct, weapon, cap, player, heal, ";".join(g(e) for e in enemies)),
                        expected_pulse(enemies, pct, weapon, cap, player, heal)))
        # no weapon damage and no cap: nothing taken, nothing healed
        out.append((T("drain", pct, 0, cap, 1e5, heal, "1e6;2e6"), "0;0;|0"))
        out.append((T("drain", pct, 100, 0, 1e5, heal, "1e6"), "0;|0"))
        out.append((T("drain", pct, 100, cap, 1e5, 0, "1e6"), g(min(1e6 * pct / 100, cap * 100)) + ";|0"))
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

    def test_every_rule_agrees_with_the_power_file(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine(), "real")
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        row_mutants = {
            "another_event": [r[:12] + ("kill",) + r[13:] for r in rows],
            "period_two": [r[:15] + (2.0,) for r in rows],
            "no_period": [r[:15] + (0.0,) for r in rows],
            "drain_doubled": [r[:5] + (1.0, 1.0) + r[7:] for r in rows],
            "another_effect": [r[:4] + ("frenzy_stacks",) + r[5:] for r in rows],
            "no_rows": [],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                want, got = self.drive(real, mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        body = real[real.index("inline Drained DrainPulse("):]
        body = body[:body.index("\n    }\n")]
        rules = {
            "no_enemy_cap": ("std::min(most * pct / 100.0, capWeapons * weaponDamage)", "most * pct / 100.0"),
            "percent_not_divided": ("most * pct / 100.0", "most * pct"),
            "cap_ignores_weapon": ("capWeapons * weaponDamage", "capWeapons"),
            "no_heal_cap": ("std::min(sum, playerMaxLife * healPct / 100.0)", "sum"),
            "heal_only_the_last": ("sum += one;", "sum = one;"),
            "heal_share_not_divided": ("playerMaxLife * healPct / 100.0", "playerMaxLife * healPct"),
        }
        for name, (old, new) in rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, body.count(old), name + " does not apply once")
                want, got = self.drive(real.replace(body, body.replace(old, new)), rows, name)
                self.assertNotEqual(want, got, name + " survived")
        fire = real[real.index("inline std::vector<Fired> Fire("):]
        fire = fire[:fire.index("\n    }\n")]
        fire_rules = {
            "period_is_the_number": ('row.stat == "cast_skill" ? (number > 0 ? number : situation.castCooldownSeconds) : row.icdSeconds', "number"),
            "period_end_exclusive": ("< static_cast<std::uint32_t>(icd * 1000.0)", "<= static_cast<std::uint32_t>(icd * 1000.0)"),
            "unworn_fires": ("!Owned(row, counts, situation, number)", "false"),
            "any_event_fires": ("row.fireOn != fireOn ||", "false ||"),
        }
        for name, (old, new) in fire_rules.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, fire.count(old), name + " does not apply once")
                want, got = self.drive(real.replace(fire, fire.replace(old, new)), rows, name)
                self.assertNotEqual(want, got, name + " survived")


if __name__ == "__main__":
    unittest.main()
