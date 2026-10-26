"""Stupefy on the shared charm (diablocraft-0hl62): the Barbarian's Weapon Throw rune charms through CharmEffect::Apply, its record carries the
charm mechanic, and the Juggernaut refuses that mechanic.

What this proves, and how:

  * **The caller.** The text of dc_barbarian_primaries.cpp: the Stupefy proc (the row's 15% roll, unchanged) calls
    CharmEffect::Apply(player, target, row->id, row->duration / 1000.0), the row's 3 seconds read from primary_effects.csv; it does so only when
    another enemy is in sight, as the aura script it replaces refused a monster alone; the old direct cast of record 81192 and the dc_stupefy aura
    script and its registration are gone. Each rule is mutated in a copy of the text and the guard must fail.
  * **The record.** data/generated/spell_shells.sql carries 81192 with Mechanic 1 (the core's MECHANIC_CHARM, read from the core's SharedDefines.h;
    30 is Sapped) and still the AOE_CHARM effect; the render combat_0092 differs from the one before it, combat_0091, in that one record and the removed dc_stupefy script row; the generator sets it from primary_spells.py.
  * **The Juggernaut.** dc_affix_juggernaut.cpp's immunity list names the core's MECHANIC_CHARM constant (no literal), and the rifts' contract
    says 1, not 30.

What it does not prove: a charm on a running server, and that the Juggernaut refuses the aura in game (the compile and the donor 26740's
mechanic are test_charm_effect.py's).

    python mod-diablocraft/scripts/tests/classes/test_stupefy_shared_charm.py
"""

import csv
import re
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
UPDATES = MODULE / "data/sql/db-world/updates"
PRIMARIES = MODULE / "src/classes/barbarian/dc_barbarian_primaries.cpp"
JUGGERNAUT = MODULE / "src/monsters/affixes/dc_affix_juggernaut.cpp"
CORE_DEFINES = REPO / "azerothcore-wotlk/src/server/shared/SharedDefines.h"
STUPEFY = 81192
WEAPON_THROW_STUPEFY = 81032


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def row_seconds():
    with (MODULE / "data/d3/primary_effects.csv").open(encoding="utf-8-sig", newline="") as stream:
        row = next(r for r in csv.DictReader(stream) if r["spell_id"] == str(WEAPON_THROW_STUPEFY))
    assert row["behavior"] == "stupefy"
    return float(row["duration_ms"]) / 1000


def record(sql, spell_id):
    """{column: value} of one spell_dbc record of a render."""
    columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql, re.S)[1].split(",")]
    values = re.search(r"\n\(%d,([^)]*)\)" % spell_id, sql)[1].split(",")
    return dict(zip(columns, [str(spell_id)] + values))


def caller_problems(text):
    """Every way the Barbarian's Stupefy proc can be off the shared charm; empty when it is on it."""
    flat = squeeze(text)
    problems = []
    if '#include "../../combat/dc_charm_effect.h"' not in flat:
        problems.append("does not include the shared charm")
    body = flat[flat.find("if (row->behavior == B::stupefy)"):][:900]
    if "CharmEffect::Apply(player, target, row->id, row->duration / 1000.0);" not in body:
        problems.append("does not call Apply with the row's id and seconds")
    if "others.remove(target); if (!others.empty()) CharmEffect::Apply(" not in body:
        problems.append("charms with no other enemy in sight")
    if "Enemies(player, target, target->GetVisibilityRange())" not in body:
        problems.append("looks for the other enemy somewhere else than the core's visibility range")
    if "D::STUPEFY" in flat:
        problems.append("still casts record 81192 itself")
    if "dc_stupefy" in flat:
        problems.append("still holds the dc_stupefy aura script")
    return problems


