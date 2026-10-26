"""Electrocute jumps as D3 (the builder for Velvet Camaral and Myken's Ball of Hate).

What this proves, and how:

  * **The jumps.** tests/wizard_electrocute_jumps/harness.cpp compiles the real dc_wizard_chain.h and feeds it the
    sheet's own numbers (wizard_skill_values.csv: the skill's target_count 2, Chain Lightning's 10; the tunable jump
    radius from data/tunables/wizard.csv): the skill jumps to 2 more enemies, Chain Lightning electrocutes 10 in all,
    Lightning Blast and Arc Lightning do not jump, a lone target is unchanged, a jump hits a second enemy, each jump is
    the nearest enemy within the radius of the one the bolt is on (Combat::Enemies' search in production, the harness's
    own on its line) and never one it has hit (unless the re-hit flag,
    Myken's seam, is set). Planted mutations of the header must each make it fail.
  * **The numbers are D3's.** The sheet's counts match the D3 text (the skill's "additional enemies", Chain Lightning's
    "maximum number of enemies that can be electrocuted"); the radius row carries Power/Wizard_Electrocute.pow SF_2
    'Target Search Radius' 15. Every Electrocute record keeps a chain count above 1, so the core asks for the chain
    targets and dc_ability_targets::Chain answers.
  * **The wiring.** dc_combat_resolve.cpp registers Chain on Electrocute's TARGET_UNIT_TARGET_ENEMY, Chain puts Wizard::Jumps
    into the core's chain list and `native`, and ResolveTargets' single_enemy adds `native` after the aimed enemy, each
    a hit of its own; dc_wizard_electrocute.cpp's Jumps reads the count, the tunable and the walk from the header. Planted mutations
    of the sources must each fail the guards.

What it does not prove: anything on a running server (docs/test-diablocraft-d00zm.md).

    python mod-diablocraft/scripts/tests/classes/test_wizard_electrocute_jumps.py
"""

import csv
import io
import re
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/wizard/dc_wizard_chain.h"
HARNESS = "tests/wizard_electrocute_jumps/harness.cpp"
COMBAT = MODULE / "src" / "combat" / "dc_combat_resolve.cpp"
WIZARD = MODULE / "src" / "classes" / "wizard" / "dc_wizard_electrocute.cpp"
SKILL = "Electrocute"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def target_count(rune):
    rows = [r for r in read(D3 / "wizard_skill_values.csv")
            if (r["skill"], r["rune"], r["token"]) == (SKILL, rune, "target_count")]
    assert len(rows) == 1, (rune, len(rows))
    return float(rows[0]["value"])


def radius_row():
    rows = [r for r in read(MODULE / "data" / "tunables" / "wizard.csv") if r["name"] == "electrocute_jump_radius_yards"]
    assert len(rows) == 1, len(rows)
    return rows[0]


def radius():
    row = radius_row()
    return float(row["value"] or row["d3_value"])


def scratch_tree(mutate=None):
    """The header one build stages ({path under src/: text}); the mutation edits it."""
    text = (MODULE / HEADER).read_text(encoding="utf-8")
    if mutate:
        old, new = mutate
        if text.count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once")
        text = text.replace(old, new)
    return {HEADER[len("src/"):]: text}


def build_and_run(tree):
    try:
        binary = harness_env.build([MODULE / HARNESS], flags=["-std=c++20", "-O1"], files=tree)
    except harness_env.BuildError as error:
        return subprocess.CompletedProcess([], 1, error.stderr, "")
    numbers = [target_count(""), target_count("Chain Lightning"), radius()]
    try:
        return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired as hung:  # a walk that never stops fails too
        return subprocess.CompletedProcess(hung.cmd, 1, str(hung.stdout or "") + "\nTIMEOUT", "")


