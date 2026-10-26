"""Legendary rest, bead diablocraft-iv3xg: Aether Walker (a wizard wand, list row 84, K1), and the piece it builds, N-COST's added cost (N-CD, the cooldown cut, is Gesture of Orpheus's).

  "Teleport no longer has a cooldown but costs 25 Arcane Power."
  * the words are d3planner's (data.json items[698], P1_Wand_norm_unique_01: custom leg_aetherwalker, args 0: no number in the text); the numbers are the power file's, read through
    decode_pow.py (Item_Power_Passive ItemPassive_Unique_Ring_759_x1.pow: the item's own number 1; SF_0 'Resource Cost' = 25, SF_1 'Cooldown Reduction %' = 1, a fraction: 100%).
    The table (data/legendary_powers.csv) holds TWO `skill` rows for the wand: Teleport `cooldown_reduction_pct` 100 and Teleport `cost_add_resource` 25;
  * the generated SQL and the committed migration are what the generator renders, and the migration is the newest full table; the generator accepts `cooldown_reduction_pct` up to 100
    (Gesture of Orpheus's test holds the refusals) and `cost_add_resource` only as an item's one fixed cost above 0 on one skill whose sheet states no cost_resource, simply on;
  * the spell records (the generated spell_dbc rows the newest combat migration carries): Teleport has one hidden flat SPELLMOD_COST aura in the Wizard's family, its mask Teleport's bit in
    word one, so it reaches exactly Teleport's records (the skill and its five runes) and not the class's cost probe;
  * the production rules (src/combat/dc_item_power_math.h: CooldownFactor, SkillSum; dc_cost_math.h: FlatAmount) are compiled and driven with the generated rows: the cooldown is gone for Teleport
    only while the wand is worn, the cost is 25 points of Arcane Power for Teleport only, and the aura carries 25 units at the registry's scale; mutants of the rows and the rules fail the same driver;
  * source-text guards that CostAuras puts the added cost in step with the worn items. The C++ is compile-checked by syntax_check.sh and the in-game steps are in docs/test-diablocraft-iv3xg.md.
  * Archon's Teleport is the Archon skill's own ability and is not the Teleport skill: the wand does not touch it.
"""
import csv
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_legendary_powers as generator  # noqa: E402
import harness_env  # noqa: E402
from test_control_immunity_gap import number  # noqa: E402
from test_item_power_cindercoat import FAMILIES, HEADER, SHELLS_SQL, affected, manifest, records, words  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src"
MATH = SRC / "combat/dc_item_power_math.h"
COST_MATH = SRC / "combat/dc_cost_math.h"
COSTS = SRC / "combat/dc_item_powers_costs.cpp"
HARNESS = MODULE / "tests/item_power_aether_walker/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
GENERATED = max((MODULE / "data/generated").glob("legendary_powers_*_table.sql"))   # the one full table: a renumber moves it, not this file
OWNER = "P1_Wand_norm_unique_01"
SKILL = "Teleport"
ROW = re.compile(r"\('([^']*)',(\d+),'([^']*)','([^']*)','([^']*)',(-?[\d.]+),(-?[\d.]+),'([^']*)',([\d.]+),'([^']*)',([\d.]+),"
                 r"(\d+),'([^']*)','([^']*)',([\d.]+),([\d.]+)\)")
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731
g = lambda x: "%.10g" % x  # noqa: E731
SPELL_AURA_ADD_FLAT_MODIFIER, SPELLMOD_COST = 107, 14
COOLDOWN_PCT, COST = 100.0, 25.0
BLANK = ("", 0.0, "", 0.0, 0, "", "", 100.0, 0.0)


def read_csv(name):
    with (MODULE / name).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def all_rows():
    return [(m[1], int(m[2]), m[3], m[4], m[5], float(m[6]), float(m[7]), m[8], float(m[9]), m[10], float(m[11]), int(m[12]), m[13], m[14],
             float(m[15]), float(m[16])) for m in ROW.finditer(GENERATED.read_text(encoding="utf-8"))]


