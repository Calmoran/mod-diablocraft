"""A timed cut to a skill's cost, the shared piece (src/combat/dc_cost_cut*.h/.cpp), and Vault's Tumble on it (diablocraft-wkous).

Tumble: "After using Vault, your next Vault within 6 seconds has its Discipline cost reduced by 50%." Built first as the full price taken and half given back after the
cast; the designer ruled it a real cut: the next Vault costs half up front, through the hidden cost modifier, and the full cost is never taken.

What this proves, and how:

  * **The rules that need no core type.** tests/cost_cut/harness.cpp compiles the real dc_cost_cut_math.h and is driven with cases from the meaning of "N% less for S
    seconds": a cut lasts S seconds from the moment it is given (the end exclusive), never takes off more than the whole cost, no percent or no seconds is no cut, and two
    cuts of different sources multiply (50% and 50% leave a quarter). Planted differences in a scratch copy of the header must each make the driver fail.
  * **The hidden cost aura.** Vault has one hidden flat-percent SPELLMOD_COST aura in the Demon Hunter's family (the same record kind a worn item's cost cut uses, built by
    generate_spells.py from CLASS_COST_CUT_SKILLS), its mask Vault's bit alone, so it reaches the skill and its five runes and nothing else and not the class's cost probe;
    the newest combat migration is the render.
  * **The wiring.** The cost the core charges comes from that aura, so the cut is in place BEFORE the cast: CostCut::Hold stores it under a key, puts the cost auras where it
    is now and again where it ends; the cost auras take the combined percent of the worn items' rows and the timed cuts; Vault's Tumble cast gives the cut for the rune's
    seconds and percent (each Tumble Vault starts the window again), and nothing is paid back (no Energize, no power cost read in the hook).

What it does not prove: anything on a running server. The Discipline bar showing the half price and never the full one is docs/test-diablocraft-wkous.md's, live.

    python mod-diablocraft/scripts/tests/combat/test_cost_cut.py
"""
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as spells  # noqa: E402
import harness_env  # noqa: E402
from test_control_immunity_gap import number  # noqa: E402
from test_item_power_cindercoat import FAMILIES, HEADER, SHELLS_SQL, affected, manifest, records, words  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
SRC = MODULE / "src/combat"
MATH = SRC / "dc_cost_cut_math.h"
ENGINE = SRC / "dc_cost_cut.cpp"
ENGINE_H = SRC / "dc_cost_cut.h"
COSTS = SRC / "dc_item_powers_costs.cpp"
POWERS_H = SRC / "dc_item_powers.h"
COMBAT = SRC / "dc_combat.cpp"
VAULT = MODULE / "src/classes/demon_hunter/dc_demon_hunter_vault.cpp"
HARNESS = MODULE / "tests/cost_cut/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
SKILL = "Vault"
SPELL_AURA_ADD_PCT_MODIFIER, SPELLMOD_COST = 108, 14
T = lambda *cells: "\t".join(str(c) for c in cells)  # noqa: E731


def cases():
    out = []
    for pct, now, seconds, want in ((50, 1000, 6, "pct=50 until=7000"), (50, 0, 0.5, "pct=50 until=500"), (150, 1000, 6, "pct=100 until=7000"), (100, 0, 1, "pct=100 until=1000"),
                                    (0, 1000, 6, "pct=0 until=0"), (-20, 1000, 6, "pct=0 until=0"), (50, 1000, 0, "pct=0 until=0"), (50, 1000, -4, "pct=0 until=0")):
        out.append((T("given", pct, now, seconds), want))
    for pct, until, now, want in ((50, 7000, 6999, 1), (50, 7000, 7000, 0), (50, 7000, 20000, 0), (50, 7000, 0, 1), (0, 7000, 5000, 0), (-5, 7000, 5000, 0)):
        out.append((T("live", pct, until, now), str(want)))
    for pct, want in ((30, "pct=30 until=18446744073709551615"), (50, "pct=50 until=18446744073709551615"), (150, "pct=100 until=18446744073709551615"), (0, "pct=0 until=0"), (-5, "pct=0 until=0")):
        out.append((T("standing", pct), want))
    for pct, now, want in ((30, 0, 1), (30, 10 ** 15, 1), (30, 2 ** 40, 1)):
        out.append((T("live", pct, 18446744073709551615, now), str(want)))
    for a, b, want in ((0, 0, "0"), (50, 0, "50"), (0, 50, "50"), (50, 50, "75"), (30, 20, "44"), (100, 50, "100"), (150, 50, "100"), (-10, 50, "50"), (50, -10, "50"), (25, 25, "43.75")):
        out.append((T("combine", a, b), want))
    return out


