"""Demon Hunter 'Requires Bow' (src/classes/demon_hunter/dc_demon_hunter_ranged_weapon.h and .cpp).

decisions.md 2026-10-21: the eight Demon Hunter skills whose tooltip says "Requires Bow" are cast only with a bow, a crossbow or a
hand crossbow wielded, as in D3; otherwise the cast is refused with the stock equipped-item error.

What this proves, and how:

  * **The rule, over the sheet and the item data.** tests/demon_hunter_ranged_weapon/harness.cpp compiles the real
    dc_demon_hunter_ranged_weapon.h and is fed cases this test writes: each of the eight skills the sheet marks (read from
    demon_hunter_skill_values.csv) with each ranged weapon kind in the main hand (Bow, Crossbow, Hand Crossbow, Repeating
    Crossbow), in the off hand, and with each melee kind and nothing; the weapon subclasses are the item generator's own
    (generate_sql.py WEAPON_SUBCLASS), and a skill that does not carry the token (Impale, Caltrops, Strafe...) is cast with
    anything. Five mutations planted in a scratch copy (the bow does not count, the crossbow does not count, the off hand is not
    looked at, an empty hand is a ranged weapon, a skill that does not require one is refused) must each make it fail.
  * **The sheet is the column.** The token's rows are exactly the skills whose tooltip text in demon_hunter_skills.csv says
    "Requires Bow", every such skill has one, and the generated value table gives each of its runes the same row; no skill name
    appears in the code.
  * **The wiring.** The class's CanCast maps a refusal to the stock error, the engine asks it for a player's own cast only (not a
    triggered one) after the other classes, the .cpp reads the weapon from the item template and checks the core's subclass
    constants.

What it does not prove: the client's text for the error, or anything on a running server. docs/test-diablocraft-vawmy.11.md's.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_ranged_weapon.py
"""

