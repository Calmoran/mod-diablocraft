"""The rest of the proc coefficients (diablocraft-il3bf, after iqsk8): the Crusader's and the Necromancer's sheets state each attack's
coefficient, a pet's blows roll the coefficient of the pet's own melee attack, and the effects the bead named are read against their power
files.

What this proves, and how:

  * **The sheets.** Each Crusader and Necromancer skill whose power file states a ProcCoefficient has a row per rune: the file's expression
    evaluated for the rune, and (where the client data is installed) the expression is the file's own. A skill whose coefficients are all 0
    or whose hit comes from a power that states none has no row. The newest render carries every row.
  * **Pets.** A pet's blow rolls the coefficient of its own melee attack (a combat tunable per creature entry, from the power file), not
    its owner's skill's. The minions piece wraps each swing and each aura pulse in a PetBlow; the item powers and the gems read
    Combat::ProcCoefficient and no longer read the sheet directly.
  * **The named effects.** Wrathful (Wrath spent), Indestructible (a kill), Draw Life (regeneration), Grisly Tribute (Life on Hit, which the
    module restores whole once per cast), Elemental Arrow's Nether Tentacles and Bolas' Bitter Pill (numbers of the rune's own power) are not
    scaled by the landing attack's coefficient in the power files, so they are not scaled here.

What it does not prove: anything on a running server.

    python mod-diablocraft/scripts/tests/combat/test_pet_proc_coefficients.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
SRC = MODULE / "src"
CLASS_ROWS = {
    "crusader": {"Punish", "Slash", "Smite", "Justice", "Shield Bash", "Sweep Attack", "Blessed Shield", "Fist of the Heavens",
                 "Shield Glare", "Steed Charge", "Falling Sword", "Bombardment"},
    "necromancer": {"Bone Spikes", "Siphon Blood", "Bone Spear", "Corpse Lance", "Death Nova", "Land of the Dead", "Blood Rush",
                    "Simulacrum"},
}
# the skills of each class whose hit has no ProcCoefficient in its power file (or all 0): no row, so no chance and no scaled effect
STATES_NONE = {
    "crusader": {"Blessed Hammer", "Iron Skin", "Consecration", "Judgment", "Provoke", "Phalanx", "Laws of Valor", "Laws of Justice",
                 "Laws of Hope", "Heaven's Fury", "Condemn", "Akarat's Champion"},
    "necromancer": {"Grim Scythe", "Skeletal Mage", "Corpse Explosion", "Devour", "Revive", "Command Skeletons", "Command Golem",
                    "Army of the Dead", "Decrepify", "Leech", "Frailty", "Bone Armor", "Bone Spirit"},
}
# creature entry -> (the pet, the power file of its melee attack, the coefficient the file states)
PETS = {
    900150: ("Skeletal Mage", "P6_Necro_SkeletonMage_Fire_Projectile", 1.0),
    900151: ("Skeletal Warrior", "P6_Necro_Skeletal_Warrior_Melee", 1.0),
    900152: ("Flesh Golem", "P6_Necro_Golem_Melee", 1.0),
    900153: ("Revived Minion", "P6_Necro_Revive_Melee", 1.0),
    # the Witch Doctor's pets: entries of 2c (w/diablocraft-vxrcu.7), which merges separately
    900170: ("Zombie Dog", "Witchdoctor_ZombieDog_Melee", 1.0),
    900171: ("Gargantuan", "Witchdoctor_Gargantuan_Cleave", 0.0),
    900172: ("Fetish", "Witchdoctor_FetishArmy_Melee", 1.0),
    900173: ("Fetish Sycophant", "Witchdoctor_FetishSycophants_Melee", 1.0),
}


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def squeeze(text):
    return re.sub(r"\s+", " ", text)


def rows_of(cls):
    return [r for r in read(D3 / f"{cls}_skill_values.csv") if r["token"] == "proc_coefficient"]


def evaluate(expression, letter):
    text = expression.strip()
    if not text.startswith("("):
        text = "(" + text + ")"
    text = re.sub(r"Rune_([A-E])", lambda m: "1" if letter == m.group(1) else "0", text)
    for _ in range(12):
        reduced = re.sub(r"\((\d)\s*\?\s*([\d.]+)\s*:\s*([\d.]+)\)", lambda m: m.group(2) if m.group(1) == "1" else m.group(3), text)
        if reduced == text:
            break
        text = reduced
    return float(text.strip("() "))


class Sheets(unittest.TestCase):
    def test_a_row_per_rune_for_each_skill_that_states_a_coefficient(self):
        for cls, skills in CLASS_ROWS.items():
            with self.subTest(cls):
                rows = rows_of(cls)
                self.assertEqual({r["skill"] for r in rows}, skills)
                names = {r["skill_name"] for r in read(D3 / f"{cls}_skills.csv")}
                self.assertEqual(names - skills, STATES_NONE[cls])
                runes = {}
                for r in read(D3 / f"{cls}_runes.csv"):
                    runes.setdefault(r["skill_name"], []).append(r["rune_name"])
                for skill in skills:
                    self.assertEqual({r["rune"] for r in rows if r["skill"] == skill}, {""} | set(runes[skill]), skill)

    def test_each_row_is_its_power_files_expression_for_the_rune(self):
        for cls in CLASS_ROWS:
            letters = {(r["skill_name"], r["rune_name"]): r["rune_slot"] for r in read(D3 / f"{cls}_runes.csv")}
            for row in rows_of(cls):
                with self.subTest(cls=cls, skill=row["skill"], rune=row["rune"]):
                    found = re.search(r"Power/(\w+)\.pow \(ProcCoefficient = '([^']*)'; decode_pow\.py power (\w+)\)", row["source"])
                    self.assertIsNotNone(found, row["source"])
                    self.assertEqual(found.group(1), found.group(3))
                    letter = letters[(row["skill"], row["rune"])] if row["rune"] else ""
                    self.assertAlmostEqual(float(row["value"]), evaluate(found.group(2), letter), places=9)

    def test_the_expressions_are_the_client_datas_own(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the client data is not installed")
        for cls in CLASS_ROWS:
            seen = set()
            for row in rows_of(cls):
                found = re.search(r"Power/(\w+)\.pow \(ProcCoefficient = '([^']*)'", row["source"])
                if found.group(1) in seen:
                    continue
                seen.add(found.group(1))
                power = decode_pow.parse_power(decode_pow.extract(f"Power/{found.group(1)}.pow"))
                tag = power["tags"][decode_pow.TAG_PROC_COEFFICIENT]
                self.assertEqual(("%g" % tag) if isinstance(tag, float) else str(tag), found.group(2), found.group(1))
            self.assertEqual(len(seen), len(CLASS_ROWS[cls]))

    def test_the_known_numbers(self):
        def value(cls, skill, rune):
            rows = [r for r in rows_of(cls) if (r["skill"], r["rune"]) == (skill, rune)]
            self.assertEqual(len(rows), 1, (skill, rune))
            return float(rows[0]["value"])

        self.assertEqual(value("crusader", "Slash", ""), 0.8)
        self.assertEqual(value("crusader", "Shield Bash", ""), 1.0)
        self.assertEqual(value("crusader", "Blessed Shield", ""), 1.0)
        self.assertEqual(value("crusader", "Shield Glare", ""), 0.1667)
        self.assertEqual(value("necromancer", "Bone Spear", ""), 0.5)
        self.assertEqual(value("necromancer", "Siphon Blood", ""), 0.333)
        self.assertEqual(value("necromancer", "Corpse Lance", ""), 0.5)

    def test_the_engine_can_read_each_row_and_the_newest_render_carries_them(self):
        mapped = {(r["skill"], r["rune"]) for r in read(MODULE / "data/generated/spell_value_map.csv") if r["token"] == "proc_coefficient"}
        for cls in CLASS_ROWS:
            for row in rows_of(cls):
                self.assertIn((row["skill"], row["rune"]), mapped)
        sql = (MODULE / "data/sql/db-world/updates/combat_0121_crusader_necromancer_proc_coefficients.sql").read_text(encoding="utf-8")
        generated = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        self.assertEqual(sql.count("'proc_coefficient'"), generated.count("'proc_coefficient'"))
        self.assertGreater(sql.count("'proc_coefficient'"), 220)


class Pets(unittest.TestCase):
    def test_a_row_per_pet_with_the_power_files_number_and_none_of_alexs(self):
        rows = {r["name"]: r for r in read(MODULE / "data/tunables/combat.csv") if r["name"].startswith("pet_proc_coefficient_")}
        self.assertEqual(set(rows), {f"pet_proc_coefficient_{entry}" for entry in PETS})
        for entry, (pet, power, number) in PETS.items():
            row = rows[f"pet_proc_coefficient_{entry}"]
            with self.subTest(pet):
                self.assertEqual((row["d3_value"], row["value"]), ("%g" % number, ""))
                self.assertIn(f"Power/{power}.pow", row["notes"])
                self.assertNotIn("PLACEHOLDER", row["notes"])

    def test_the_numbers_are_the_client_datas_own(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the client data is not installed")
        for entry, (pet, power, number) in PETS.items():
            tag = decode_pow.parse_power(decode_pow.extract(f"Power/{power}.pow"))["tags"][decode_pow.TAG_PROC_COEFFICIENT]
            self.assertEqual(float(tag), number, pet)

    def test_the_necromancers_entries_are_its_summons(self):
        entries = {int(r["entry"]): r["summon"] for r in read(D3 / "necromancer_summons.csv")}
        for entry, (pet, _, _) in PETS.items():
            if entry < 900160:
                self.assertEqual(entries[entry], pet)

    def test_a_pet_with_no_attack_power_that_states_one_has_no_row(self):
        # the Demon Hunter's Companion (DH_Companion_MeleeAttack, DH_Companion_ChargeAttack) and the Simulacrum's weapon attack state none
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the client data is not installed")
        for power in ("DH_Companion_MeleeAttack", "DH_Companion_ChargeAttack", "P6_Necro_Simulacrum_Weapon_Melee_Instant"):
            self.assertNotIn(decode_pow.TAG_PROC_COEFFICIENT, decode_pow.parse_power(decode_pow.extract(f"Power/{power}.pow"))["tags"], power)
        for entry in (900154, 900160, 900161, 900162, 900163, 900164, 900165):
            self.assertNotIn(entry, PETS)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.minions = squeeze((SRC / "combat/dc_minions.cpp").read_text(encoding="utf-8"))
        self.resolve = squeeze((SRC / "combat/dc_combat_resolve.cpp").read_text(encoding="utf-8"))

    def test_every_swing_and_every_pulse_is_a_pet_blow_with_its_creatures_coefficient(self):
        self.assertEqual(self.minions.count("Combat::PetBlow const blow(MeleeCoefficient());"), 2)
        swing = self.minions[self.minions.index("Combat::PetBlow const blow(MeleeCoefficient());"):]
        self.assertLess(swing.index("Combat::PetBlow"), swing.index("Combat::Strike(player, target, kind.record, share)"))
        self.assertIn('std::string const name = "pet_proc_coefficient_" + std::to_string(kind.entry);', self.minions)
        self.assertIn('if (!Tunables::Has("combat", name)) return std::nullopt; return Tunables::Get("combat", name);', self.minions)

    def test_the_landing_coefficient_is_the_pets_while_one_blows(self):
        self.assertIn('return Proc::Landing(petBlow, petCoefficient, Numbers::Get(spellId, "proc_coefficient"));', self.resolve)
        self.assertIn("petBlow = true; petCoefficient = coefficient;", self.resolve)
        self.assertIn("petBlow = false; petCoefficient.reset();", self.resolve)

    def test_the_item_powers_and_the_gems_read_the_landing_coefficient(self):
        events = squeeze((SRC / "combat/dc_item_powers_events.cpp").read_text(encoding="utf-8"))
        gems = squeeze((SRC / "combat/dc_gem_powers.cpp").read_text(encoding="utf-8"))
        self.assertEqual(events.count("Combat::ProcCoefficient(spellId)"), 2)
        self.assertEqual(gems.count("Combat::ProcCoefficient(spellId)"), 1)
        for text in (events, gems):
            self.assertNotIn('Numbers::Get(spellId, "proc_coefficient")', text)

    def test_the_effects_the_power_files_do_not_scale_are_not_scaled(self):
        for path in ("classes/crusader/dc_crusader_passives.cpp", "classes/necromancer/dc_necromancer_passives.cpp",
                     "classes/demon_hunter/dc_demon_hunter_elemental_arrow.cpp", "classes/demon_hunter/dc_demon_hunter_bolas.cpp"):
            text = (SRC / path).read_text(encoding="utf-8")
            self.assertNotIn("Proc::Scaled", text, path)
            self.assertNotIn('"proc_coefficient"', text, path)


class NamedEffects(unittest.TestCase):
    """What each power file says of the effects the bead named: their numbers are the effect's own, none reads the landing attack's."""

    def labels(self, power):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the client data is not installed")
        data = decode_pow.parse_power(decode_pow.extract(f"Power/{power}.pow"))
        return data["labels"], data["tags"], decode_pow.TAG_PROC_COEFFICIENT

    def test_wrathful_is_paid_by_wrath_spent_and_indestructible_by_a_kill(self):
        labels, tags, tag = self.labels("X1_Crusader_Passive_Wrathful")
        self.assertIn("Life per Wrath Spent", labels)
        self.assertNotIn(tag, tags)
        labels, tags, tag = self.labels("X1_Crusader_Passive_Indestructible")
        self.assertIn("Life per Kill Bonus", labels)
        self.assertNotIn(tag, tags)

    def test_grisly_tribute_is_a_share_of_life_on_hit(self):
        labels, tags, tag = self.labels("P6_Necro_Passive_GrislyTribute")
        self.assertEqual([label for label in labels if label], ["% of Life Per Hit Healed"])
        self.assertNotIn(tag, tags)
        # Life on Hit is restored whole once per cast (stats.csv row 15), which a minion's hit follows
        stats = (SRC / "stats/dc_sustain.cpp").read_text(encoding="utf-8")
        self.assertIn("restores 100% of the sheet value once per cast", stats)

    def test_the_tentacle_heal_and_the_bitter_pill_are_numbers_of_the_runes_own_power(self):
        labels, _, _ = self.labels("DemonHunter_ElementalArrow")
        self.assertIn("RuneD: Life Absorption Scalar", labels)
        labels, _, _ = self.labels("DemonHunter_Bolas")
        self.assertIn("D: Chance to Gain Discipline", labels)
        self.assertIn("D: Discipline", labels)


if __name__ == "__main__":
    unittest.main()