def mine(rows=None):
    return [r for r in (all_rows() if rows is None else rows) if r[0] == OWNER]


class Table(unittest.TestCase):
    def test_the_sources_say_no_cooldown_and_25_arcane_power(self):
        items = json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["items"]
        item = next(i for i in items if i.get("id") == OWNER)
        self.assertEqual("Aether Walker", item["name"])
        self.assertEqual("Teleport no longer has a cooldown but costs 25 Arcane Power.", item["required"]["custom"]["format"])
        self.assertEqual(0, item["required"]["custom"]["args"])
        self.assertIn("Teleport no longer has a cooldown but costs 25 Arcane Power.", (REPO / "docs/research/legendary-catalogue.csv").read_text(encoding="utf-8"))

    def test_the_power_file_has_the_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("no D3 archives on this machine")
        run = lambda *a: harness_env.run([sys.executable, str(MODULE / "scripts/decode_pow.py"), *a], capture_output=True, text=True).stdout  # noqa: E731
        power = run("power", "ItemPassive_Unique_Ring_759_x1")
        self.assertRegex(power, r"'Resource Cost' = 25\b")
        self.assertRegex(power, r"'Cooldown Reduction %' = 1\b")
        self.assertIn("ItemPassive_Unique_Ring_759_x1.pow: 1", run("item", OWNER))

    def test_two_rows_for_the_wand(self):
        self.assertEqual([(OWNER, 0, "skill", SKILL, "cooldown_reduction_pct", COOLDOWN_PCT, COOLDOWN_PCT, *BLANK),
                          (OWNER, 0, "skill", SKILL, "cost_add_resource", COST, COST, *BLANK)], sorted(mine(), key=lambda r: r[4]))

    def test_teleport_has_a_cooldown_and_no_cost_to_start_with(self):
        sheet = read_csv("data/d3/wizard_skill_values.csv")
        own = {r["token"]: r["value"] for r in sheet if r["skill"] == SKILL and not r["rune"]}
        self.assertEqual("11", own["cooldown_seconds"])
        self.assertNotIn("cost_resource", own)

    def test_the_render_is_the_newest_full_table_and_the_applied_one_is_left(self):
        self.assertEqual(GENERATED.read_bytes(), (MODULE / "data/sql/db-world/updates" / GENERATED.name).read_bytes())
        self.assertGreaterEqual(GENERATED.name, "legendary_powers_0067_table.sql")


