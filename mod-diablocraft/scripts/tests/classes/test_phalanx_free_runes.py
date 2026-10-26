"""Phalanx's three free runes cost nothing (diablocraft-a569c): the spell records of Bowmen, Shield Bearers and Bodyguard carry no Wrath cost,
as the power file says (Power/x1_Crusader_Phalanx3.pow SF_5: Rune_E ? 0 : Rune_D ? 0 : Rune_A ? 0 : the cost); they run on an internal
cooldown instead.

What this proves, and how:

  * **The sheet.** data/d3/crusader_runes.csv states "Wrath cost removed" for those three runes' modified_cost_cooldown_damage cell and for no other
    Phalanx rune (Bowmen keeps its 185% weapon damage clause beside it); the values sheet states no cost for any rune of the skill, so the three
    inherit none (the generator refuses a removed cost that still has a value).
  * **The records.** data/generated/spell_shells.sql: Phalanx 85416, Shield Charge 85505 and Stampede 85506 keep ManaCost 30 and the Wrath power
    type; Bowmen 85504, Shield Bearers 85507 and Bodyguard 85508 have ManaCost 0 and no power type; the generated value map has no cost row for
    the three and keeps the inherited one for the others.
  * **The render.** The migration combat_0093 differs from the newest render before it, combat_0092,
    in exactly those three records' ManaCost and PowerType.
  * **The code.** The cast no longer gives the cost back (the records no longer take it): no GainWrath in Phalanx's cast, no CostGivenBack.

What it does not prove: the cost in game (the client Spell.dbc is test_spell_records.py's), and the committed patch.

    python mod-diablocraft/scripts/tests/classes/test_phalanx_free_runes.py
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
GENERATED = MODULE / "data/generated"
UPDATES = MODULE / "data/sql/db-world/updates"
SKILL = "Phalanx"
FREE = {"Bowmen": 85504, "Shield Bearers": 85507, "Bodyguard": 85508}
PAYING = {"": 85416, "Shield Charge": 85505, "Stampede": 85506}
CLAUSE = "Wrath cost removed"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def clauses():
    return {r["rune_name"]: r["modified_cost_cooldown_damage"] for r in read(MODULE / "data/d3/crusader_runes.csv") if r["skill_name"] == SKILL}


def sheet_problems(cells):
    """What is off in the Phalanx rune cells (rune -> modified_cost_cooldown_damage); empty when the three are free and the two pay."""
    problems = []
    for rune in FREE:
        if CLAUSE not in [c.strip() for c in cells[rune].split("|")]:
            problems.append(rune + " is not free")
    for rune in ("Shield Charge", "Stampede"):
        if "cost" in cells[rune]:
            problems.append(rune + " is free")
    return problems


def records(sql):
    """{spell id: {column: value}} of the Phalanx spell_dbc records of a render."""
    columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql, re.S)[1].split(",")]
    found = {}
    for spell_id in list(FREE.values()) + list(PAYING.values()):
        values = re.search(r"\n\(%d,([^)]*)\)" % spell_id, sql)[1].split(",")
        found[spell_id] = dict(zip(columns, [str(spell_id)] + values))
    return found


class Sheet(unittest.TestCase):
    def test_the_three_runes_are_free_and_the_other_two_pay(self):
        cells = clauses()
        self.assertEqual([], sheet_problems(cells))
        self.assertEqual("185% weapon damage | " + CLAUSE, cells["Bowmen"])

    def test_the_problems_are_caught(self):
        cells = clauses()
        for rune in FREE:
            self.assertNotEqual([], sheet_problems({**cells, rune: cells[rune].replace(CLAUSE, "").strip(" |")}), rune)
        self.assertNotEqual([], sheet_problems({**cells, "Stampede": CLAUSE.replace("Wrath", "Wrath") + " | cost"}))

    def test_no_rune_of_the_skill_states_a_cost_and_the_skill_states_thirty(self):
        costs = [(r["rune"], float(r["value"])) for r in read(MODULE / "data/d3/crusader_skill_values.csv")
                 if r["skill"] == SKILL and r["token"] == "cost_resource"]
        self.assertEqual([("", 30.0)], costs)


class Records(unittest.TestCase):
    def test_the_free_runes_cost_nothing_and_the_others_keep_thirty(self):
        found = records((GENERATED / "spell_shells.sql").read_text(encoding="utf-8"))
        for rune, spell_id in FREE.items():
            self.assertEqual(("0", "0"), (found[spell_id]["ManaCost"], found[spell_id]["PowerType"]), rune)
        for rune, spell_id in PAYING.items():
            self.assertEqual(("30", found[PAYING[""]]["PowerType"]), (found[spell_id]["ManaCost"], found[spell_id]["PowerType"]), rune)
        self.assertNotEqual("0", found[PAYING[""]]["PowerType"])

    def test_the_value_map_has_no_cost_row_for_the_free_runes(self):
        rows = [(int(r["spell_id"]), r["token"]) for r in read(GENERATED / "spell_value_map.csv")]
        for spell_id in FREE.values():
            self.assertNotIn((spell_id, "cost_resource"), rows)
        for spell_id in (85505, 85506):
            self.assertIn((spell_id, "cost_resource"), rows)

    def test_the_render_differs_from_the_one_before_by_three_records_and_the_generated_file_is_the_newest(self):
        new = (UPDATES / "combat_0093_phalanx_free_runes.sql").read_bytes()
        newest = max(UPDATES.glob("combat_*.sql"))   # the generated file is the newest render, which a later bead moves on
        self.assertEqual((GENERATED / "spell_shells.sql").read_bytes(), newest.read_bytes())
        old = (UPDATES / "combat_0092_stupefy_charm_mechanic.sql").read_text(encoding="utf-8").splitlines()
        now = new.decode("utf-8").splitlines()
        self.assertEqual(len(old), len(now))
        moved = [(a.split(","), b.split(",")) for a, b in zip(old, now) if a != b]
        self.assertEqual(sorted(FREE.values()), sorted(int(before[0].lstrip("(")) for before, _ in moved))
        for before, after in moved:
            self.assertEqual(len(before), len(after))
            self.assertEqual(2, len([1 for a, b in zip(before, after) if a != b]), "only ManaCost and PowerType moved")
            self.assertEqual(["0"], sorted({after[i] for i, (a, b) in enumerate(zip(before, after)) if a != b}))


class Code(unittest.TestCase):
    def test_the_cast_no_longer_gives_the_cost_back(self):
        text = (MODULE / "src/classes/crusader/dc_crusader_phalanx.cpp").read_text(encoding="utf-8")
        cast = text[text.index("void Cast("):text.index("void Ground(")]
        self.assertNotIn("GainWrath", cast)
        self.assertNotIn("CostGivenBack", text)
        self.assertNotIn("CostGivenBack", (MODULE / "src/classes/crusader/dc_crusader_phalanx.h").read_text(encoding="utf-8"))
        self.assertIn("SendSkillCooldown(player, spellId, std::uint32_t(Millis(cooldown)));", cast)


if __name__ == "__main__":
    unittest.main()
