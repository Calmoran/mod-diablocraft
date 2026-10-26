"""Fury of the Vanished Peak (diablocraft-e0pt4, legendary list row 32; builds N-COST): "Reduces the Fury cost of Seismic Slam by 50% and increases its
damage by [400-500]%."

  * data/legendary_powers.csv gains two `skill` rows for the pool weapon P61_Unique_Mighty_2H_006: Seismic Slam `cost_reduction_pct` 50 (fixed: the text's
    number) and `damage_increase_pct` 400-500 (rolled once per item); the words and the range come from d3planner (data.json) and are set against the
    tooltip; the generator refuses a cost row it cannot carry (a condition, an event, more than the whole cost, a skill that states no cost);
  * the spell records (the generated spell_dbc rows the newest combat migration carries): each skill a cost row names has one hidden SPELLMOD_COST aura in
    its class's family, the gear cost aura's shape, its mask the skill's bit in word one. The core's SpellInfo::IsAffected is restated over every record of
    the family: the aura reaches exactly that skill's records (the skill and every rune), and the class's cost probe (the sheet's Resource Cost
    Reduction) is not one of them;
  * the production rule (dc_item_power_math.h SkillSum) is driven with the generated rows through the k0k2 harness, and its mutants fail the same driver;
  * source-text guards that Refresh's CostAuras puts the skill auras in step (they prove the call is there, not that it runs; the C++ is compile-checked by
    syntax_check.sh and the in-game steps are in docs/test-diablocraft-e0pt4.md).
"""
import re
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as spells  # noqa: E402
import harness_env  # noqa: E402
import test_item_power_math as k0k2  # noqa: E402  (a module, so its test classes are not run twice)
from test_control_immunity_gap import number  # noqa: E402
from test_item_power_cindercoat import FAMILIES, HEADER, SHELLS_SQL, affected, manifest, records, words  # noqa: E402
from test_item_power_math import all_rows, planner_json, read_csv, tooltip  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
FURY = "P61_Unique_Mighty_2H_006"
SLAM = "Seismic Slam"
SPELL_AURA_ADD_PCT_MODIFIER, SPELLMOD_COST = 108, 14
OWNERS = {FURY: ("Barbarian", SLAM), "P61_Unique_CombatStaff_2H_003_x1": ("Monk", "Wave of Light"),     # every one-skill cost owner: its class and skill (Incense Torch, diablocraft-3jl7t;
          "P61_Unique_Staff_009": ("Wizard", "Meteor")}                                                  # The Grand Vizier, diablocraft-muzdx)
HERGBRASH = "P4_Unique_Belt_06"                                                                          # one row, three skills (diablocraft-uynen)
HERGBRASH_SKILLS = ("Arcane Torrent", "Disintegrate", "Ray of Frost")
COST_SKILLS = [*OWNERS.values(), *(("Wizard", skill) for skill in HERGBRASH_SKILLS)]                     # every skill a cost row names: its class and name


def source():
    """(text, low, high) as d3planner's data.json words the power."""
    custom = planner_json(FURY)["required"]["custom"]
    assert custom["format"] == "Reduces the Fury cost of Seismic Slam by 50%% and increases its damage by %d%%.", custom
    return custom["format"] % custom["min"], float(custom["min"]), float(custom["max"])


def cost_rows():
    return {(r[0], r[3]): r for r in all_rows() if r[2] == "skill" and r[4] == "cost_reduction_pct"}