class Harness(unittest.TestCase):
    def test_the_jumps_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, (out.stdout + out.stderr)[-2000:])
        self.assertGreaterEqual(int(out.stdout.split("cases=")[1].split()[0]), 17, out.stdout)

    def test_a_planted_difference_is_caught(self):
        mutations = {
            "Chain Lightning's number read as jumps": ('rune == "Chain Lightning" ? targetCount - 1 : targetCount',
                                                      "targetCount"),
            "Lightning Blast jumps": ('rune == "Lightning Blast" || ', ""),
            "Arc Lightning jumps": ('rune == "Arc Lightning" || ', ""),
            "an enemy already hit is jumped to": ("(mayRehit ? again : -1)", "again"),
            "the re-hit flag is ignored": ("(mayRehit ? again : -1)", "-1"),
            "the bolt jumps to the enemy it is on": ("if (c.current)", "if (false)"),
            "not the nearest": ("best < 0 || c.distance < candidates[best].distance", "best < 0"),
            "one jump too many": ("while (out.size() < jumps)", "while (out.size() <= jumps)"),
            "measured from the first": ("on = around[std::size_t(next)];", "(void)around;"),
        }
        for label, mutation in mutations.items():
            with self.subTest(label):
                out = build_and_run(scratch_tree(mutation))
                self.assertNotEqual(out.returncode, 0, f"{label} survived:\n{out.stdout[-1500:]}")