class Caller(unittest.TestCase):
    def setUp(self):
        self.text = PRIMARIES.read_text(encoding="utf-8")

    def test_the_proc_charms_through_the_shared_charm(self):
        self.assertEqual([], caller_problems(self.text))
        self.assertEqual(3.0, row_seconds())

    def test_the_roll_is_still_the_rows_chance_and_a_live_target(self):
        flat = squeeze(self.text)
        self.assertIn("if (roll_chance_f(float(row->chance))) { if (row->behavior == B::hammer)", flat)
        self.assertLess(flat.index("if (target->IsAlive())"), flat.index("if (row->behavior == B::stupefy)"))

    def test_the_rules_are_each_guarded(self):
        mutants = {
            "no include": ('#include "../../combat/dc_charm_effect.h"\n', ""),
            "the seconds are not the row's": ("row->duration / 1000.0", "3.0"),
            "the row's id is not passed": ("CharmEffect::Apply(player, target, row->id,", "CharmEffect::Apply(player, target, 0,"),
            "no other enemy needed": ("if (!others.empty())", "if (true)"),
            "the old cast is back": ("CharmEffect::Apply(player, target, row->id, row->duration / 1000.0);",
                                     "player->CastSpell(target, D::STUPEFY, true);"),
            "the old script is back": ("RegisterSpellScript(dc_primary_spell);", "RegisterSpellScript(dc_primary_spell); RegisterSpellScript(dc_stupefy);"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, self.text.count(old), name + " does not apply")
                self.assertNotEqual([], caller_problems(self.text.replace(old, new, 1)), name + " survived")


class Record(unittest.TestCase):
    def test_the_core_names_the_charm_mechanic_one(self):
        if not CORE_DEFINES.is_file():
            self.skipTest("no core source")
        text = CORE_DEFINES.read_text(encoding="utf-8", errors="replace")
        self.assertRegex(text, r"MECHANIC_CHARM\s*=\s*1,")
        self.assertRegex(text, r"MECHANIC_SAPPED\s*=\s*30,")

    def test_stupefys_record_carries_it_and_still_charms(self):
        stupefy = record((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), STUPEFY)
        self.assertEqual(("1", "177"), (stupefy["Mechanic"], stupefy["EffectAura_1"]))

    def test_the_new_render_is_the_generated_file_and_differs_from_the_applied_one_by_the_record_and_the_script_row(self):
        new = (UPDATES / "combat_0092_stupefy_charm_mechanic.sql").read_bytes()
        newest = max(UPDATES.glob("combat_*.sql"))   # the generated file is the newest render, which a later bead moves on
        self.assertEqual((MODULE / "data/generated/spell_shells.sql").read_bytes(), newest.read_bytes())
        old = (UPDATES / "combat_0091_falling_sword_leap.sql").read_text(encoding="utf-8").splitlines()
        now = new.decode("utf-8").splitlines()
        self.assertEqual(len(old) - 1, len(now))
        gone = [line for line in old if line not in now]
        added = [line for line in now if line not in old]
        self.assertEqual(2, len(gone), gone)
        self.assertEqual(1, len(added), added)
        self.assertIn("(%d,'dc_stupefy')" % STUPEFY, "".join(gone))
        before = [line for line in gone if line.startswith("(%d," % STUPEFY)][0].split(",")
        after = added[0].split(",")
        self.assertEqual(len(before), len(after))
        self.assertEqual([i for i, (a, b) in enumerate(zip(before, after)) if a != b], [3], "only the Mechanic column moved")
        self.assertEqual(("0", "1"), (before[3], after[3]))
        self.assertNotIn("dc_stupefy", "".join(line for line in now if line.startswith("INSERT INTO spell_script_names")))
        self.assertIn("'dc_stupefy'", "".join(now), "the delete of the old script row stays")

    def test_the_generator_sets_the_mechanic_from_the_one_place(self):
        text = (MODULE / "scripts/primary_spells.py").read_text(encoding="utf-8")
        self.assertRegex(squeeze(text), r"elif key == 'Stupefy': put\('EffectAura_1',177\).*? put\('Mechanic',1\)")
        generator = (MODULE / "scripts/generate/classes/generate_spells.py").read_text(encoding="utf-8")
        self.assertNotIn("{primary_spells.STUPEFY},'dc_stupefy'", generator)
        self.assertIn("'dc_stupefy'", generator)  # the DELETE that clears the old row


class Juggernaut(unittest.TestCase):
    def test_the_immunity_list_names_the_cores_charm_mechanic(self):
        text = JUGGERNAUT.read_text(encoding="utf-8")
        loop = squeeze(text[text.index("for (uint32 mechanic : {"):text.index("elite->ApplySpellImmune(0, IMMUNITY_MECHANIC")])
        self.assertIn("{MECHANIC_CHARM,", loop)
        self.assertNotRegex(loop, r"\b30\b")
        # the list is the one SetJuggernautImmunities puts on or takes off (the Shaman's Purge takes it off)
        self.assertIn("elite->ApplySpellImmune(0, IMMUNITY_MECHANIC, mechanic, on);", squeeze(text))
        self.assertIn("SetJuggernautImmunities(elite, true);", squeeze(text))

    def test_the_contract_names_one_not_thirty(self):
        text = (REPO / "docs/contracts/legendary-world-pieces.md").read_text(encoding="utf-8")
        self.assertIn("`MECHANIC_CHARM` (1)", text)
        self.assertNotIn("MECHANIC_CHARM` (30)", text)


if __name__ == "__main__":
    unittest.main()
