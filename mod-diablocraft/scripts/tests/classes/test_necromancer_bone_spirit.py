"""Bone Spirit and its five runes (src/classes/necromancer/dc_necromancer_bone_spirit*.{h,cpp}) and the shared charge store
(src/combat/dc_charge_store.h).

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_bone_spirit/harness.cpp compiles the real dc_necromancer_bone_spirit_math.h and
    dc_charge_store.h with the sheet's rune names and numbers: each name is its rune; the enemies on the way of the spirit; the charges (full at
    first, the last spent holds the button for the recharge, one lands each period, a corpse takes its second off). Planted mutations in
    both must each turn it red.
  * **The numbers.** The sheet rows come from the tooltip and agree with the power file (decode_pow.py power p6_Necro_BoneSpirit: SF_0 15,
    SF_1 3 + 1, SF_2 40, SF_7 1, SF_9 10, SF_10 0.05, SF_11 2, SF_12 10, SF_14 10, SF_15 12.5, SF_16 0.15); the Life cost is a tunable with its SF
    cited, the width of the way is the designer's standing default.
  * **It is wired.** The dispatch answers BasePct, Casting, Multipliers, Cast and RegisterScripts; the charge is spent by the cast; each rune's part.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_bone_spirit.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
FOLDER = MODULE / "src/classes/necromancer"
HEADER = "src/classes/necromancer/dc_necromancer_bone_spirit_math.h"
STORE = "src/combat/dc_charge_store.h"
HARNESS = MODULE / "tests/necromancer_bone_spirit/harness.cpp"
CODE = FOLDER / "dc_necromancer_bone_spirit.cpp"
SKILL = "Bone Spirit"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token):
    rows = [r for r in read(D3 / "necromancer_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, "")]
    assert len(rows) == 1, (rune, token, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "necromancer_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/necromancer.csv")}


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in (HEADER, STORE)}
    if mutate:
        old, new = mutate[0], mutate[1]
        path = mutate[2] if len(mutate) > 2 else HEADER
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("", "charge_count"), value("Poltergeist", "charge_count"), value("", "charge_recharge_seconds"),
               value("", "charge_recharge_reduction_seconds"), value("Astral Projection", "damage_bonus_pct")]
    return harness_env.run([str(binary)] + runes() + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 22, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", ('return Rune::AstralProjection;\n        return Rune::None;', 'return Rune::Poltergeist;\n        return Rune::None;')),
            ("a rune is no rune", ('if (name == "Panic Attack")', 'if (name == "Panic Attacks")')),
            ("every rune keeps the skill's hit", ("return rune == Rune::UnfinishedBusiness;", "return rune != Rune::None;")),
            ("Unfinished Business loses the skill's hit", ("return rune == Rune::UnfinishedBusiness;", "return false;")),
            ("the way has no end", ("return along >= 0 && along < length && aside <= width / 2.0;", "return along >= 0 && aside <= width / 2.0;")),
            ("the target is passed", ("return along >= 0 && along < length &&", "return along >= 0 && along <= length &&")),
            ("behind the caster is passed", ("return along >= 0 && along < length &&", "return along < length &&")),
            ("the way is twice as wide", ("aside <= width / 2.0", "aside <= width")),
            ("the edge of the way is out", ("aside <= width / 2.0", "aside < width / 2.0")),
            ("the sides are not told apart", ("std::fabs((ex - px) * dy - (ey - py) * dx) / length", "std::fabs((ex - px) * dx - (ey - py) * dy) / length")),
            ("a negative share lowers the damage", ("passed * std::max(0.0, perEnemyPct)", "passed * perEnemyPct")),
            ("the bonus is one enemy's", ("passed * std::max(0.0, perEnemyPct)", "std::max(0.0, perEnemyPct)")),
            ("a player starts empty", ("count = cap;\n                known = true;", "count = 0;\n                known = true;", STORE)),
            ("a charge lands a period late", ("while (next && now >= next && count < cap)", "while (next && now > next && count < cap)", STORE)),
            ("a charge never lands", ("while (next && now >= next && count < cap)", "while (false && next && now >= next && count < cap)", STORE)),
            ("the count passes the cap", ("if (count >= cap)\n            {\n                count = cap;\n                next = 0;\n            }", "if (count >= cap)\n            {\n                next = 0;\n            }", STORE)),
            ("the last charge holds nothing", ("return count ? 0 : next - now;\n        }\n\n        // The recharge", "return 0;\n        }\n\n        // The recharge", STORE)),
            ("a spend takes two", ("if (count)\n                --count;", "if (count)\n                count = count > 1 ? count - 2 : 0;", STORE)),
            ("a corpse shortens nothing", ("next = next > now + ms ? next - ms : now;", "next = next;", STORE)),
            ("a corpse shortens too much", ("next = next > now + ms ? next - ms : now;", "next = next > now + ms ? next - 2 * ms : now;", STORE)),
            ("a corpse can push the landing into the past", ("next = next > now + ms ? next - ms : now;", "next = next - ms;", STORE)),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_five_runes(self):
        self.assertEqual(runes(), ["Possession", "Panic Attack", "Poltergeist", "Unfinished Business", "Astral Projection"])

    def test_the_sheet_numbers_agree_with_the_power_file(self):
        self.assertEqual([value("", t) for t in ("damage_pct", "charge_recharge_seconds", "charge_count", "charge_recharge_reduction_seconds")],
                         [4000, 15, 3, 1])  # SF_2 40, SF_0, SF_1, SF_7
        self.assertEqual(value("Possession", "charm_duration_seconds"), 10)  # SF_9
        self.assertEqual([value("Panic Attack", t) for t in ("radius_yards", "fear_duration_seconds")], [10, 2])  # SF_12, SF_11
        self.assertEqual(value("Poltergeist", "charge_count"), 4)  # SF_1 3 + SF_13 1
        self.assertEqual([value("Unfinished Business", t) for t in ("damage_pct", "radius_yards")], [1250, 10])  # SF_15 12.5, SF_14
        self.assertEqual(value("Astral Projection", "damage_bonus_pct"), 15)  # SF_16 0.15

    def test_every_name_the_cast_reads_exists(self):
        text = CODE.read_text(encoding="utf-8")
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+?, "([a-z_]+)"'
        tokens = set(re.findall(call, text))
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet, set())
        self.assertEqual(tokens, {"damage_pct", "charge_count", "charge_recharge_seconds", "charge_recharge_reduction_seconds",
                                  "damage_bonus_pct", "charm_duration_seconds", "radius_yards", "fear_duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("", "damage_pct"), ("", "charge_count"), ("", "charge_recharge_seconds"), ("Poltergeist", "charge_count"),
                            ("Possession", "charm_duration_seconds"), ("Panic Attack", "radius_yards"), ("Panic Attack", "fear_duration_seconds"),
                            ("Unfinished Business", "damage_pct"), ("Unfinished Business", "radius_yards"),
                            ("Astral Projection", "damage_bonus_pct")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    def test_the_life_cost_is_the_power_files_and_the_way_is_alexs_default(self):
        rows = tunables()
        self.assertEqual((rows["possession_life_cost_pct"]["d3_value"], rows["possession_life_cost_pct"]["value"]), ("5", ""))  # SF_10
        self.assertIn("decode_pow.py power p6_Necro_BoneSpirit", rows["possession_life_cost_pct"]["notes"])
        self.assertEqual((rows["bone_spirit_way_yards"]["d3_value"], rows["bone_spirit_way_yards"]["value"]), ("3", ""))
        self.assertIn("standing default", rows["bone_spirit_way_yards"]["notes"])
        for name in ("possession_life_cost_pct", "bone_spirit_way_yards"):
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"])

    def test_the_code_reads_exactly_these(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)) | set(re.findall(r'WayWidth = "([a-z0-9_]+)"', text)),
                         {"possession_life_cost_pct", "bone_spirit_way_yards"})


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertIn("if (auto spirit = BoneSpirit::BasePct(spellId)) return spirit;", self.dispatch)
        self.assertIn("BoneSpirit::Casting(player, spellId);", self.dispatch)
        self.assertIn("BoneSpirit::Cast(player, spellId, targets);", self.dispatch)
        self.assertIn("BoneSpirit::Multipliers(player, spellId, out);", self.dispatch)
        self.assertIn("BoneSpirit::RegisterScripts();", self.dispatch)

    def test_unfinished_business_keeps_the_skills_number_for_the_spirits_hit(self):
        self.assertIn('KeepsTheSkillsHit(RuneAt(spellId)) ? std::optional<double>(Numbers::Get(BaseId(Skill), "damage_pct")) : std::nullopt;', self.code)

    def test_the_cast_spends_a_charge_and_holds_or_clears_the_button(self):
        self.assertIn("wait = charges[player->GetGUID().GetRawValue()].Spend(Now(), Cap(spellId), Period(player, spellId));", self.code)
        self.assertIn("SendSkillCooldown(player, spellId, std::uint32_t(wait));", self.code)
        self.assertIn('return unsigned(Numbers::Num(spellId, "charge_count"));', self.code)
        self.assertIn("ReducedCooldownMilliseconds(player, spellId,", self.code)

    def test_a_consumed_corpse_shortens_the_recharge_of_the_slotted_rune(self):
        self.assertIn("Corpses::OnConsumed(CorpsesConsumed);", self.code)
        self.assertIn("std::uint32_t const spellId = Slotted(owner, Skill); if (!spellId || taken.empty()) return;", self.code)
        self.assertIn('Millis(Numbers::Num(spellId, "charge_recharge_reduction_seconds")) * taken.size()', self.code)

    def test_possession_takes_life_and_charms_and_panic_attack_frightens_the_enemies_around_the_target(self):
        self.assertIn('if (rune == Rune::Possession) SpendLife(player, Tune("possession_life_cost_pct"));', self.code)
        self.assertIn('CharmEffect::Apply(player, target, spellId, Numbers::Num(spellId, "charm_duration_seconds"));', self.code)
        self.assertIn('Fear(player, enemy, Numbers::Num(spellId, "fear_duration_seconds"));', self.code)

    def test_unfinished_business_explodes_around_the_target(self):
        self.assertIn('Combat::Strike(player, enemy, spellId, Numbers::Num(spellId, "damage_pct"));', self.code)
        self.assertIn('Combat::Enemies(player, spellId, target->GetPosition(), Numbers::Num(spellId, "radius_yards"))', self.code)

    def test_astral_projection_counts_the_enemies_on_the_way_to_the_selected_target_and_adds_their_bonus(self):
        self.assertIn("if (Unit* target = player->GetSelectedUnit())", self.code)
        self.assertIn("enemy != target && PassedThrough(", self.code)
        self.assertIn('PassBonusPct(count, Numbers::Num(spellId, "damage_bonus_pct"))', self.code)
        self.assertIn('AddFactor(out, "Astral Projection", bonus);', self.code)


if __name__ == "__main__":
    unittest.main()
