"""Cindercoat: Fire skills cost [23-30]% less (diablocraft-5cqu3, legendary build 2).

  * data/legendary_powers.csv gains Cindercoat's row (`element` fire `cost_reduction_pct` [23-30]), its numbers and words read from
    d3planner's item file and set against the tooltip the players see; the generator refuses a cost row it cannot carry (a condition, an
    event, more than 100%);
  * the spell records (the generated spell_dbc rows that combat_0061 carries): word three of each skill record's SpellClassMask is its
    element's school bit, the element read from the class sheets (a rune's own, else its skill's), and each class has one hidden
    SPELLMOD_COST aura that names the Fire bit in word three. The core's SpellInfo::IsAffected is restated over every record of the two
    families: the class's Fire aura reaches exactly its Fire skill records, nothing of the other class, and no other modifier or donor
    mask uses word three. The cost probes (the sheet's Resource Cost Reduction) are no Fire record;
  * the production rule (dc_item_power_math.h ElementSum) is driven with the generated rows through the power_math harness, and its mutants
    fail the same driver;
  * source-text guards that Refresh puts the auras in step (they prove the call is there, not that it runs; the C++ is compile-checked by
    syntax_check.sh and the in-game steps are in docs/test-diablocraft-5cqu3.md).
"""
import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as spells  # noqa: E402
from class_names import sheet_stem  # noqa: E402
from test_control_immunity_gap import insert_rows, number  # noqa: E402
import harness_env  # noqa: E402
import shutil  # noqa: E402
import test_item_power_math as power_math  # noqa: E402  (a module, so its test classes are not run twice)
from test_item_power_math import generator, planner, read_csv, tooltip, all_rows  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
SHELLS_SQL = MODULE / "data/generated/spell_shells.sql"
SHELLS_CSV = MODULE / "data/generated/spell_shells.csv"
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0061_element_cost_auras.sql"
POWERS_SQL = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))
POWERS_MIGRATION = MODULE / "data/sql/db-world/updates" / POWERS_SQL.name
HEADER = SRC / "combat/dc_spell_shells.h"
CINDERCOAT, MAGEFIST = "Unique_Chest_006_x1", "P41_Unique_Gloves_014"
# Every class the spell generator writes skill records for (a class block and its skill sheet in data/d3) has its own hidden Fire cost
# aura, so a new class joins here by itself; a class with a block and no sheet yet (only its resource records) is not in it:
# {class name as the aura's name spells it: SpellClassSet family}.
CLASS_ROWS = read_csv("data/d3/class_map.csv")
FAMILIES = {r["d3_class"]: spells.CLASS_BLOCKS[sheet_stem(r["d3_class"])].family for r in CLASS_ROWS
            if sheet_stem(r["d3_class"]) in spells.CLASS_BLOCKS and (MODULE / "data/d3" / ("%s_skills.csv" % sheet_stem(r["d3_class"]))).is_file()}
CLASS_IDS = {r["d3_class"]: int(r["class_id"]) for r in CLASS_ROWS}   # the class number the header's probe table keys by
SPELL_AURA_ADD_PCT_MODIFIER, SPELLMOD_COST = 108, 14


def source_range():
    text = planner("item_torso.js", CINDERCOAT)
    found = re.search(r'custom: \{id: "leg_cindercoat", name: "[^"]*", format: "Reduces the resource cost of Fire skills by %d%%.", '
                      r'min: (\d+), max: (\d+)\}', text)
    assert found, text
    return float(found[1]), float(found[2])


def records():
    return {int(r["ID"]): r for r in insert_rows(SHELLS_SQL.read_text(encoding="utf-8"), "spell_dbc")}


def manifest():
    with SHELLS_CSV.open(encoding="utf-8", newline="") as stream:
        return {int(r["spell_id"]): r for r in csv.DictReader(stream)}


