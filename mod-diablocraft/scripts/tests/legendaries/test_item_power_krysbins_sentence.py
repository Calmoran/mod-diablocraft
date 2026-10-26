"""Legendary rest, bead diablocraft-vvtvv: Krysbin's Sentence (ring, any class). N-TCTRL (a bonus by the control state of the target), the player-wide use.

  "You deal [75-100]% increased damage against slowed enemies or triple this bonus against enemies afflicted by any other type of control-impairing effect."
  * the numbers (75 to 100) are read from d3planner (item_finger.js, leg_krysbinssentence); the table (data/legendary_powers.csv) holds ONE `player` row for the
    pool item P6_Unique_Ring_03: `damage_vs_impaired_pct`, 75-100, always on, which the roller rolls once per item;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts the stat
    as an always-on player row and refuses a condition, an event, a skill row;
  * the production rule (src/combat/dc_item_power_math.h: ImpairedFactor, with TargetSlowed and the new TargetControlled bit of Situation::targetControl) is
    compiled and driven with the generated row: 1 + N/100 against a slowed target, 1 + 3N/100 against one under any other control (both: the tripled one),
    1 against a target under none, nothing with the item unworn or unrolled, a second source multiplies; mutants of the rule and of the row fail the same driver;
  * source-text guards for the server side (dc_item_powers_readers.cpp ImpairedFactor, dc_control_immunity.cpp ImpairedBesidesSlow, dc_combat.cpp ComputeHit): the
    states are read from the target before the lock, a slow is the strongest slow aura below 0 (a Chill is one) and every other control mechanic of
    ControlImmunity's list counts, the hit multiplies its legendary term by the factor once, and only when some row gives it; mutants of that text are caught.
    The in-game steps are in docs/test-diablocraft-vvtvv.md.
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
import item_powers_source  # noqa: E402
import generate_legendary_powers as generator  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
COMBAT = SRC / "combat/dc_combat.cpp"
CONTROL = SRC / "combat/dc_control_immunity.cpp"
HARNESS = MODULE / "tests/item_power_krysbins_sentence/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P6_Unique_Ring_03"
STAT = "damage_vs_impaired_pct"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


def numbers():
    """(low, high) of the bonus, in percent, as the planner words it."""
    text = (REPO / "reference/d3planner/item_finger.js").read_text(encoding="utf-8")
    start = text.index('id: "%s"' % OWNER)
    item = text[start:text.index("\n  },", start)]
    m = re.search(r'You deal %d%% increased damage against slowed enemies or triple this bonus against enemies afflicted by any other type of '
                  r'control-impairing effect\.", min: (\d+), max: (\d+)', item)
    assert m, item
    return float(m[1]), float(m[2])


class Table(unittest.TestCase):
    def test_the_source_gives_the_range(self):
        self.assertEqual((75.0, 100.0), numbers())

    def test_one_player_row_holds_the_range(self):
        low, high = numbers()
        self.assertEqual([(OWNER, 0, "player", "", STAT, low, high, *BLANK)], mine())

    def test_the_row_has_its_source_and_says_how_it_combines(self):
        rows = [r for r in read_csv("data/legendary_powers.csv") if r["owner"] == OWNER]
        self.assertEqual(1, len(rows))
        self.assertIn("item_finger.js", rows[0]["source"])
        self.assertIn("leg_krysbinssentence", rows[0]["source"])
        self.assertIn("1 + 3N/100", rows[0]["note"])

    def test_the_tooltip_shows_the_text(self):
        m = re.search(r"\('%s','[^']*','([^']*)'" % OWNER, (MODULE / "data/generated/crafting.sql").read_text(encoding="utf-8"))
        self.assertTrue(m)
        self.assertEqual("You deal 75–100% increased damage against slowed enemies or triple this bonus against enemies afflicted by any other type of control-impairing effect.", m[1])

    def test_the_power_is_in_the_contract(self):
        text = (REPO / "docs/contracts/legendary-powers.md").read_text(encoding="utf-8")
        self.assertIn("### Krysbin's Sentence (`diablocraft-vvtvv`", text)


class Generator(unittest.TestCase):
    BASE = {"owner": OWNER, "pieces": "", "kind": "player", "skill": "", "stat": STAT, "value_min": "75", "value_max": "100", "cond": "",
            "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
            "icd_seconds": "", "source": "s", "note": "n"}

    def render_with(self, *edits):
        work = Path(tempfile.mkdtemp(prefix="krysbin-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            sheet = read_csv("data/legendary_powers.csv")
            kept = [r for r in sheet if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(sheet[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.BASE, **e} for e in edits])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_row_is_accepted(self):
        self.assertEqual(1, len([r for r in self.render_with({}) if r[0] == OWNER]))

    def test_it_refuses_what_the_code_does_not_read(self):
        refused = {
            "a condition": {"cond": "life_missing"},
            "an event": {"fire_on": "hit_generator"},
            "a skill row": {"kind": "skill", "skill": "Leap"},
            "a skill list": {"cond_skills": "Leap"},
            "a negative number": {"value_min": "-100", "value_max": "-75"},
        }
        for name, edit in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(edit)


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_item_power_math.h": header_text})
        return Path(tempfile.mkdtemp(prefix="krysbin-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        low, high = numbers()
        out = [(T("row", *r), None) for r in rows]
        clear = [(T("clear"), None)]
        worn = lambda roll: clear + [(T("wears", OWNER), None), (T("value", OWNER, "", STAT, roll), None)]  # noqa: E731
        # not worn, worn with no roll, a roll in the bag: nothing, whatever the target
        out += clear + [(T("impaired", 1, 1), "1")]
        out += clear + [(T("wears", OWNER), None), (T("impaired", 1, 0), "1")]
        out += clear + [(T("value", OWNER, "", STAT, high), None), (T("impaired", 0, 1), "1")]
        # worn and rolled: a target under no control takes nothing extra; a slowed one N%; one under any other control triple N%; both, the tripled
        for roll in (low, 87, high):
            out += worn(roll) + [(T("impaired", 0, 0), "1"), (T("impaired", 1, 0), g(1 + roll / 100)), (T("impaired", 0, 1), g(1 + 3 * roll / 100)),
                                 (T("impaired", 1, 1), g(1 + 3 * roll / 100))]
        # a second source multiplies (another item's fixed 10%)
        out += worn(high) + [(T("wears", "Other Ring"), None), (T("impaired", 1, 0), g((1 + high / 100) * 1.1)), (T("impaired", 0, 1), g((1 + 3 * high / 100) * 1.3)),
                             (T("impaired", 0, 0), "1")]
        # the stat is a player stat of its own, not the damage multiplier read on every hit
        out += worn(high) + [(T("factor", "damage_dealt_pct"), "1"), (T("sum", "damage_reduction_pct"), "0")]
        # the range rolls once per item (a Primal stores the top)
        out += [(T("roll", OWNER, 1), "power::%s=%g;" % (STAT, high)), (T("roll", OWNER, 0), "power::%s=%g;" % (STAT, (low + high) / 2))]
        return out

    def other(self):
        return [("Other Ring", 0, "player", "", STAT, 10.0, 10.0, *BLANK)]

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
        want, got = self.drive(MATH.read_text(encoding="utf-8"), mine() + self.other(), "real")
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(1, len(rows))
        want, _ = self.drive(real, rows + self.other(), "want")
        row_mutants = {
            "the_row_lost": [],
            "the_number_halved": [r[:5] + (r[5] / 2, r[6] / 2) + r[7:] for r in rows],
            "the_stat_changed": [r[:4] + ("damage_dealt_pct",) + r[5:] for r in rows],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(real, mutant_rows + self.other(), name)
                self.assertNotEqual(want, got, name + " survived")
        header_mutants = {
            "the_triple_lost": real.replace("factor *= 1.0 + 3.0 * pct / 100.0;", "factor *= 1.0 + pct / 100.0;"),
            "the_triple_is_double": real.replace("factor *= 1.0 + 3.0 * pct / 100.0;", "factor *= 1.0 + 2.0 * pct / 100.0;"),
            "a_slow_gets_the_triple": real.replace("else if ((situation.targetControl & TargetSlowed) != 0)\n                factor *= 1.0 + pct / 100.0;",
                                                   "else if ((situation.targetControl & TargetSlowed) != 0)\n                factor *= 1.0 + 3.0 * pct / 100.0;"),
            "a_slow_gets_nothing": real.replace("else if ((situation.targetControl & TargetSlowed) != 0)\n                factor *= 1.0 + pct / 100.0;", ""),
            "other_control_gets_nothing": real.replace("if ((situation.targetControl & TargetControlled) != 0)\n                factor *= 1.0 + 3.0 * pct / 100.0;\n            else if",
                                                       "if (false)\n                factor *= 1.0 + 3.0 * pct / 100.0;\n            else if"),
            "both_states_stack": real.replace("else if ((situation.targetControl & TargetSlowed) != 0)\n                factor *= 1.0 + pct / 100.0;",
                                              "if ((situation.targetControl & TargetSlowed) != 0)\n                factor *= 1.0 + pct / 100.0;"),
            "every_target_takes_it": real.replace("else if ((situation.targetControl & TargetSlowed) != 0)\n                factor *= 1.0 + pct / 100.0;",
                                                  "else\n                factor *= 1.0 + pct / 100.0;"),
            "a_source_added_not_multiplied": real.replace("factor *= 1.0 + pct / 100.0;\n        }\n        return factor;\n    }\n\n    // N-CLOCK", "factor += pct / 100.0;\n        }\n        return factor;\n    }\n\n    // N-CLOCK"),
            "the_stat_read_is_another": real.replace('"damage_vs_impaired_pct", situation)', '"damage_dealt_pct", situation)'),
        }
        for name, header in header_mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, header, name + " did not apply")
                _, got = self.drive(header, rows + self.other(), name)
                self.assertNotEqual(want, got, name + " survived")


class Wiring(unittest.TestCase):
    def check(self, readers, powers, combat, control):
        """The guards on how the target's control state reaches the rule; raises AssertionError on a mutant."""
        reader = readers[readers.index("double ImpairedFactor(Player const* player, Unit const* target)"):]
        reader = reader[:reader.index("\n    }\n") + 7]
        assert "if (!player || !target || !Data().impaired)\n            return 1.0;" in reader, "no target, no row, no factor"
        assert "unsigned held = target->GetMaxNegativeAuraModifier(SPELL_AURA_MOD_DECREASE_SPEED) != 0.0f ? ItemPower::TargetSlowed : 0u;" in reader, "a slow is the strongest slow aura"
        assert "if (ControlImmunity::ImpairedBesidesSlow(target))\n            held |= ItemPower::TargetControlled;" in reader, "any other control counts"
        assert reader.index("held |= ItemPower::TargetControlled;") < reader.index("std::lock_guard<std::mutex> lock(mutex);"), "the states are read before the lock"
        assert "situation.targetControl = held;" in reader, "the situation carries the states"
        assert "return ItemPower::ImpairedFactor(Data().rows, CountsOf(guid), situation);" in reader, "the rule over the player's rows"
        assert "ItemPower::Situation seen = Seen(player);" in reader, "a fresh read of the player"
        assert 'loaded.impaired = loaded.impaired || (row.kind == "player" && row.stat == "damage_vs_impaired_pct");' in powers, "the table notes that a row gives it"
        compute = combat[combat.index("bool ComputeHit("):combat.index("std::string Hit::Describe()")]
        read = "hit.legendary *= ItemPowers::ImpairedFactor(player, target);"
        assert read in compute, "ComputeHit multiplies the legendary term by it, with the hit's target"
        assert compute.index("hit.legendary *= ItemPowers::TargetFactor(") < compute.index(read), "beside the other target factor, after the term is set"
        assert combat.count("ItemPowers::ImpairedFactor(") == 1, "nothing else reads it"
        besides = control[control.index("bool ImpairedBesidesSlow(Unit const* unit)"):]
        besides = besides[:besides.index("\n    }\n") + 7]
        assert "unit->HasAuraWithMechanic(ControlImpairing & ~(1ull << MECHANIC_SNARE))" in besides, "every control mechanic of the list but the snare"

    def parts(self):
        return dict(readers=item_powers_source.named("dc_item_powers_readers.cpp"), powers=item_powers_source.named("dc_item_powers.cpp"),
                    combat=COMBAT.read_text(encoding="utf-8"), control=CONTROL.read_text(encoding="utf-8"))

    def test_the_target_state_reaches_the_rule(self):
        self.check(**self.parts())

    def test_the_guards_fail_their_mutants(self):
        before = self.parts()
        r, p, c, k = before["readers"], before["powers"], before["combat"], before["control"]
        mutants = {
            "always_looked_at": dict(readers=r.replace("if (!player || !target || !Data().impaired)", "if (!player || !target)", 1)),
            "any_speed_change": dict(readers=r.replace("GetMaxNegativeAuraModifier(SPELL_AURA_MOD_DECREASE_SPEED) != 0.0f ? ItemPower::TargetSlowed : 0u;\n        if (ControlImmunity",
                                                       "GetMaxNegativeAuraModifier(SPELL_AURA_MOD_STUN) != 0.0f ? ItemPower::TargetSlowed : 0u;\n        if (ControlImmunity", 1)),
            "the_slow_counts_as_other": dict(readers=r.replace("ControlImmunity::ImpairedBesidesSlow(target)", "ControlImmunity::Impaired(target)", 1)),
            "other_control_dropped": dict(readers=r.replace("            held |= ItemPower::TargetControlled;", "", 1)),
            "states_after_the_lock": dict(readers=r.replace("        if (ControlImmunity::ImpairedBesidesSlow(target))\n            held |= ItemPower::TargetControlled;\n        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n",
                                                            "        ItemPower::Situation seen = Seen(player);\n        std::lock_guard<std::mutex> lock(mutex);\n        if (ControlImmunity::ImpairedBesidesSlow(target))\n            held |= ItemPower::TargetControlled;\n", 1)),
            "states_dropped": dict(readers=r.replace("        situation.targetControl = held;\n", "", 1)),
            "flag_not_set": dict(powers=p.replace('loaded.impaired = loaded.impaired ||', 'loaded.impaired = false ||', 1)),
            "not_in_the_hit": dict(combat=c.replace("        hit.legendary *= ItemPowers::ImpairedFactor(player, target); // Krysbin's Sentence: by the target's slow or other control (N-TCTRL)\n", "", 1)),
            "no_target": dict(combat=c.replace("ItemPowers::ImpairedFactor(player, target)", "ItemPowers::ImpairedFactor(player, nullptr)", 1)),
            "snare_included": dict(control=k.replace("ControlImpairing & ~(1ull << MECHANIC_SNARE)", "ControlImpairing", 1)),
        }
        for name, edit in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(before, {**before, **edit}, name + " did not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    self.check(**{**before, **edit})


if __name__ == "__main__":
    unittest.main()
