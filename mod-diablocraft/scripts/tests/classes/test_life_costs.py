"""A skill's or rune's Life cost reaches the module as an exact health_cost_pct value, and the record charges nothing itself.
Since diablocraft-u59aj no record carries POWER_HEALTH or ManaCostPct: the core would charge that from base health on top of
the skill code's own SpendLife (D3's percent of max Life, never below 1), so a cast cost both.

What this proves, and how:

  * **The rule.** life_cost_pct() with made-up rows: a skill's health_cost_pct is its cost; a rune takes its skill's
    cost unless its modifier cell says "Health cost N%" (that number), "Health cost removed" (none) or "Health cost
    doubled" (twice the skill's); doubling a cost the skill does not have, and a "Cost: N% Health" label that
    disagrees with the sheet, are refused. rune_modifiers() reads the three Life forms and "Cooldown changed to N
    seconds".
  * **The shipped render.** For every Necromancer skill and rune, the cost this test works out from the sheets on its
    own (necromancer_skills.csv health_cost_pct, the runes' modifier cells) is the one the generated dc_spell_values row
    carries; a record with no Life cost carries none; no record anywhere has PowerType POWER_HEALTH or a ManaCostPct.
  * **Charged once.** For each of the Life-cost casts the skill code charges (Blood Rush and Metabolism, Possession, Oblation, Blood
    Lance, Final Embrace, Dead Storm, Thy Flesh Sustained): the record takes nothing from the core (no cost of any kind beside
    it), its skill file calls SpendLife once through the tunable that names the cost, and that tunable's D3 value is the
    sheet's percent. So a cast costs exactly SpendLife's amount. Simulacrum has the same record shape and no skill code yet;
    its skill bead's SpendLife will charge the token.

What it does not prove: what SpendLife takes in game (max Life, never below 1), or anything else in game.

    python mod-diablocraft/scripts/tests/classes/test_life_costs.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
GENERATED = MODULE / "data" / "generated"
sys.path.insert(0, str(MODULE / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells as gs  # noqa: E402
from test_class_records import split_values  # noqa: E402

POWER_HEALTH = -2


def read(name):
    with (D3 / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def skill(name="Blood Rush", pct="5", text="Cost: 5% Health | Shed your mortal flesh"):
    return {"skill_name": name, "health_cost_pct": pct, "full_tooltip_text": text}


def rune(cell, text="A rune.", name="Blood Rush", rune_name="Some Rune"):
    return {"skill_name": name, "rune_name": rune_name, "modified_cost_cooldown_damage": cell, "full_rune_text": text}


def expected_costs():
    """{(skill, rune): percent} from the sheets, worked out here without the generator."""
    skills = {row["skill_name"]: row for row in read("necromancer_skills.csv")}
    out = {}
    for name, row in skills.items():
        if row["health_cost_pct"]:
            out[(name, "")] = float(row["health_cost_pct"])
    for row in read("necromancer_runes.csv"):
        base = float(skills[row["skill_name"]]["health_cost_pct"] or 0)
        cell = row["modified_cost_cooldown_damage"]
        own = re.search(r"Health cost ([0-9.]+)%", cell)
        if "Health cost removed" in cell:
            continue
        cost = base * 2 if "Health cost doubled" in cell else float(own[1]) if own else base
        if cost:
            out[(row["skill_name"], row["rune_name"])] = cost
    return out


class Rule(unittest.TestCase):
    def test_skill_cost(self):
        self.assertEqual(gs.life_cost_pct(skill()), 5)
        self.assertIsNone(gs.life_cost_pct(skill(pct="", text="Bone Spear")))

    def test_rune_inherits(self):
        self.assertEqual(gs.life_cost_pct(skill(), rune("")), 5)

    def test_rune_sets_removes_doubles(self):
        self.assertEqual(gs.life_cost_pct(skill(pct="", text="x"), rune("650% weapon damage | Health cost 10%")), 10)
        self.assertIsNone(gs.life_cost_pct(skill(), rune("Health cost removed")))
        self.assertEqual(gs.life_cost_pct(skill(), rune("Health cost doubled")), 10)

    def test_doubling_nothing_refused(self):
        with self.assertRaises(SystemExit):
            gs.life_cost_pct(skill(pct="", text="x"), rune("Health cost doubled"))

    def test_label_disagreeing_refused(self):
        with self.assertRaises(SystemExit):
            gs.life_cost_pct(skill(pct="6"))
        with self.assertRaises(SystemExit):
            gs.life_cost_pct(skill(pct="", text="x"), rune("", text="Cost: 20% health | Raise a storm"))

    def test_modifier_forms(self):
        self.assertEqual(gs.rune_modifiers("Health cost 2%"), {"health_cost": 2.0})
        self.assertEqual(gs.rune_modifiers("Health cost removed"), {"no_health_cost": 0.0})
        self.assertEqual(gs.rune_modifiers("Health cost doubled"), {"health_cost_doubled": 0.0})
        self.assertEqual(gs.rune_modifiers("Cooldown changed to 45 seconds"), {"cooldown": 45.0})


class ShippedRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sql = (GENERATED / "spell_shells.sql").read_text(encoding="utf-8")
        columns = re.search(r"INSERT INTO `spell_dbc` \(([^)]*)\)", sql)[1].replace("`", "").split(", ")
        index = {name: columns.index(name) for name in ("ID", "PowerType", "ManaCost", "ManaCostPct")}
        cls.records = {}
        for line in sql.splitlines():
            if line.startswith("(") and line.rstrip(",;").endswith(")"):
                values = split_values(line.rstrip(",;")[1:-1])
                if len(values) == len(columns):
                    cls.records[int(values[index["ID"]])] = {k: int(values[i]) for k, i in index.items()}
        cls.exact = {int(i): float(v) for i, v in re.findall(r"\((\d+),'health_cost_pct','',([0-9.]+)\)", sql)}
        with (GENERATED / "spell_shells.csv").open(encoding="utf-8", newline="") as stream:
            first, last = gs.CLASS_BLOCKS["necromancer"].records
            cls.ids = {}
            for row in csv.DictReader(stream):
                identifier = int(row["spell_id"])
                if first <= identifier <= last and row["kind"] in ("active", "rune"):
                    name, _, rune_name = row["name"].partition(" - ")
                    cls.ids[(name, rune_name)] = identifier

    def test_there_are_costs_to_check(self):
        self.assertGreaterEqual(len(expected_costs()), 20)
        self.assertEqual(len(self.ids), 21 + 105)

    def test_every_record_carries_the_sheet_cost(self):
        expected = expected_costs()
        for key, identifier in self.ids.items():
            record = self.records[identifier]
            with self.subTest(record=key):
                self.assertEqual(self.exact.get(identifier), expected.get(key))
                self.assertNotEqual(record["PowerType"], POWER_HEALTH)
                self.assertEqual(record["ManaCostPct"], 0)

    def test_no_record_charges_life_itself(self):
        self.assertEqual([i for i, r in self.records.items() if r["PowerType"] == POWER_HEALTH or r["ManaCostPct"]], [])

    def test_a_life_only_cast_costs_exactly_spendlifes_amount(self):
        expected = expected_costs()
        source = MODULE / "src" / "classes" / "necromancer"
        casts = [("Blood Rush", "", "dc_necromancer_blood_rush.cpp", "blood_rush_life_cost_pct"),
                 ("Blood Rush", "Metabolism", "dc_necromancer_blood_rush.cpp", "metabolism_life_cost_pct"),
                 ("Bone Spirit", "Possession", "dc_necromancer_bone_spirit.cpp", "possession_life_cost_pct"),
                 ("Revive", "Oblation", "dc_necromancer_revive.cpp", "revive_oblation_life_cost_pct"),
                 ("Corpse Lance", "Blood Lance", "dc_necromancer_corpse_lance.cpp", "blood_lance_life_cost_pct"),
                 ("Corpse Explosion", "Final Embrace", "dc_necromancer_corpse_explosion.cpp", "final_embrace_life_cost_pct"),
                 ("Army of the Dead", "Dead Storm", "dc_necromancer_army_of_the_dead.cpp", "dead_storm_life_cost_pct"),
                 ("Bone Armor", "Thy Flesh Sustained", "dc_necromancer_bone_armor.cpp", "thy_flesh_sustained_life_cost_pct")]
        with (MODULE / "data/tunables/necromancer.csv").open(encoding="utf-8", newline="") as stream:
            tunables = {r["name"]: r for r in csv.DictReader(stream)}
        for skill_name, rune_name, file, tunable in casts:
            with self.subTest(cast=(skill_name, rune_name)):
                record = self.records[self.ids[(skill_name, rune_name)]]
                # The record takes nothing from the core: no resource cost and no percent of base health.
                self.assertEqual((record["PowerType"] != POWER_HEALTH, record["ManaCost"], record["ManaCostPct"]), (True, 0, 0))
                text = (source / file).read_text(encoding="utf-8")
                self.assertEqual(1, len(re.findall(r"SpendLife\(", text)))   # the skill file charges the Life once
                self.assertIn('Tune("%s")' % tunable, text)                    # at the tunable that names the cost
                self.assertEqual(float(tunables[tunable]["d3_value"]), expected[(skill_name, rune_name)])   # which is D3's percent


if __name__ == "__main__":
    unittest.main()