class Sources(unittest.TestCase):
    def test_the_counts_are_the_d3_texts(self):
        texts = {r["rune_name"]: r["full_rune_text"] for r in read(D3 / "wizard_runes.csv") if r["skill_name"] == SKILL}
        skill = [r for r in read(D3 / "wizard_skills.csv") if r["skill_name"] == SKILL][0]
        self.assertIn("hitting up to {target_count} additional enemies", skill["full_tooltip_text"])
        self.assertIn("maximum number of enemies that can be electrocuted to {target_count}", texts["Chain Lightning"])
        self.assertIn("pierce through enemies", texts["Lightning Blast"])
        self.assertIn("Blast a cone of lightning", texts["Arc Lightning"])
        self.assertEqual((2.0, 10.0), (target_count(""), target_count("Chain Lightning")))

    def test_the_radius_is_the_power_files(self):
        row = radius_row()
        self.assertEqual("15", row["d3_value"])
        self.assertEqual("yards", row["unit"])
        self.assertIn("SF_2 'Target Search Radius' = 15", row["notes"])

    def test_every_electrocute_record_asks_for_chain_targets(self):
        shells = {int(m[1]): m[2] for m in re.finditer(r'\{(\d+), "Electrocute", "([^"]*)"', (MODULE / "src/combat/dc_spell_shells.h").read_text())}
        self.assertEqual({"", "Lightning Blast", "Chain Lightning", "Arc Lightning", "Surge of Power", "Forked Lightning"}, set(shells.values()))
        updates = sorted((MODULE / "data/sql/db-world/updates").glob("combat_0*.sql"))
        records = [p for p in updates if "INSERT INTO `spell_dbc`" in p.read_text(encoding="utf-8")][-1].read_text(encoding="utf-8")
        columns = re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", records)[1].replace("`", "").split(", ")
        for line in records.splitlines():
            spell = int(line[1:line.index(",")]) if line.startswith("(") and line[1:2].isdigit() else None
            if spell in shells:
                row = dict(zip(columns, next(csv.reader(io.StringIO(line[1:].rstrip(",;").rstrip(")")), quotechar="'", escapechar="\\"))))
                with self.subTest(spell=spell):
                    self.assertGreater(int(row["EffectChainTargets_1"]), 1)
                    self.assertEqual("6", row["ImplicitTargetA_1"])  # TARGET_UNIT_TARGET_ENEMY


def wiring_failures(combat, wizard):
    """What is wrong with the wiring ([] when it is right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("Chain is registered on Electrocute's aimed target",
         "Wizard::Chains(m_scriptSpellId) &&" in combat
         and "OnObjectAreaTargetSelect += SpellObjectAreaTargetSelectFn(dc_ability_targets::Chain, EFFECT_0,\n"
             "                                                                              TARGET_UNIT_TARGET_ENEMY);" in combat)
    chain = combat[combat.index("void Chain(std::list<WorldObject*>& targets)"):]
    chain = chain[:chain.index("\n            }\n")]
    need("Chain takes the walk", "Wizard::Jumps(player, GetSpellInfo()->Id, GetExplTargetUnit())" in chain)
    need("Chain keeps every jump in native", "native.push_back(unit->GetGUID());" in chain)
    need("Chain replaces the core's list", "targets.clear();" in chain and "targets.push_back(unit);" in chain)
    resolve = combat[combat.index("if (row.type == \"single_enemy\")"):]
    resolve = resolve[:resolve.index("return out;")]
    need("single_enemy hits the aimed enemy first", "std::vector<Unit*> out{explicitTarget};" in resolve)
    need("single_enemy adds the jumps", "for (ObjectGuid guid : native)" in resolve and "out.push_back(unit);" in resolve)
    need("Chains is Electrocute's", 'return row && std::string_view(row->skill) == "Electrocute";' in wizard)
    jumps = wizard[wizard.index("std::vector<Unit*> Jumps(Player* player, std::uint32_t spellId, Unit* first)"):]
    jumps = jumps[:jumps.index("\n    }\n")]
    need("Jumps is Electrocute's", 'std::string_view(row->skill) != "Electrocute"' in jumps)
    need("Jumps counts from the sheet", 'Chain::JumpCount(row->rune, Num(spellId, "target_count"))' in jumps)
    need("Jumps reads the radius tunable", 'DC::Tunables::Get("wizard", "electrocute_jump_radius_yards")' in jumps
         and 'DC::Tunables::Has("wizard", "electrocute_jump_radius_yards")' in jumps)
    need("a re-hit only through Myken's Ball of Hate (diablocraft-3j0cg)", 'bool const mayRehit = ItemPowers::SkillSetTo(player, "Electrocute", "jump_rehit", 0) > 0;' in jumps)
    need("Jumps walks the header's rule over the enemies around", "Chain::Walk(" in jumps
         and "Combat::Enemies(player, spellId, on->GetPosition(), radius)" in jumps)
    return wrong


class Wiring(unittest.TestCase):
    def test_the_wiring(self):
        self.assertEqual([], wiring_failures(COMBAT.read_text(encoding="utf-8"), WIZARD.read_text(encoding="utf-8")))

    def test_the_guards_fail_their_mutants(self):
        combat = COMBAT.read_text(encoding="utf-8")
        wizard = WIZARD.read_text(encoding="utf-8")
        mutants = {
            "not registered": (COMBAT, "dc_ability_targets::Chain, EFFECT_0,", "dc_ability_targets::Collect, EFFECT_0,"),
            "native not kept": (COMBAT, "                    native.push_back(unit->GetGUID());\n                    if (std::find(targets.begin()",
                                "                    if (std::find(targets.begin()"),
            "the core's list kept": (COMBAT, "                native.clear();\n                targets.clear();\n                Player* player = GetCaster()->ToPlayer();\n                for (Unit* unit : Wizard::Jumps",
                                     "                native.clear();\n                Player* player = GetCaster()->ToPlayer();\n                for (Unit* unit : Wizard::Jumps"),
            "jumps not hit": (COMBAT, "                for (ObjectGuid guid : native)\n                    if (Unit* unit = ObjectAccessor::GetUnit(*player, guid); unit && ValidTarget(player, unit, info, false))\n                        out.push_back(unit);\n",
                              ""),
            "every skill chains": (WIZARD, 'return row && std::string_view(row->skill) == "Electrocute";', "return row != nullptr;"),
            "every skill jumps": (WIZARD, 'std::string_view(row->skill) != "Electrocute" ||', "false ||"),
            "a fixed count": (WIZARD, 'Chain::JumpCount(row->rune, Num(spellId, "target_count"))', "2u"),
            "re-hits": (WIZARD, 'bool const mayRehit = ItemPowers::SkillSetTo(player, "Electrocute", "jump_rehit", 0) > 0;', "bool const mayRehit = true;"),
            "no jump radius": (WIZARD, "Combat::Enemies(player, spellId, on->GetPosition(), radius)",
                               "Combat::Enemies(player, spellId, on->GetPosition(), 100.0)"),
        }
        for name, (where, old, new) in mutants.items():
            with self.subTest(mutant=name):
                text = combat if where == COMBAT else wizard
                self.assertEqual(1, text.count(old), name + " does not apply once")
                mutated = text.replace(old, new)
                self.assertTrue(wiring_failures(mutated if where == COMBAT else combat, mutated if where == WIZARD else wizard),
                                name + " survived")


if __name__ == "__main__":
    unittest.main()