def drive(header_text, name="real"):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files={"combat/dc_cost_cut_math.h": header_text})
    work = Path(tempfile.mkdtemp(prefix="costcut-%s-" % name, dir=str(SCRATCH)))
    try:
        lines = cases()
        (work / "cases.txt").write_text("\n".join(line for line, _ in lines) + "\n")
        run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
        assert run.returncode == 0, run.stderr
        return [w for _, w in lines if w is not None], run.stdout.split("\n")[:-1]
    finally:
        shutil.rmtree(work, ignore_errors=True)


class Rules(unittest.TestCase):
    def test_every_rule_agrees_with_the_meaning(self):
        want, got = drive(MATH.read_text(encoding="utf-8"))
        self.assertGreater(len(want), 20)
        self.assertEqual(want, got)

    def test_the_mutants_fail_the_same_driver(self):
        real = MATH.read_text(encoding="utf-8")
        want, _ = drive(real)
        mutants = {
            "no_percent_is_a_cut": ("if (pct <= 0 || seconds <= 0)", "if (seconds <= 0)"),
            "no_seconds_is_a_cut": ("if (pct <= 0 || seconds <= 0)", "if (pct <= 0)"),
            "more_than_the_cost": ("{std::min(pct, 100.0), now", "{pct, now"),
            "the_end_is_in_seconds": ("now + static_cast<std::uint64_t>(seconds * 1000.0)", "now + static_cast<std::uint64_t>(seconds)"),
            "the_end_is_inclusive": ("return held.pct > 0 && now < held.until;", "return held.pct > 0 && now <= held.until;"),
            "a_cut_of_nothing_stands": ("return held.pct > 0 && now < held.until;", "return now < held.until;"),
            "never_over": ("return held.pct > 0 && now < held.until;", "return held.pct > 0;"),
            "a_standing_cut_ends": ("return {std::min(pct, 100.0), UINT64_MAX};", "return {std::min(pct, 100.0), 1000000};"),
            "no_percent_stands": ("        if (pct <= 0)\n            return {};\n        return {std::min(pct, 100.0), UINT64_MAX};", "        return {std::min(pct, 100.0), UINT64_MAX};"),
            "a_standing_cut_is_more_than_the_cost": ("return {std::min(pct, 100.0), UINT64_MAX};", "return {pct, UINT64_MAX};"),
            "cuts_add": ("return 100.0 * (1.0 - (1.0 - a / 100.0) * (1.0 - b / 100.0));", "return std::min(100.0, a + b);"),
            "the_bigger_cut_wins": ("return 100.0 * (1.0 - (1.0 - a / 100.0) * (1.0 - b / 100.0));", "return std::max(a, b);"),
            "a_negative_cut_adds_cost": ("double const a = std::clamp(aPct, 0.0, 100.0), b = std::clamp(bPct, 0.0, 100.0);", "double const a = aPct, b = bPct;"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply")
                _, got = drive(real.replace(old, new, 1), name)
                self.assertNotEqual(want, got, name + " survived")


CUT_SKILLS = {"Vault": "Demon Hunter", "Caltrops": "Demon Hunter", "Smoke Screen": "Demon Hunter", "Shadow Power": "Demon Hunter", "Marked for Death": "Demon Hunter",
             "Command Skeletons": "Necromancer", "Decrepify": "Necromancer", "Leech": "Necromancer", "Frailty": "Necromancer",
             "Lava Burst": "Shaman", "Chain Lightning": "Shaman", "Earthquake (Shaman)": "Shaman", "Elemental Blast": "Shaman"}


class Aura(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = records()
        cls.manifest = manifest()
        cls.auras = {skill: next(i for i, r in cls.manifest.items() if r["kind"] == "skill_cost_modifier" and r["name"] == "%s cost reduction" % skill)
                     for skill in CUT_SKILLS}

    def test_the_skills_are_exactly_the_class_code_ones(self):
        self.assertEqual(set(CUT_SKILLS), set(spells.CLASS_COST_CUT_SKILLS))
        for skill in CUT_SKILLS:
            self.assertIn(skill, spells.skill_cost_skills())

    def test_each_has_the_hidden_percent_aura_in_its_classs_family(self):
        for skill, d3_class in CUT_SKILLS.items():
            with self.subTest(skill):
                aura = self.records[self.auras[skill]]
                gear = self.records[next(i for i, r in self.manifest.items() if r["name"].startswith("Resource cost reduction - gear and paragon - %s" % d3_class))]
                self.assertEqual((6, SPELL_AURA_ADD_PCT_MODIFIER, SPELLMOD_COST, 0, 0, 1),
                                 tuple(number(aura[c]) for c in ("Effect_1", "EffectAura_1", "EffectMiscValue_1", "EffectBasePoints_1", "EffectDieSides_1", "ImplicitTargetA_1")))
                self.assertEqual(FAMILIES[d3_class], number(aura["SpellClassSet"]))
                mask = words(aura, "EffectSpellClassMaskA_%d")
                self.assertEqual((0, 0), mask[1:])
                self.assertEqual(1, bin(mask[0]).count("1"))
                self.assertEqual((0, 0, 0), words(aura, "SpellClassMask_%d"))
                for column in ("DurationIndex", "Attributes", "Effect_2", "Effect_3"):
                    self.assertEqual(gear[column], aura[column], column)
                self.assertIn('{"%s", %d},' % (skill, self.auras[skill]), HEADER.read_text(encoding="utf-8"))

    def test_each_aura_reaches_exactly_its_skills_records(self):
        for skill, d3_class in CUT_SKILLS.items():
            with self.subTest(skill):
                family = FAMILIES[d3_class]
                mask = words(self.records[self.auras[skill]], "EffectSpellClassMaskA_%d")
                reached = {i for i, r in self.records.items() if affected(r, family, mask)}
                named = {i for i, r in self.records.items() if number(r["SpellClassSet"]) == family and number(r["SpellClassMask_1"])
                         and self.manifest[i]["name"].split(" - ")[0] == skill and self.manifest[i]["kind"] in ("active", "rune")}
                self.assertEqual(6, len(named))                                          # the skill and its five runes
                self.assertTrue(named <= reached)
                # The skill is named as the manifest keys it (the client names the Shaman's Earthquake "Earthquake").
                self.assertEqual({skill}, {self.manifest[i]["name"].split(" - ")[0] for i in reached})

    def test_the_cost_probes_are_none_of_the_skills(self):
        for m in re.finditer(r"\{\d+, \d+, (\d+), \d+, \d+\}, // ", HEADER.read_text(encoding="utf-8")):
            self.assertNotIn(self.manifest[int(m[1])]["name"].split(" - ")[0], CUT_SKILLS)

    def test_the_newest_combat_migration_is_the_render(self):
        updates = MODULE / "data/sql/db-world/updates"
        newest = sorted(p.name for p in updates.glob("combat_0*.sql"))[-1]
        self.assertEqual(SHELLS_SQL.read_text(encoding="utf-8"), (updates / newest).read_text(encoding="utf-8"))
        self.assertNotIn(newest, (MODULE / "data/sql/applied_migrations.csv").read_text(encoding="utf-8"))


def failures(engine, costs, powers_h, combat, vault, header=None):
    flat_h = re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", header if header is not None else ENGINE_H.read_text(encoding="utf-8")))
    flat = re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", engine)).replace("( ", "(").replace(" )", ")")
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    hold = flat[flat.find("void Hold("):flat.find("double Pct(")]
    need("a cut is stored per player, skill and key, and a second one under the key replaces the first",
         "auto& mine = held[player->GetGUID().GetRawValue()][std::string(skill)]; if (Live(given, Now())) mine[key] = given; else mine.erase(key);" in hold)
    need("the cut is given for seconds from now", "Held const given = Given(pct, Now(), seconds);" in hold)
    need("the cost auras are put where the cut is now, and again where it ends",
         "ItemPowers::RefreshCostAuras(player); if (Live(given, Now())) player->m_Events.AddEventAtOffset([player] { ItemPowers::RefreshCostAuras(player); },"
         " std::chrono::milliseconds(static_cast<std::uint64_t>(seconds * 1000.0) + 1));" in hold)
    need("the lock is let go before the auras are refreshed", hold.find("std::lock_guard<std::mutex> guard(mutex);") < hold.find("} // The core charges") if "} // The core charges" in hold else
         hold.find("std::lock_guard<std::mutex> guard(mutex);") < hold.find("ItemPowers::RefreshCostAuras(player); if (Live"))
    stand = flat[flat.find("void Stand("):flat.find("double Pct(")]
    need("a standing cut is stored under the key like a timed one, with no end, and the auras follow",
         "Held const standing = Standing(pct);" in stand and "mine[key] = standing; else mine.erase(key); } ItemPowers::RefreshCostAuras(player);" in stand
         and "AddEventAtOffset" not in stand)
    need("the header declares it", "void Stand(Player* player, std::string_view skill, std::uint32_t key, double pct);" in flat_h)
    pct = flat[flat.find("double Pct("):flat.find("void Clear(")]
    need("the live cuts of the skill are combined", "if (Live(cut, now)) pct = Combine(pct, cut.pct);" in pct and "auto cuts = mine->second.find(std::string(skill));" in pct)
    clear = flat[flat.find("void Clear("):flat.find("void RegisterScripts()")]
    need("a cleared player's auras follow", "held.erase(player->GetGUID().GetRawValue()); } ItemPowers::RefreshCostAuras(player);" in clear)
    need("the cuts go with the player on logout", "PLAYERHOOK_ON_LOGOUT" in flat and "void OnPlayerLogout(Player* player) override { Clear(player); }" in flat)
    cflat = re.sub(r"\s+", " ", re.sub(r"//[^\n]*", "", costs))
    need("the skill cost auras take the combined percent of the worn items' rows and the timed cuts",
         "pct = CostCut::Combine(pct, CostCut::Pct(player, row.skill)); PutCostAura(player, row.id, pct);" in cflat and '#include "dc_cost_cut.h"' in costs)
    need("the cost auras can be refreshed from outside", "void RefreshCostAuras(Player* player) { if (player) Detail::CostAuras(player); }" in cflat)
    need("the header declares it", "void RefreshCostAuras(Player*);" in powers_h)
    need("the scripts are registered with the combat's", "CostCut::RegisterScripts();" in combat and '#include "dc_cost_cut.h"' in combat)
    hook = re.sub(r"\s+", " ", vault[vault.index("class CastHook"):vault.index("bool Is(")])
    need("only a Vault of the Tumble rune that the player cast gives the cut", "if (!player || !info || spell->IsTriggered() || RuneAt(info->Id) != Rune::Tumble) return;" in hook)
    need("the cut is the rune's percent for the rune's seconds, under the skill's key",
         'CostCut::Hold(player, Skill, BaseId(Skill), Numbers::Num(info->Id, "cost_reduction_pct"), Numbers::Num(info->Id, "duration_seconds"));' in hook)
    need("nothing is paid back after the cast", not any(word in vault for word in ("Energize", "GetPowerCost", "Refund", "lastCast")))
    return wrong


class Wiring(unittest.TestCase):
    def test_the_cut_is_in_place_before_the_cast(self):
        self.assertEqual([], failures(*(p.read_text(encoding="utf-8") for p in (ENGINE, COSTS, POWERS_H, COMBAT, VAULT))))

    def test_the_source_guards_fail_their_mutants(self):
        engine, costs, powers_h, combat, vault = (p.read_text(encoding="utf-8") for p in (ENGINE, COSTS, POWERS_H, COMBAT, VAULT))
        mutants = [
            ("engine", "the_cut_is_not_stored", "mine[key] = given;", "mine[0] = given;"),
            ("engine", "a_zero_cut_stays", "mine[key] = given;\n            else\n                mine.erase(key);", "mine[key] = given;"),
            ("engine", "the_cut_is_for_no_time", "Given(pct, Now(), seconds)", "Given(pct, Now(), 0)"),
            ("engine", "the_auras_are_not_refreshed", "        ItemPowers::RefreshCostAuras(player);\n        if (Live(given, Now()))", "        if (Live(given, Now()))"),
            ("engine", "the_end_is_not_refreshed", "[player] { ItemPowers::RefreshCostAuras(player); },", "[player] {},"),
            ("engine", "only_the_first_cut_counts", "if (Live(cut, now))\n                pct = Combine(pct, cut.pct);", "if (Live(cut, now))\n                pct = cut.pct;"),
            ("engine", "a_standing_cut_has_an_end", "Held const standing = Standing(pct);", "Held const standing = Given(pct, Now(), 1.0);"),
            ("engine", "a_standing_cut_is_not_stored", "mine[key] = standing;\n            else\n                mine.erase(key);\n        }\n        ItemPowers::RefreshCostAuras(player);\n    }\n\n    double Pct(", "mine.erase(key);\n        }\n        ItemPowers::RefreshCostAuras(player);\n    }\n\n    double Pct("),
            ("engine", "a_standing_cut_does_not_move_the_auras", "mine.erase(key);\n        }\n        ItemPowers::RefreshCostAuras(player);\n    }\n\n    double Pct(", "mine.erase(key);\n        }\n    }\n\n    double Pct("),
            ("engine", "stays_after_logout", "void OnPlayerLogout(Player* player) override\n            {\n                Clear(player);\n            }", "void OnPlayerLogout(Player* player) override\n            {\n            }"),
            ("costs", "the_items_alone", "pct = CostCut::Combine(pct, CostCut::Pct(player, row.skill));", ""),
            ("costs", "the_cuts_alone", "pct = CostCut::Combine(pct, CostCut::Pct(player, row.skill));", "pct = CostCut::Pct(player, row.skill);"),
            ("costs", "no_refresh", "        if (player)\n            Detail::CostAuras(player);", ""),
            ("powers_h", "not_declared", "    void RefreshCostAuras(Player*);\n", ""),
            ("combat", "not_registered", "        CostCut::RegisterScripts();\n", ""),
            ("vault", "no_cut", 'CostCut::Hold(player, Skill, BaseId(Skill), Numbers::Num(info->Id, "cost_reduction_pct"), Numbers::Num(info->Id, "duration_seconds"));', ""),
            ("vault", "the_wrong_percent", 'Numbers::Num(info->Id, "cost_reduction_pct"), Numbers::Num(info->Id, "duration_seconds"));', 'Numbers::Num(info->Id, "duration_seconds"), Numbers::Num(info->Id, "cost_reduction_pct"));'),
            ("vault", "every_rune_cuts", "|| RuneAt(info->Id) != Rune::Tumble", ""),
            ("vault", "a_refund_comes_back", 'CostCut::Hold(player, Skill,', 'Resources::Energize(player, Resources::Discipline, info->Id, 1.0);\n                CostCut::Hold(player, Skill,'),
        ]
        texts = {"engine": engine, "costs": costs, "powers_h": powers_h, "combat": combat, "vault": vault}
        for which, name, old, new in mutants:
            with self.subTest(mutant=name):
                self.assertEqual(1, texts[which].count(old), name + " does not apply")
                changed = {**texts, which: texts[which].replace(old, new, 1)}
                self.assertNotEqual([], failures(changed["engine"], changed["costs"], changed["powers_h"], changed["combat"], changed["vault"]), name + " survived")


if __name__ == "__main__":
    unittest.main()