class Generator(unittest.TestCase):
    COOLDOWN = {"owner": OWNER, "pieces": "", "kind": "skill", "skill": SKILL, "stat": "cooldown_reduction_pct", "value_min": "100", "value_max": "100", "cond": "", "cond_arg": "",
                "cond_skills": "", "stack_seconds": "", "stack_max": "", "fire_on": "", "fire_skills": "", "chance_pct": "", "icd_seconds": "", "source": "s", "note": "n"}
    COST = {**COOLDOWN, "stat": "cost_add_resource", "value_min": "25", "value_max": "25"}

    def render_with(self, cost=None, cooldown=None):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="aether-gen-", dir=str(SCRATCH)))
        try:
            shutil.copytree(MODULE / "data/d3", work / "data/d3")
            shutil.copy(MODULE / "data/legendary_power_buffs.csv", work / "data/legendary_power_buffs.csv")
            rows = read_csv("data/legendary_powers.csv")
            kept = [r for r in rows if r["owner"] != OWNER]
            with (work / "data/legendary_powers.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(kept + [{**self.COOLDOWN, **(cooldown or {})}, {**self.COST, **(cost or {})}])
            return generator.rows(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def test_the_real_rows_pass(self):
        self.assertEqual(2, len([r for r in self.render_with() if r[0] == OWNER]))

    def test_all_of_the_cooldown_is_allowed_and_no_more(self):
        self.assertEqual(100.0, [r for r in self.render_with() if r[0] == OWNER and r[4] == "cooldown_reduction_pct"][0][5])
        with self.assertRaises(ValueError):
            self.render_with(cooldown={"value_min": "100", "value_max": "101"})

    def test_it_refuses_a_cost_it_cannot_carry(self):
        refused = {
            "a range": dict(value_max="30"),
            "no cost": dict(value_min="0", value_max="0"),
            "a negative cost": dict(value_min="-5", value_max="-5"),
            "a condition": dict(cond="triggered", cond_arg="5"),
            "an event": dict(fire_on="cast", fire_skills=SKILL),
            "a set level": dict(pieces="2"),
            "two skills": dict(skill="Teleport;Slow Time"),
            "a skill that states a cost": dict(skill="Energy Twister"),
        }
        for name, edits in refused.items():
            with self.subTest(case=name):
                with self.assertRaises(ValueError):
                    self.render_with(cost=edits)


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = records()
        cls.manifest = manifest()
        cls.aura = next(i for i, r in cls.manifest.items() if r["kind"] == "skill_cost_adder" and r["name"] == "%s cost addition" % SKILL)

    def test_one_hidden_flat_cost_aura_for_teleport(self):
        self.assertEqual(1, sum(r["kind"] == "skill_cost_adder" for r in self.manifest.values()))
        gear = self.records[next(i for i, r in self.manifest.items() if r["name"] == "Resource cost reduction - gear and paragon - Wizard - cost modifier")]
        aura = self.records[self.aura]
        self.assertEqual((6, SPELL_AURA_ADD_FLAT_MODIFIER, SPELLMOD_COST, 0, 0, 1),
                         tuple(number(aura[c]) for c in ("Effect_1", "EffectAura_1", "EffectMiscValue_1", "EffectBasePoints_1", "EffectDieSides_1", "ImplicitTargetA_1")))
        self.assertEqual(FAMILIES["Wizard"], number(aura["SpellClassSet"]))
        mask = words(aura, "EffectSpellClassMaskA_%d")
        self.assertEqual((0, 0), mask[1:])
        self.assertEqual(1, bin(mask[0]).count("1"))                                  # Teleport's bit alone
        self.assertEqual((0, 0, 0), words(aura, "SpellClassMask_%d"))                  # no modifier reaches the aura itself
        for column in ("DurationIndex", "Attributes", "Effect_2", "Effect_3"):
            self.assertEqual(gear[column], aura[column], column)
        self.assertIn('{"%s", %d},' % (SKILL, self.aura), HEADER.read_text(encoding="utf-8"))
        self.assertIn("%s cost addition,%d,wizard" % (SKILL, self.aura), (MODULE / "data/generated/spell_helper_ids.csv").read_text(encoding="utf-8"))

    def test_the_aura_reaches_exactly_teleports_records(self):
        family = FAMILIES["Wizard"]
        mask = words(self.records[self.aura], "EffectSpellClassMaskA_%d")
        reached = {i for i, r in self.records.items() if affected(r, family, mask)}
        named = {i for i, r in self.records.items() if number(r["SpellClassSet"]) == family and number(r["SpellClassMask_1"])
                 and r["Name_Lang_enUS"].split(" - ")[0] == SKILL and self.manifest[i]["kind"] in ("active", "rune")}
        runes = {r["rune_name"] for r in read_csv("data/d3/wizard_runes.csv") if r["skill_name"] == SKILL}
        self.assertEqual(len(runes) + 1, len(named))                                    # the skill and its five runes
        self.assertTrue(named <= reached)
        self.assertEqual({SKILL}, {self.records[i]["Name_Lang_enUS"].split(" - ")[0] for i in reached})

    def test_teleports_records_take_the_class_resource_and_state_no_cost(self):
        """The core charges the added cost in the record's own power type: Arcane Power is Mana (one unit a point), and the records state none."""
        for i, r in self.records.items():
            if r["Name_Lang_enUS"].split(" - ")[0] == SKILL and self.manifest[i]["kind"] in ("active", "rune") and number(r["SpellClassSet"]) == FAMILIES["Wizard"]:
                self.assertEqual((0, 0), (number(r["PowerType"]), number(r["ManaCost"])), r["Name_Lang_enUS"])

    def test_the_cost_probe_is_not_teleport(self):
        header = HEADER.read_text(encoding="utf-8")
        for m in re.finditer(r"\{\d+, \d+, (\d+), \d+, \d+\}, // ", header):
            self.assertNotEqual(SKILL, self.manifest[int(m[1])]["name"].split(" - ")[0])

    def test_the_newest_combat_migration_is_the_render(self):
        updates = MODULE / "data/sql/db-world/updates"
        newest = sorted(p.name for p in updates.glob("combat_0*.sql"))[-1]
        self.assertEqual(SHELLS_SQL.read_text(encoding="utf-8"), (updates / newest).read_text(encoding="utf-8"))
        self.assertNotIn(newest, (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))
        self.assertGreaterEqual(newest, "combat_0103")


class Rules(unittest.TestCase):
    @classmethod
    def build(cls, files, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {**files}
        for other in ("dc_item_proc_math.h", "dc_proc_math.h"):
            files["combat/" + other] = (SRC / "combat" / other).read_text(encoding="utf-8")
        files["classes/dc_resource_data.h"] = (SRC / "classes/dc_resource_data.h").read_text(encoding="utf-8")
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        return Path(tempfile.mkdtemp(prefix="itemaether-%s-" % name, dir=str(SCRATCH))), binary

    def cases(self, rows):
        """[(command line, expected output line or None)]: worked out from the item's words and the power file's numbers, not from the code."""
        out = [(T("row", *r), None) for r in rows]
        out += [(T("row", "Other Wand", 0, "skill", SKILL, "cooldown_reduction_pct", 30.0, 30.0, *BLANK), None),
                (T("row", "Other Wand", 0, "skill", SKILL, "cost_add_resource", 10.0, 10.0, *BLANK), None),
                (T("row", "Other Wand", 0, "skill", "Slow Time", "cooldown_reduction_pct", 40.0, 40.0, *BLANK), None)]
        clear = [(T("clear"), None)]
        wand = clear + [(T("wears", OWNER), None)]
        # the cooldown: gone for Teleport while the wand is worn, whole, and for no other skill
        out += wand + [(T("cooldown", SKILL), "0"), (T("cooldown", "Slow Time"), "1"), (T("cooldown", "Frost Nova"), "1"), (T("cooldown", ""), "1")]
        out += clear + [(T("cooldown", SKILL), "1")]
        out += clear + [(T("wears", "Other Wand"), None), (T("cooldown", SKILL), g(0.7)), (T("cooldown", "Slow Time"), g(0.6))]
        out += clear + [(T("wears", OWNER), None), (T("wears", "Other Wand"), None), (T("cooldown", SKILL), "0"), (T("cooldown", "Slow Time"), g(0.6))]
        # the cost: 25 points on Teleport while the wand is worn, nothing on another skill, not worn, or in the bag
        out += wand + [(T("added", SKILL), "25"), (T("added", "Slow Time"), "0"), (T("added", "Energy Twister"), "0"), (T("added", ""), "0")]
        out += clear + [(T("added", SKILL), "0")]
        out += clear + [(T("wears", "Other Wand"), None), (T("added", SKILL), "10")]
        out += clear + [(T("wears", OWNER), None), (T("wears", "Other Wand"), None), (T("added", SKILL), "35")]
        # the aura's amount: whole units of the class resource at its scale, never below nothing
        for points, scale, want in ((25, 1.0, 25), (25, 10.0, 250), (25, 0.4, 10), (0, 1.0, 0), (-5, 1.0, 0), (25, 0.0, 0), (25, -1.0, 0), (2.5, 1.0, 3), (2.4, 1.0, 2), (0.4, 1.0, 0)):
            out.append((T("flat", points, scale), str(want)))
        out.append((T("arcane"), "1"))
        return out

    def drive(self, files, rows, name):
        cases = self.cases(rows)
        work, binary = self.build(files, name)
        try:
            (work / "cases.txt").write_text("\n".join(line for line, _ in cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            return [w for _, w in cases if w is not None], run.stdout.split("\n")[:-1]
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def files(self, math=None, cost=None):
        return {"combat/dc_item_power_math.h": math or MATH.read_text(encoding="utf-8"), "combat/dc_cost_math.h": cost or COST_MATH.read_text(encoding="utf-8")}

    def test_every_rule_agrees_with_the_item_text(self):
        want, got = self.drive(self.files(), mine(), "real")
        self.assertGreater(len(want), 25)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        math, cost = MATH.read_text(encoding="utf-8"), COST_MATH.read_text(encoding="utf-8")
        rows = mine()
        self.assertEqual(2, len(rows))
        want, _ = self.drive(self.files(), rows, "want")
        by_stat = {r[4]: r for r in rows}
        row_mutants = {
            "ninety_nine_percent": [by_stat["cooldown_reduction_pct"][:5] + (99.0, 99.0) + by_stat["cooldown_reduction_pct"][7:], by_stat["cost_add_resource"]],
            "twenty_four_points": [by_stat["cooldown_reduction_pct"], by_stat["cost_add_resource"][:5] + (24.0, 24.0) + by_stat["cost_add_resource"][7:]],
            "the_cost_on_another_skill": [by_stat["cooldown_reduction_pct"], by_stat["cost_add_resource"][:3] + ("Slow Time",) + by_stat["cost_add_resource"][4:]],
            "no_cost_row": [by_stat["cooldown_reduction_pct"]],
            "no_cooldown_row": [by_stat["cost_add_resource"]],
        }
        for name, mutant_rows in row_mutants.items():
            with self.subTest(mutant=name):
                _, got = self.drive(self.files(), mutant_rows, name)
                self.assertNotEqual(want, got, name + " survived")
        rule_mutants = {
            "cooldown_never_to_nothing": (math, "std::max(0.0, 1.0 - pct / 100.0)", "std::max(0.01, 1.0 - pct / 100.0)", "math"),
            "cooldown_adds_sources": (math, "factor *= std::max(0.0, 1.0 - pct / 100.0);", "factor -= pct / 100.0;", "math"),
            "cooldown_of_another_stat": (math, 'ActiveValues(rows, counts, "skill", skill, "cooldown_reduction_pct", situation)', 'ActiveValues(rows, counts, "skill", skill, "cost_reduction_pct", situation)', "math"),
            "added_cost_of_another_skill": (math, 'ActiveValues(rows, counts, "skill", skill, stat, situation))\n            sum += value;', 'ActiveValues(rows, counts, "skill", "Teleport", stat, situation))\n            sum += value;', "math"),
            "added_cost_takes_the_highest": (math, "            sum += value;\n        return sum;\n    }\n\n    // The multiplier of the `damage_per_distance_pct`", "            sum = std::max(sum, value);\n        return sum;\n    }\n\n    // The multiplier of the `damage_per_distance_pct`", "math"),
            "flat_amount_ignores_the_scale": (cost, "std::max(0.0, points) * std::max(0.0, scale)", "std::max(0.0, points)", "cost"),
            "flat_amount_goes_negative": (cost, "std::max(0.0, points) * std::max(0.0, scale)", "points * std::max(0.0, scale)", "cost"),
            "flat_amount_truncates": (cost, "std::int32_t(std::llround(std::max(0.0, points) * std::max(0.0, scale)))", "std::int32_t(std::max(0.0, points) * std::max(0.0, scale))", "cost"),
            "flat_amount_is_a_reduction": (cost, "return std::int32_t(std::llround(std::max(0.0, points) * std::max(0.0, scale)));", "return -std::int32_t(std::llround(std::max(0.0, points) * std::max(0.0, scale)));", "cost"),
        }
        for name, (text, old, new, which) in rule_mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, text.count(old), name + " does not apply")
                changed = text.replace(old, new, 1)
                _, got = self.drive(self.files(math=changed) if which == "math" else self.files(cost=changed), rows, name)
                self.assertNotEqual(want, got, name + " survived")


def cost_failures(costs):
    """What is wrong with the added cost in CostAuras ([] when it is right)."""
    flat = re.sub(r"\s+", " ", costs)
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    start = flat.find("void CostAuras(Player* player) {")
    end = flat.find("} // namespace Detail", start)
    body = flat[start:end] if start >= 0 and end > start else ""
    need("CostAuras exists", bool(body))
    adders = body[body.find("Resources::Resource const* resource"):] if "Resources::Resource const* resource" in body else ""
    need("the wearer's class resource is the unit", "Resources::Resource const* resource = Resources::Of(classId);" in adders)
    need("every adder is walked", "for (Shells::SkillCostAdder const& row : Shells::SkillCostAdders) {" in adders)
    need("the points are the worn rows' sum for the skill, under the lock",
         'std::lock_guard<std::mutex> lock(mutex); points = ItemPower::SkillSum(Data().rows, CountsOf(guid), row.skill, "cost_add_resource", SituationOf(guid)); }' in adders)
    need("the aura carries the points in whole units of the resource at its scale, and none without one",
         "PutCostAmount(player, row.id, resource ? CostMath::FlatAmount(points, resource->scale) : 0);" in adders)
    need("the reductions are still walked first", 0 <= body.find("SkillCostModifiers") < body.find("SkillCostAdders"))
    amount = flat[flat.find("void PutCostAmount(Player* player, std::uint32_t id, std::int32_t amount) {"):flat.find("} // namespace", flat.find("void PutCostAmount(Player* player, std::uint32_t id, std::int32_t amount) {"))]
    need("an aura is recast when its amount changes and removed at 0",
         "if (effect ? effect->GetAmount() == amount : amount == 0) return; if (current) player->RemoveAurasDueToSpell(id); if (amount != 0) player->CastCustomSpell(player, id, &amount, nullptr, nullptr, true);" in amount)
    need("the percent reductions still go through the same writer",
         "void PutCostAura(Player* player, std::uint32_t id, double pct) { PutCostAmount(player, id, CostMath::ModifierAmount(pct)); }" in flat)
    return wrong


class Hooks(unittest.TestCase):
    def test_cost_auras_put_the_added_cost(self):
        self.assertEqual([], cost_failures(COSTS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        real = COSTS.read_text(encoding="utf-8")
        mutants = {
            "another_resource": ("Resources::Of(classId);", "Resources::Of(0);"),
            "no_adders": ("for (Shells::SkillCostAdder const& row : Shells::SkillCostAdders)", "for (Shells::SkillCostModifier const& row : Shells::SkillCostModifiers)"),
            "another_stat": ('row.skill, "cost_add_resource"', 'row.skill, "cost_reduction_pct"'),
            "not_under_the_lock": ("                {\n                    std::lock_guard<std::mutex> lock(mutex);\n                    points = ItemPower::SkillSum(", "                {\n                    points = ItemPower::SkillSum("),
            "points_not_units": ("CostMath::FlatAmount(points, resource->scale)", "CostMath::FlatAmount(points, 1.0)"),
            "a_reduction": ("CostMath::FlatAmount(points, resource->scale)", "CostMath::ModifierAmount(points)"),
            "no_resource_guard": ("resource ? CostMath::FlatAmount(points, resource->scale) : 0", "CostMath::FlatAmount(points, resource->scale)"),
            "never_removed": ("if (amount != 0)\n                player->CastCustomSpell", "if (true)\n                player->CastCustomSpell"),
            "the_writer_is_not_shared": ("PutCostAmount(player, id, CostMath::ModifierAmount(pct));", "PutCostAmount(player, id, 0);"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                self.assertNotEqual([], cost_failures(real.replace(old, new, 1)), name + " survived")


if __name__ == "__main__":
    unittest.main()