import csv
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/demon_hunter/dc_demon_hunter_ranged_weapon.h"
SOURCES = [HEADER, "tests/demon_hunter_ranged_weapon/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_ranged_weapon.cpp"
TOKEN = "requires_ranged_weapon"
NO_WEAPON = 0xFFFFFFFF
RANGED = ("Bow", "Crossbow", "Hand Crossbow", "Repeating Crossbow")
OTHER_RANGED = ("Hydra Bow", "Ballista")  # other classes' bows, the same subclass


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def marked_skills():
    return sorted({r["skill"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["token"] == TOKEN})


def weapon_subclasses():
    import generate_sql
    return dict(generate_sql.WEAPON_SUBCLASS)


def cases():
    kinds = weapon_subclasses()
    ranged = {name: kinds[name] for name in RANGED}
    melee = {name: sub for name, sub in kinds.items() if name not in RANGED and name not in OTHER_RANGED}
    lines = []
    for skill in marked_skills():
        for name, sub in ranged.items():
            lines.append((1, sub, NO_WEAPON, 1))                    # a ranged weapon in the main hand
            lines.append((1, NO_WEAPON, sub, 1))                    # in the off hand
            lines.append((1, kinds["Sword"], sub, 1))               # a melee main hand with it in the off hand
        for name, sub in melee.items():
            lines.append((1, sub, NO_WEAPON, 0))                    # a melee weapon alone
            lines.append((1, sub, sub, 0))                          # two of them
        lines.append((1, NO_WEAPON, NO_WEAPON, 0))                  # nothing
    for name, sub in kinds.items():
        lines.append((0, sub, NO_WEAPON, 1))                        # a skill that does not require one
    lines.append((0, NO_WEAPON, NO_WEAPON, 1))
    return lines


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8")
             for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/demon_hunter_ranged_weapon/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "cases.txt"
        path.write_text("".join("%d %d %d %d\n" % line for line in cases()), encoding="utf-8")
        return harness_env.run([str(binary), str(path)], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_every_marked_skill_with_every_weapon_kind(self):
        self.assertEqual(len(marked_skills()), 8)
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        count = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(count, 8 * (3 * 4 + 2) + 1, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_the_item_data_has_the_four_ranged_kinds_on_the_two_subclasses(self):
        kinds = weapon_subclasses()
        self.assertEqual({kinds[name] for name in RANGED}, {2, 18})
        extras = {name for name, sub in kinds.items() if sub in (2, 18) and name not in RANGED}
        self.assertEqual(extras, set(OTHER_RANGED))

    def test_a_planted_difference_is_caught(self):
        guard = "return subclass == Bow || subclass == Crossbow;"
        mutations = [
            ("the bow does not count", (HEADER, guard, "return subclass == Crossbow;")),
            ("the crossbow does not count", (HEADER, guard, "return subclass == Bow;")),
            ("the off hand is not looked at", (HEADER, "return !requiresRanged || IsRanged(mainHand) || IsRanged(offHand);",
                                               "return !requiresRanged || IsRanged(mainHand);")),
            ("an empty hand is a ranged weapon", (HEADER, guard, "return subclass == Bow || subclass == Crossbow || subclass == NoWeapon;")),
            ("a skill that does not require one is refused", (HEADER, "return !requiresRanged || IsRanged(mainHand) || IsRanged(offHand);",
                                                              "return IsRanged(mainHand) || IsRanged(offHand);")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheet(unittest.TestCase):
    def test_the_token_is_on_exactly_the_skills_whose_tooltip_says_requires_bow(self):
        tooltip = {r["skill_name"] for r in read(D3 / "demon_hunter_skills.csv")
                   if "Requires Bow" in r["full_tooltip_text"].split(" | ")}
        self.assertEqual(len(tooltip), 8)
        self.assertEqual(set(marked_skills()), tooltip)
        rows = [r for r in read(D3 / "demon_hunter_skill_values.csv") if r["token"] == TOKEN]
        self.assertEqual(len(rows), 8)
        for row in rows:
            self.assertEqual((row["rune"], row["qualifier"], row["value"]), ("", "", "1"), row["skill"])
            self.assertIn("decisions.md 2026-10-21", row["source"])

    def test_every_rune_of_a_marked_skill_has_the_row_in_the_value_table(self):
        mapped = {(r["skill"], r["rune"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["token"] == TOKEN}
        runes = {}
        for r in read(D3 / "demon_hunter_runes.csv"):
            runes.setdefault(r["skill_name"], []).append(r["rune_name"])
        for skill in marked_skills():
            self.assertEqual(mapped[(skill, "")]["origin"], "own", skill)
            self.assertEqual(mapped[(skill, "")]["source"], "exact", skill)
            for rune in runes[skill]:
                self.assertEqual(mapped[(skill, rune)]["origin"], "inherited", (skill, rune))

    def test_no_skill_is_named_in_the_code(self):
        text = CODE.read_text(encoding="utf-8") + (MODULE / HEADER).read_text(encoding="utf-8")
        for skill in marked_skills():
            self.assertNotIn(skill, text)
        self.assertIn('Numbers::Has(spellId, "requires_ranged_weapon")', text)

    def test_the_generator_lets_the_token_through_and_the_migration_carries_the_rows(self):
        generator = (MODULE / "scripts/generate/classes/generate_spells.py").read_text(encoding="utf-8")
        self.assertIn('"requires_ranged_weapon"', generator)
        migration = (MODULE / "data/sql/db-world/updates/combat_0097_demon_hunter_requires_ranged_weapon.sql").read_text(encoding="utf-8")
        # a row for each of the eight skills' records: the skill and its five runes
        self.assertEqual(len(re.findall(r"'requires_ranged_weapon'", migration)), 8 * 6)


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))
        self.engine = re.sub(r"\s+", " ", (MODULE / "src/combat/dc_combat.cpp").read_text(encoding="utf-8"))

    def test_the_class_maps_a_refusal_to_the_stock_error(self):
        self.assertIn("if (!RangedWeapon::Permitted(player, spellId)) return SPELL_FAILED_EQUIPPED_ITEM_CLASS_MAINHAND;", self.dispatch)

    def test_the_engine_asks_for_a_players_own_cast_after_the_other_classes(self):
        call = "if (!spell->IsTriggered()) if (SpellCastResult const refused = DemonHunter::CanCast(player, spell->GetSpellInfo()->Id); refused != SPELL_CAST_OK)"
        self.assertEqual(self.engine.count(call), 1)
        self.assertLess(self.engine.index("Necromancer::CanCast("), self.engine.index(call))

    def test_the_weapon_is_read_from_the_item_template_of_both_hands(self):
        self.assertIn("worn->Class == ITEM_CLASS_WEAPON ? worn->SubClass : NoWeapon", self.code)
        self.assertIn("SubclassIn(player, EQUIPMENT_SLOT_MAINHAND), SubclassIn(player, EQUIPMENT_SLOT_OFFHAND)", self.code)
        self.assertIn("static_assert(Bow == ITEM_SUBCLASS_WEAPON_BOW && Crossbow == ITEM_SUBCLASS_WEAPON_CROSSBOW", self.code)


if __name__ == "__main__":
    unittest.main()