def sheet_elements():
    """{record name: element} of every skill and rune shell, from the class sheets (a rune names its own element or keeps its skill's)."""
    out = {}
    for d3_class in FAMILIES:
        stem = sheet_stem(d3_class)
        skills = {r["skill_name"]: r["element"].strip().lower() or "physical" for r in read_csv("data/d3/%s_skills.csv" % stem)}
        out.update(skills)
        for r in read_csv("data/d3/%s_runes.csv" % stem):
            out["%s - %s" % (r["skill_name"], r["rune_name"])] = r["element"].strip().lower() or skills[r["skill_name"]]
    return out


def words(record, prefix):
    return tuple(number(record[prefix % i]) for i in (1, 2, 3))


def affected(spell, family, mask):
    """SpellInfo::IsAffected (SpellInfo.cpp): the modifier's family, then any bit of its 96-bit mask in the spell's family flags."""
    if number(spell["SpellClassSet"]) != family:
        return False
    flags = words(spell, "SpellClassMask_%d")
    return not any(mask) or any(m & f for m, f in zip(mask, flags))


class Row(unittest.TestCase):
    def test_the_row_is_the_sources(self):
        low, high = source_range()
        self.assertEqual((23, 30), (low, high))
        mine = [r for r in all_rows() if r[0] == CINDERCOAT]
        self.assertEqual([(CINDERCOAT, 0, "element", "fire", "cost_reduction_pct", low, high, "", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)], mine)
        self.assertIn("Reduces the resource cost of Fire skills by %g–%g%%." % (low, high), tooltip(CINDERCOAT))   # rolledPower's range
        pool = next(r for r in read_csv("data/d3/base_items.csv") if r["d3_id"] == CINDERCOAT)
        self.assertEqual(("Cindercoat", "yes"), (pool["d3_name"], pool["pool_version"]))

    def test_the_table_and_its_migration_are_the_render(self):
        self.assertEqual(generator.render(MODULE), POWERS_SQL.read_text(encoding="utf-8"))
        self.assertEqual(generator.render(MODULE), POWERS_MIGRATION.read_text(encoding="utf-8"))
        applied = (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8")
        self.assertNotIn(POWERS_SQL.name, applied)
        # 0005 (li0ie) stays as written: Cindercoat rides the new full replace
        self.assertNotIn(CINDERCOAT, (MODULE / "data/sql/db-world/updates/legendary_powers_0005_table.sql").read_text(encoding="utf-8"))

    def test_the_generator_refuses_a_cost_row_it_cannot_carry(self):
        base = {"owner": CINDERCOAT, "pieces": "", "kind": "element", "skill": "fire", "stat": "cost_reduction_pct", "value_min": "23",
                "value_max": "30", "cond": "", "cond_arg": "", "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "",
                "fire_skills": "", "chance_pct": "", "icd_seconds": "", "source": "x", "note": ""}
        bad = {
            "a condition (the aura is set when the worn items change)": dict(base, cond="triggered", cond_arg="3", fire_on="kill"),
            "an event": dict(base, fire_on="kill"),
            "more than the whole cost": dict(base, value_max="120"),
            "an element that is not one": dict(base, skill="shadow"),
        }
        for name, row in bad.items():
            with self.subTest(name), self.assertRaises(ValueError):
                power_math.Table.rows_of([row])
        self.assertEqual(1, len(power_math.Table.rows_of([base])))


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = records()
        cls.manifest = manifest()
        cls.auras = {d3_class: next(i for i, r in cls.manifest.items()
                                    if r["kind"] == "element_cost_modifier" and r["name"] == "Fire skills cost reduction - %s" % d3_class)
                     for d3_class in FAMILIES}

    def test_one_hidden_fire_cost_aura_per_class(self):
        self.assertEqual(len(FAMILIES), sum(r["kind"] == "element_cost_modifier" for r in self.manifest.values()))
        gear = self.records[82403]      # the gear-and-paragon cost aura: the same shape, every skill's bit in place of the element's
        for d3_class, family in FAMILIES.items():
            aura = self.records[self.auras[d3_class]]
            self.assertEqual((spells.SPELL_EFFECT_APPLY_AURA, SPELL_AURA_ADD_PCT_MODIFIER, SPELLMOD_COST, 0, 0, 1),
                             tuple(number(aura[c]) for c in ("Effect_1", "EffectAura_1", "EffectMiscValue_1", "EffectBasePoints_1",
                                                             "EffectDieSides_1", "ImplicitTargetA_1")), d3_class)
            self.assertEqual((0, 0, spells.SCHOOL["fire"]), words(aura, "EffectSpellClassMaskA_%d"), d3_class)
            self.assertEqual(family, number(aura["SpellClassSet"]))
            self.assertEqual((0, 0, 0), words(aura, "SpellClassMask_%d"))           # no modifier reaches the aura itself
            for column in ("DurationIndex", "Attributes", "Effect_2", "Effect_3"):
                self.assertEqual(gear[column], aura[column], (d3_class, column))
            self.assertIn("{%d, \"fire\", %d}, // %s" % (CLASS_IDS[d3_class], self.auras[d3_class], d3_class),
                          HEADER.read_text(encoding="utf-8"))

    def test_word_three_is_the_sheets_element(self):
        elements = sheet_elements()
        seen = 0
        for identifier, r in self.records.items():
            if number(r["SpellClassSet"]) not in FAMILIES.values():
                continue
            bit = number(r["SpellClassMask_1"])
            expected = spells.SCHOOL[self.manifest[identifier]["element"]] if bit else 0
            self.assertEqual(expected, number(r["SpellClassMask_3"]), r["Name_Lang_enUS"])
            # the sheets' key, not the name the player reads: the Shaman's Earthquake shows as the Barbarian's
            key = self.manifest[identifier]["name"]
            if self.manifest[identifier]["kind"] in ("active", "rune") and key in elements:
                self.assertEqual(spells.SCHOOL[elements[key]], number(r["SpellClassMask_3"]), key)
                seen += 1
        self.assertGreater(seen, 250)

    def test_the_fire_aura_reaches_exactly_the_classs_fire_skills(self):
        elements = sheet_elements()
        for d3_class, family in FAMILIES.items():
            mask = words(self.records[self.auras[d3_class]], "EffectSpellClassMaskA_%d")
            reached = {i for i, r in self.records.items() if affected(r, family, mask)}
            fire = {i for i, r in self.records.items() if number(r["SpellClassSet"]) == family and number(r["SpellClassMask_1"])
                    and self.manifest[i]["element"] == "fire"}
            self.assertEqual(fire, reached, d3_class)
            # every skill and rune shell of the class the sheets call Fire, and none they do not
            shells = {self.manifest[i]["name"]: i for i, r in self.records.items()
                      if number(r["SpellClassSet"]) == family and self.manifest[i]["kind"] in ("active", "rune")}
            named = {name: i for name, i in shells.items() if name in elements}
            self.assertGreater(len(named), 100, d3_class)
            self.assertEqual({i for name, i in named.items() if elements[name] == "fire"}, reached & set(named.values()), d3_class)
        self.assertIn(81043, {i for i, r in self.records.items()                       # Whirlwind - Volcanic Eruption: its ticks ask the core
                              if affected(r, FAMILIES["Barbarian"], words(self.records[self.auras["Barbarian"]], "EffectSpellClassMaskA_%d"))})

    def test_nothing_else_uses_word_three(self):
        for identifier, r in self.records.items():
            if number(r["SpellClassSet"]) not in FAMILIES.values() or self.manifest[identifier]["kind"] == "element_cost_modifier":
                continue
            for prefix in ("EffectSpellClassMaskA_3", "EffectSpellClassMaskB_3", "EffectSpellClassMaskC_3"):
                self.assertEqual(0, number(r[prefix]), (r["Name_Lang_enUS"], prefix))

    def test_the_cost_probes_are_no_fire_record(self):
        header = HEADER.read_text(encoding="utf-8")
        probes = [int(m[1]) for m in re.finditer(r"\{\d+, \d+, (\d+), \d+, \d+\}, // ", header)]
        self.assertEqual(len(FAMILIES), len(probes))
        for probe in probes:
            self.assertNotEqual("fire", self.manifest[probe]["element"], probe)

    def test_the_migration_is_the_render(self):
        # Every record 0061 brought is, in the generated render, field for field what the newest migration that writes it carries: a
        # later migration may change a record on purpose (combat_0087 moved the ManaCost scale) and this stays green; a render that
        # drifts from the newest writer, or a record that lost its place, fails. Nothing is asserted about records 0061 did not bring.
        sql = SHELLS_SQL.read_text(encoding="utf-8")
        brought = {int(r["ID"]): r for r in insert_rows(MIGRATION.read_text(encoding="utf-8"), "spell_dbc")}
        self.assertTrue(brought)
        for spell in (82418, 83364):   # 0061 brought both, and a later full render (Stone Gauntlets' combat_0064) keeps them
            self.assertIn(spell, brought)
        newest, pending = {}, set(brought)
        for path in sorted(MIGRATION.parent.glob("combat_0*.sql"), reverse=True):   # newest first: stop once every record has its writer
            if not pending:
                break
            for r in insert_rows(path.read_text(encoding="utf-8"), "spell_dbc"):
                if int(r["ID"]) in pending:
                    newest[int(r["ID"])] = r
                    pending.discard(int(r["ID"]))
        self.assertEqual(set(), pending)
        for spell in brought:
            self.assertEqual(newest[spell], self.records.get(spell), spell)
        self.assertIn("DELETE FROM `spell_dbc` WHERE `ID` BETWEEN 81000 AND ", sql)
        self.assertIn(83600, self.records)   # e719a's 83600 is still in the render
        self.assertNotIn("combat_0061", (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))


class Rules(unittest.TestCase):
    def cases(self):
        T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
        out = [(T("row", *r), None) for r in all_rows()]
        clear = [(T("clear"), None)]
        low, high = source_range()
        # nothing worn, or rolled and not worn: no cut
        out += clear + [(T("element", "fire", "cost_reduction_pct"), "0"), (T("wears", CINDERCOAT), None),
                        (T("element", "fire", "cost_reduction_pct"), "0")]
        out += clear + [(T("value", CINDERCOAT, "fire", "cost_reduction_pct", 27), None), (T("element", "fire", "cost_reduction_pct"), "0")]
        for roll in (low, 27, high):
            out += clear + [(T("wears", CINDERCOAT), None), (T("value", CINDERCOAT, "fire", "cost_reduction_pct", roll), None)]
            out += [(T("element", e, "cost_reduction_pct"), "%g" % (roll if e == "fire" else 0)) for e in generator.ELEMENTS]
            out += [(T("element", "fire", "damage_pct"), "0")]                       # not Fire damage
        # with Magefist: each number in its own bucket
        out += clear + [(T("wears", CINDERCOAT), None), (T("wears", MAGEFIST), None), (T("value", CINDERCOAT, "fire", "cost_reduction_pct", 25), None),
                        (T("value", MAGEFIST, "fire", "damage_pct", 18), None), (T("element", "fire", "cost_reduction_pct"), "25"),
                        (T("element", "fire", "damage_pct"), "18")]
        # a Primal stores the top of the range
        out += [(T("roll", CINDERCOAT, 1), "power:fire:cost_reduction_pct=%g;" % high)]
        return out

    def drive(self, header_text, name):
        cases = self.cases()
        work, binary = power_math.Rules.build(header_text, "cindercoat-" + name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_rule_agrees_with_the_source(self):
        want, got = self.drive(MATH.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        sum_call = 'ActiveValues(rows, counts, "element", element, stat, situation)'
        mutants = {
            "every_element_is_fire": real.replace(sum_call, 'ActiveValues(rows, counts, "element", "fire", stat, situation)'),
            "the_stat_is_ignored": real.replace(sum_call, 'ActiveValues(rows, counts, "element", element, "cost_reduction_pct", situation)'),
            "damage_is_the_cost": real.replace(sum_call, 'ActiveValues(rows, counts, "element", element, "damage_pct", situation)'),
        }
        for name, mutant in mutants.items():
            self.assertTrue(real != mutant, "the %s mutation no longer applies" % name)
            want, got = self.drive(mutant, name)
            self.assertNotEqual(want, got, "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
