"""Simulacrum and its five runes (src/classes/necromancer/dc_necromancer_simulacrum*.{h,cpp}), the Simulacrum of Bone in
dc_necromancer_pets.cpp, and the curses' registry that lets three curses stand on one enemy (dc_necromancer_curses*.{h,cpp}).

What this proves, and how:

  * **The rules that need no core type.** tests/necromancer_simulacrum/harness.cpp compiles the real dc_necromancer_simulacrum_math.h and
    dc_necromancer_curses_math.h with the sheet's rune names, categories and numbers: each name is its rune; Blood Debt cuts every Life cost by
    its share and no other rune does; Reservoir raises the maximum by its share; the Secondary skills are the ones repeated; a curse adds
    the other two; a blow of all the Life left is fatal; a curse takes another off unless they stand together. Planted mutations must each
    turn it red.
  * **The numbers.** The sheet rows come from the tooltip and agree with the power file (decode_pow.py power P6_Necro_Simulacrum: SF_2 15,
    SF_3 1.0, SF_4 0.75, SF_5 1.0, SF_6 10); the Life cost (the tooltip's 25%), the spawn distance (SF_0) and the number of mirrors (SF_1) are
    tunables.
  * **It is wired.** The dispatch answers Casting, Cast, Ground, Reduce and RegisterScripts; the copies rise and repeat the Secondary skills;
    the Life costs go through Blood Debt; the curses' registry keeps one curse per skill and each curse reads its own.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/classes/test_necromancer_simulacrum.py
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
HEADERS = ("src/classes/necromancer/dc_necromancer_simulacrum_math.h", "src/classes/necromancer/dc_necromancer_curses_math.h")
MATH = HEADERS[0]
CURSES_MATH = HEADERS[1]
HARNESS = MODULE / "tests/necromancer_simulacrum/harness.cpp"
CODE = FOLDER / "dc_necromancer_simulacrum.cpp"
SKILL = "Simulacrum"


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


def category(name):
    return [r["skill_name"] for r in read(D3 / "necromancer_skills.csv") if r["category"] == name]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data/tunables/necromancer.csv")}


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def scratch_tree(mutate=None):
    files = {path[len("src/"):]: (MODULE / path).read_text(encoding="utf-8") for path in HEADERS}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Blood Debt", "cost_reduction_pct"), value("Reservoir", "max_pool_pct")]
    args = runes() + [str(n) for n in numbers] + category("Secondary") + category("Curses")
    return harness_env.run([str(binary)] + args, capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 20, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        sim = MATH
        cur = CURSES_MATH
        mutations = [
            ("two runes share a name", (sim, 'return Rune::SelfSacrifice;\n        return Rune::None;', 'return Rune::BloodDebt;\n        return Rune::None;')),
            ("a rune is no rune", (sim, 'if (name == "Cursed Form")', 'if (name == "Cursed Formm")')),
            ("every rune cuts the cost", (sim, "return activeRune == Rune::BloodDebt ? std::clamp", "return activeRune != Rune::None ? std::clamp")),
            ("Blood Debt cuts nothing", (sim, "return activeRune == Rune::BloodDebt ? std::clamp", "return activeRune == Rune::None ? std::clamp")),
            ("the cut is the whole cost", (sim, "1.0 - reductionPct / 100.0, 0.0, 1.0", "0.0, 0.0, 1.0")),
            ("a cut past the cost makes it a gain", (sim, "1.0 - reductionPct / 100.0, 0.0, 1.0", "1.0 - reductionPct / 100.0, -1.0, 1.0")),
            ("a negative cut makes a cost dearer", (sim, "1.0 - reductionPct / 100.0, 0.0, 1.0", "1.0 - reductionPct / 100.0, 0.0, 2.0")),
            ("Reservoir adds nothing", (sim, "maximum * increasePct / 100.0 : 0.0", "0.0 : 0.0")),
            ("Reservoir adds its share of nothing", (sim, "maximum * increasePct / 100.0 : 0.0", "increasePct / 100.0 : 0.0")),
            ("a negative share drains the pool", (sim, "return maximum > 0 && increasePct > 0 ?", "return maximum > 0 ?")),
            ("a Primary is repeated", (sim, '{"Bone Spear", "Skeletal Mage", "Death Nova"}', '{"Bone Spear", "Skeletal Mage", "Bone Spikes"}')),
            ("the nova is cast at an enemy", (sim, 'return skill != "Death Nova";', "return true;")),
            ("a curse adds itself", (sim, "if (curse != skill && next < out.size())", "if (next < out.size())")),
            ("a curse adds one", (sim, "if (curse != skill && next < out.size())", "if (curse != skill && next < 1)")),
            ("a blow short of the Life is fatal", (sim, "return health > 0 && damage >= health;", "return health > 0 && damage >= health / 2;")),
            ("only a blow past the Life is fatal", (sim, "return health > 0 && damage >= health;", "return health > 0 && damage > health;")),
            ("the curses never stand together", (cur, "return sameSkill ? heldSpell != newSpell : !together;", "return sameSkill ? heldSpell != newSpell : true;")),
            ("the curses always stand together", (cur, "return sameSkill ? heldSpell != newSpell : !together;", "return sameSkill ? heldSpell != newSpell : false;")),
            ("the same record lifts itself", (cur, "return sameSkill ? heldSpell != newSpell : !together;", "return sameSkill ? true : !together;")),
            ("a curse that ran out is lifted", (cur, "if (!live || !heldSpell)", "if (!heldSpell)")),
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
        self.assertEqual(runes(), ["Reservoir", "Cursed Form", "Blood Debt", "Blood and Bone", "Self Sacrifice"])

    def test_the_sheet_numbers_agree_with_the_power_file(self):
        self.assertEqual([value("", t) for t in ("cooldown_seconds", "duration_seconds")], [120, 15])  # CooldownTime, SF_2
        self.assertEqual(value("Reservoir", "max_pool_pct"), 100)  # SF_5 1.0
        self.assertEqual(value("Blood Debt", "cost_reduction_pct"), 75)  # SF_4 0.75
        self.assertEqual(value("Blood and Bone", "duration_seconds"), 10)  # SF_6

    def test_the_categories_the_rules_header_names_are_the_sheets(self):
        header = (MODULE / MATH).read_text(encoding="utf-8")
        for name, constant in (("Secondary", "Secondaries"), ("Curses", "Curses")):
            listed = re.search(constant + r" = \{([^}]*)\}", header)[1]
            self.assertEqual(re.findall(r'"([^"]+)"', listed), category(name), name)

    def test_every_name_the_code_reads_exists(self):
        text = "".join(p.read_text(encoding="utf-8") for p in (CODE, FOLDER / "dc_necromancer_pets.cpp"))
        call = r'Numbers::(?:Num|Get|Own|Inherited)\((?:[^,()]|\([^()]*\))+?, "([a-z_]+)"'
        sheet = {r["token"] for r in read(D3 / "necromancer_skill_values.csv") if r["skill"] == SKILL}
        used = {t for t in re.findall(call, text) if t in sheet}
        self.assertEqual(used, {"max_pool_pct", "cost_reduction_pct", "duration_seconds"})
        mapped = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["skill"] == SKILL}
        for rune, token in (("Reservoir", "max_pool_pct"), ("Blood Debt", "cost_reduction_pct"), ("", "duration_seconds"),
                            ("Blood and Bone", "duration_seconds")):
            with self.subTest(rune=rune, token=token):
                self.assertIn((rune, token, ""), mapped)


class Tunables(unittest.TestCase):
    NUMBERS = {"simulacrum_life_cost_pct": "25", "simulacrum_spawn_yards": "8", "simulacrum_mirrors": "1"}  # tooltip, SF_0, SF_1

    def test_the_rows_hold_the_sources_numbers_and_none_of_alexs(self):
        rows = tunables()
        for name, number in self.NUMBERS.items():
            with self.subTest(name):
                self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (number, ""))
                self.assertNotIn("PLACEHOLDER", rows[name]["notes"])
                self.assertIn("decode_pow.py power P6_Necro_Simulacrum", rows[name]["notes"])

    def test_the_life_cost_is_the_sheets(self):
        skill = next(r for r in read(D3 / "necromancer_skills.csv") if r["skill_name"] == SKILL)
        self.assertEqual(float(skill["health_cost_pct"]), float(tunables()["simulacrum_life_cost_pct"]["d3_value"]))

    def test_the_code_reads_these_and_the_pets_the_rest(self):
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', CODE.read_text(encoding="utf-8"))), {"simulacrum_life_cost_pct"})
        pets = (FOLDER / "dc_necromancer_pets.cpp").read_text(encoding="utf-8")
        for name in ("simulacrum_spawn_yards", "simulacrum_mirrors", "simulacrum_life_pct"):
            self.assertIn('Tune("%s")' % name, pets)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = squeeze(CODE.read_text(encoding="utf-8"))
        self.dispatch = squeeze((FOLDER / "dc_necromancer.cpp").read_text(encoding="utf-8"))
        self.pets = squeeze((FOLDER / "dc_necromancer_pets.cpp").read_text(encoding="utf-8"))
        self.curses = squeeze((FOLDER / "dc_necromancer_curses.cpp").read_text(encoding="utf-8"))
        self.effects = squeeze((FOLDER / "dc_necromancer_effects.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        for line in ("Simulacrum::Casting(player, spellId);", "Simulacrum::Cast(player, spellId, targets);",
                     "Simulacrum::Ground(player, spellId, center);", "Simulacrum::RegisterScripts();",
                     "return Simulacrum::Reduce(victim, Passive::Reduce(victim, BoneArmor::Reduce(victim, CorpseRevive::Reduce(victim, damage))));"):
            self.assertIn(line, self.dispatch)

    def test_a_repeated_cast_costs_nothing_and_opens_nothing(self):
        # the dispatch leaves every Casting alone while a copy repeats (Rathma's Shield's opening included), and the repeat is cast without cost
        self.assertIn("if (Simulacrum::Repeating()) return; Passive::Casting(player, spellId);", self.dispatch)
        self.assertIn("if (!player || !RowOf(spellId, Skill) || repeating) return;", self.code)
        self.assertIn('SpendLife(player, Tune("simulacrum_life_cost_pct"));', self.code)

    def test_the_cast_raises_the_copy_and_blood_and_bone_a_second(self):
        self.assertIn("Pets::Simulacrum(player, false);", self.code)
        self.assertIn("if (rune == Rune::BloodAndBone) Pets::Simulacrum(player, true);", self.code)
        self.assertIn('Minions::Define("simulacrum_bone", CopyOfBone);', self.pets)
        self.assertIn('owner->GetNearPosition(float(Tune("simulacrum_spawn_yards")), bone ? std::numbers::pi_v<float> : 0.0f)', self.pets)
        self.assertIn('Minions::Raise(owner, "simulacrum_bone", at, 0, true)', self.pets)
        self.assertIn('kind.cap = unsigned(Tune("simulacrum_mirrors"));', self.pets)

    def test_each_copy_repeats_a_secondary_cast_at_the_same_enemy(self):
        self.assertIn("if (!row || repeating || !copies || !IsSecondary(row->skill)) return;", self.code)
        self.assertIn("for (unsigned copy = 0; copy < copies; ++copy) Combat::CastSkill(player, skill, aim ? ObjectAccessor::GetUnit(*player, aim) : nullptr);", self.code)
        self.assertIn("repeating = true;", self.code)
        self.assertIn("repeating = false;", self.code)
        self.assertIn("unsigned Copies(Player* player) { return Minions::Alive(player, Copy) + Minions::Alive(player, BoneCopy); }", self.code)

    def test_reservoir_adds_its_share_of_the_maximum_while_a_copy_stands(self):
        self.assertIn('value = EssenceAdded(sheet ? (*sheet)[Stat::MaxFury] - own : 0.0, Numbers::Num(spellId, "max_pool_pct"));', self.code)
        self.assertIn("Buffs::Set(player, BaseId(Skill), Stat::MaxFury, Bucket::Flat, value);", self.code)
        self.assertIn("if (rune == Rune::Reservoir) StartWatch(player);", self.code)
        self.assertIn("Reservoir(player, 0, false, false);", self.code)

    def test_cursed_form_adds_the_other_two_curses_and_lets_them_stand(self):
        self.assertIn("for (std::string_view other : OtherCurses(row->skill))", self.code)
        self.assertIn("Decrepify::Ground(player, record, center);", self.code)
        self.assertIn("Leech::Ground(player, record, center);", self.code)
        self.assertIn("Frailty::Ground(player, record, center);", self.code)
        self.assertIn("Curses::StandTogether(CursedForm);", self.code)
        self.assertIn("if (!Lifts(stand, sameSkill, live, held, spellId)) return;", self.curses)
        self.assertIn("if (std::get<2>(it->first) == skill || stand) {", self.curses)

    def test_blood_debt_cuts_every_life_cost(self):
        self.assertIn("pct * Simulacrum::LifeCostShare(player)", self.effects)
        self.assertIn('return record ? LifeCostShare(RuneAt(record), Numbers::Num(record, "cost_reduction_pct")) : 1.0;', self.code)

    def test_self_sacrifice_ends_the_copies_and_heals_in_full(self):
        self.assertIn("RuneAt(record) != Rune::SelfSacrifice || !Fatal(damage, player->GetHealth())", self.code)
        self.assertIn("Minions::Dismiss(player, Copy);", self.code)
        self.assertIn("Minions::Dismiss(player, BoneCopy);", self.code)
        self.assertIn("player->SetHealth(player->GetMaxHealth());", self.code)
        self.assertIn("return 0.0;", self.code)

    def test_each_curse_reads_its_own_skills_curse(self):
        decrepify = squeeze((FOLDER / "dc_necromancer_decrepify.cpp").read_text(encoding="utf-8"))
        leech = squeeze((FOLDER / "dc_necromancer_leech.cpp").read_text(encoding="utf-8"))
        frailty = squeeze((FOLDER / "dc_necromancer_frailty.cpp").read_text(encoding="utf-8"))
        self.assertIn("Curses::On(player, target, Skill)", decrepify)
        self.assertIn("Curses::On(player, target, Skill)", leech)
        self.assertIn("Curses::Left(player, victim, Skill)", leech)
        self.assertIn("Curses::On(player, enemy, Skill)", frailty)


if __name__ == "__main__":
    unittest.main()