class Table(unittest.TestCase):
    def test_the_rows_are_the_source(self):
        text, low, high = source()
        blank = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)
        self.assertEqual({(FURY, 0, "skill", SLAM, "cost_reduction_pct", 50.0, 50.0, *blank), (FURY, 0, "skill", SLAM, "damage_increase_pct", low, high, *blank)},
                         {r for r in all_rows() if r[0] == FURY})
        self.assertEqual((400.0, 500.0), (low, high))
        self.assertEqual(text.replace("400%", "400–500%"), tooltip(FURY))
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == FURY)
        self.assertEqual(("Fury of the Vanished Peak", "yes", "barbarian"), (pool["d3_name"], pool["pool_version"], pool["designated_class"]))
        self.assertEqual({*OWNERS, HERGBRASH}, {owner for owner, _ in cost_rows()})

    def test_the_generator_refuses_a_cost_row_it_cannot_carry(self):
        base = {"owner": FURY, "pieces": "", "kind": "skill", "skill": SLAM, "stat": "cost_reduction_pct", "value_min": "50", "value_max": "50",
                "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "",
                "icd_seconds": "", "source": "x", "note": ""}
        costed = {r["skill"] for r in read_csv("data/d3/barbarian_skill_values.csv") if r["token"] == "cost_resource" and not r["rune"]}
        free = sorted({r["skill_name"] for r in read_csv("data/d3/barbarian_skills.csv")} - costed)[0]
        bad = {
            "a condition (the aura is set when the worn items change)": dict(base, cond="triggered", cond_arg="3", fire_on="kill"),
            "an event": dict(base, fire_on="kill"),
            "more than the whole cost": dict(base, value_min="120", value_max="120"),
            "nothing off": dict(base, value_min="0", value_max="0"),
            "a skill that states no cost": dict(base, skill=free),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                k0k2.Table.rows_of([row])
        self.assertEqual(1, len(k0k2.Table.rows_of([base])))


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = records()
        cls.manifest = manifest()
        cls.auras = {skill: next(i for i, r in cls.manifest.items() if r["kind"] == "skill_cost_modifier" and r["name"] == "%s cost reduction" % skill)
                     for _, skill in COST_SKILLS}

    def test_one_hidden_cost_aura_per_named_skill(self):
        self.assertEqual(len(self.auras) + len(spells.CLASS_COST_CUT_SKILLS), sum(r["kind"] == "skill_cost_modifier" for r in self.manifest.values()))   # and the class skills a timed cut lowers (Vault's Tumble)
        gear = self.records[82403]      # the gear-and-paragon cost aura: the same shape, every skill's bit in place of one skill's
        header = HEADER.read_text(encoding="utf-8")
        for d3_class, skill in COST_SKILLS:
            aura = self.records[self.auras[skill]]
            self.assertEqual((spells.SPELL_EFFECT_APPLY_AURA, SPELL_AURA_ADD_PCT_MODIFIER, SPELLMOD_COST, 0, 0, 1),
                             tuple(number(aura[c]) for c in ("Effect_1", "EffectAura_1", "EffectMiscValue_1", "EffectBasePoints_1",
                                                             "EffectDieSides_1", "ImplicitTargetA_1")), skill)
            self.assertEqual(FAMILIES[d3_class], number(aura["SpellClassSet"]))
            mask = words(aura, "EffectSpellClassMaskA_%d")
            self.assertEqual((0, 0), mask[1:])
            self.assertEqual(1, bin(mask[0]).count("1"), skill)                   # one skill's bit
            self.assertEqual((0, 0, 0), words(aura, "SpellClassMask_%d"))          # no modifier reaches the aura itself
            for column in ("DurationIndex", "Attributes", "Effect_2", "Effect_3"):
                self.assertEqual(gear[column], aura[column], (skill, column))
            self.assertIn("{%s, %d}," % ('"%s"' % skill, self.auras[skill]), header)

    def test_the_aura_reaches_exactly_the_skills_records(self):
        for d3_class, skill in COST_SKILLS:
            family = FAMILIES[d3_class]
            mask = words(self.records[self.auras[skill]], "EffectSpellClassMaskA_%d")
            reached = {i for i, r in self.records.items() if affected(r, family, mask)}
            named = {i for i, r in self.records.items() if number(r["SpellClassSet"]) == family and number(r["SpellClassMask_1"])
                     and r["Name_Lang_enUS"].split(" - ")[0] == skill and self.manifest[i]["kind"] in ("active", "rune")}
            runes = {r["rune_name"] for r in read_csv("data/d3/%s_runes.csv" % d3_class.lower()) if r["skill_name"] == skill}
            self.assertEqual(len(runes) + 1, len(named), skill)                    # the skill and its five runes
            self.assertTrue(named <= reached, skill)
            self.assertEqual(set(), {self.records[i]["Name_Lang_enUS"].split(" - ")[0] for i in reached} - {skill}, skill)

    def test_the_cost_probes_are_none_of_the_skills(self):
        header = HEADER.read_text(encoding="utf-8")
        probes = [int(m[1]) for m in re.finditer(r"\{\d+, \d+, (\d+), \d+, \d+\}, // ", header)]
        self.assertEqual(len(FAMILIES), len(probes))
        for probe in probes:
            self.assertNotIn(self.manifest[probe]["name"].split(" - ")[0], {skill for _, skill in COST_SKILLS}, probe)

    def test_the_newest_combat_migration_is_the_render(self):
        updates = MODULE / "data/sql/db-world/updates"
        newest = sorted(p.name for p in updates.glob("combat_0*.sql"))[-1]
        self.assertEqual(SHELLS_SQL.read_text(encoding="utf-8"), (updates / newest).read_text(encoding="utf-8"))
        self.assertNotIn(newest, (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None)]
        # not worn: no cut
        out += clear + [(T("skillsum", SLAM, "cost_reduction_pct"), "0")]
        # worn: 50 off Seismic Slam, nothing off another skill, and the damage row is not the cost
        out += clear + [(T("wears", FURY), None), (T("skillsum", SLAM, "cost_reduction_pct"), "50"),
                        (T("skillsum", "Whirlwind", "cost_reduction_pct"), "0"), (T("element", "physical", "cost_reduction_pct"), "0")]
        for roll in (400, 450, 500):
            out += clear + [(T("wears", FURY), None), (T("value", FURY, SLAM, "damage_increase_pct", roll), None),
                            (T("factor", SLAM, "damage_increase_pct"), "%g" % (1 + roll / 100)), (T("skillsum", SLAM, "cost_reduction_pct"), "50")]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = k0k2.Rules.build(header_text, "vanished-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rule_agrees_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreaterEqual(len(want), 10)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        call = 'ActiveValues(rows, counts, "skill", skill, stat, situation))\n            sum += value;'
        mutants = {
            "the_element_rows": real.replace(call, 'ActiveValues(rows, counts, "element", skill, stat, situation))\n            sum += value;'),
            "every_skill": real.replace(call, 'ActiveValues(rows, counts, "skill", "Seismic Slam", stat, situation))\n            sum += value;'),
            "the_damage_is_the_cost": real.replace(call, 'ActiveValues(rows, counts, "skill", skill, "damage_increase_pct", situation))\n            sum += value;'),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
