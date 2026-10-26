"""The Shaman's Elemental Weapon and its five runes (diablocraft-xnrvn.30).

What this proves, and how:

  * **The rules.** tests/shaman_elemental_weapon compiles the real src/classes/shaman/dc_shaman_elemental_weapon.h with no core and runs it
    over the sheet's numbers: each imbue by its name; the base imbue boosts every skill and a rune its own element; the passive
    bonus is always on and the activation's comes on top only while activated; Flametongue burns a Fire hit, Frostbrand chills a Cold
    hit and freezes it only activated, Windfury counts a Lightning hit; every Nth hit or cast fires on the count (Windfury's activated
    count is the smaller); the base imbue pays more Maelstrom on every skill and Maelstrom Weapon, activated, only on a Primary;
    Rockbiter's Armor and Windfury's attack speed on the sheet. Planted mutations (a rune boosting every element, the activation
    replacing the passive, a freeze that is not activated, a count that never resets, Maelstrom Weapon paying on every skill, the
    activation's Armor lost) must each make it fail.
  * **The wiring.** The class dispatches the cast, the damage factors, the landed hit, the generation, the upkeep and the logout to
    ElementalWeapon; the cast hits nothing (`BasePct` 0 on purpose); a rune's number is read from its own record (`Numbers::Own`), never
    inherited from the base skill; the imbue's own records are not boosted and ride on nothing; the freeze is once per enemy per
    activation and stretched like every stun; the free Secondary gives back what the core charged, reduced by the worn powers.
  * **The data.** The seven buff records are in class_buffs.csv with each rune's sheet numbers in their text; the burn's tick is a
    tunable in combat.csv and the newest migration.

What it does not prove: an imbue or an activation on a running server (docs/test-diablocraft-xnrvn.30.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_elemental_weapon.py
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
SHAMAN = MODULE / "src/classes/shaman"
HEADER = "dc_shaman_elemental_weapon.h"
FLAGS = ["-std=c++17", "-O1"]
SKILL = "Elemental Weapon"


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def combat():
    return {row["name"]: row["value"] or row["d3_value"] for row in read(MODULE / "data/tunables/combat.csv")}


def value(rune, token, qualifier=""):
    found = [r["value"] for r in read(MODULE / "data/d3/shaman_skill_values.csv")
             if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(found) == 1, (rune, token, qualifier, found)
    return found[0]


def args():
    return [value("", "damage_bonus_pct", "passive"), value("", "damage_bonus_pct", "activate"), value("", "regen_pct"),
            value("Flametongue", "damage_bonus_pct", "passive"), value("Flametongue", "damage_bonus_pct", "activate"),
            value("Windfury", "trigger_count", "passive"), value("Windfury", "trigger_count", "activate"),
            value("Rockbiter", "armor_pct", "passive"), value("Rockbiter", "armor_pct", "activate"),
            value("Windfury", "attack_speed_pct"), value("Maelstrom Weapon", "trigger_count"),
            value("Maelstrom Weapon", "regen_pct")]


def run_harness(mutation=None):
    text = (SHAMAN / HEADER).read_text(encoding="utf-8")
    if mutation:
        old, new = mutation
        if text.count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        text = text.replace(old, new)
    binary = harness_env.build(
        [MODULE / "tests/shaman_elemental_weapon/harness.cpp"], flags=FLAGS,
        files={"classes/shaman/" + HEADER: text,
               "classes/shaman/dc_shaman_attunement.h": (SHAMAN / "dc_shaman_attunement.h").read_text(encoding="utf-8"),
               "combat/dc_damage_buckets.h": (MODULE / "src/combat/dc_damage_buckets.h").read_text(encoding="utf-8")},
        includes=[MODULE / "src"])
    return harness_env.run([str(binary), *map(str, args())], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        ran = run_harness()
        self.assertEqual(ran.returncode, 0, ran.stdout[-1500:])
        print("\n  elemental weapon:", ran.stdout.strip())

    def test_planted_differences_are_caught(self):
        plants = [
            ("a rune boosting every element", "return element == Attunement::Element::Fire;", "return true;"),
            ("Rockbiter boosting Fire", "return element == Attunement::Element::Physical;", "return element == Attunement::Element::Fire;"),
            ("the base imbue boosting nothing", "            case Rune::Base:\n                return true;", "            case Rune::Base:\n                return false;"),
            ("the activation replacing the passive", "bonus.passivePct = passive;", "bonus.passivePct = active ? 0.0 : passive;"),
            ("the activation always on", "bonus.activePct = active ? activated : 0.0;", "bonus.activePct = activated;"),
            ("a freeze that is not activated", "effect.freeze = effect.chill && active;", "effect.freeze = effect.chill;"),
            ("no freeze", "effect.freeze = effect.chill && active;", "effect.freeze = false;"),
            ("Frostbrand chilling every hit", "effect.chill = rune == Rune::Frostbrand && element == Attunement::Element::Cold;",
             "effect.chill = rune == Rune::Frostbrand;"),
            ("Flametongue burning every hit", "effect.burn = rune == Rune::Flametongue && element == Attunement::Element::Fire;",
             "effect.burn = rune == Rune::Flametongue;"),
            ("Windfury counting every hit", "effect.echo = rune == Rune::Windfury && element == Attunement::Element::Lightning;",
             "effect.echo = rune == Rune::Windfury;"),
            ("a count that never resets", "            count = 0;\n            return true;", "            return true;"),
            ("a count with no number firing", "        if (!every)\n            return false;", ""),
            ("a count one late", "if (++count >= every)", "if (++count > every)"),
            ("Maelstrom Weapon paying on every skill", "return rune == Rune::MaelstromWeapon && active && primary ? pct : 0.0;",
             "return rune == Rune::MaelstromWeapon && active ? pct : 0.0;"),
            ("Maelstrom Weapon paying before the activation", "return rune == Rune::MaelstromWeapon && active && primary ? pct : 0.0;",
             "return rune == Rune::MaelstromWeapon && primary ? pct : 0.0;"),
            ("the base imbue paying only activated", "        if (rune == Rune::Base)\n            return pct;", "        if (rune == Rune::Base)\n            return active ? pct : 0.0;"),
            ("the activation's Armor lost", "sheet.armorPct = passiveArmor + (active ? activeArmor : 0.0);", "sheet.armorPct = passiveArmor;"),
            ("the activation's Armor replacing the passive's", "sheet.armorPct = passiveArmor + (active ? activeArmor : 0.0);",
             "sheet.armorPct = active ? activeArmor : passiveArmor;"),
            ("Windfury's speed always on", "if (rune == Rune::Windfury && active)", "if (rune == Rune::Windfury)"),
            ("a rune named wrongly", 'if (name == "Rockbiter")', 'if (name == "Rock Biter")'),
            ("the seam's fire read as cold", 'if (name == "fire")\n            return Attunement::Element::Fire;', 'if (name == "fire")\n            return Attunement::Element::Cold;'),
            ("the record's school always read", "std::string_view const name = seam ? std::string_view(seam) : std::string_view();", "std::string_view const name = std::string_view();"),
            ("a stranger read as physical", "        return record;\n    }\n\n    // Whether the imbue boosts", "        return Attunement::Element::Physical;\n    }\n\n    // Whether the imbue boosts"),
        ]
        for label, old, new in plants:
            with self.subTest(label):
                ran = run_harness((old, new))
                self.assertNotEqual(ran.returncode, 0, f"{label} was not caught: {ran.stdout[-300:]}")


def source(path):
    return (MODULE / path).read_text(encoding="utf-8")


def squeeze(text):
    return re.sub(r"\s+", " ", text)


# (token, rune, qualifier) the code reads from the imbue's own record
TOKENS = [("damage_bonus_pct", "", "passive"), ("damage_bonus_pct", "", "activate"), ("regen_pct", "", ""),
          ("duration_seconds", "", ""), ("damage_pct", "Flametongue", "passive"), ("damage_pct", "Flametongue", "activate"),
          ("dot_duration_seconds", "Flametongue", "passive"), ("dot_duration_seconds", "Flametongue", "activate"),
          ("chill_pct", "Frostbrand", ""), ("chill_duration_seconds", "Frostbrand", ""), ("freeze_duration_seconds", "Frostbrand", ""),
          ("trigger_count", "Windfury", "passive"), ("trigger_count", "Windfury", "activate"), ("damage_pct", "Windfury", ""),
          ("attack_speed_pct", "Windfury", ""), ("armor_pct", "Rockbiter", "passive"), ("armor_pct", "Rockbiter", "activate"),
          ("trigger_count", "Maelstrom Weapon", ""), ("regen_pct", "Maelstrom Weapon", "")]
BUFFS = {"Elemental Weapon - buff": ("5", "5"), "Elemental Weapon - Flametongue - buff": ("15", "100", "3"),
         "Elemental Weapon - Frostbrand - buff": ("15", "30", "2"), "Elemental Weapon - Windfury - buff": ("15", "5", "150"),
         "Elemental Weapon - Rockbiter - buff": ("15", "20"), "Elemental Weapon - Maelstrom Weapon - buff": ("5",),
         "Elemental Weapon - Maelstrom Weapon - free": ()}


def wiring_problems(files):
    """What is wrong with Elemental Weapon's wiring in `files` ({path: text}); [] when it is right."""
    problems = []
    needed = {
        "src/classes/shaman/dc_shaman.cpp": [
            "ElementalWeapon::BasePct(spellId)", "ElementalWeapon::Cast(player, spellId);",
            "ElementalWeapon::Multipliers(player, spellId, out);", "ElementalWeapon::Landed(player, target, spellId);",
            "ElementalWeapon::Upkeep(player);", "ElementalWeapon::Forget(player);"],
        "src/classes/shaman/dc_shaman_maelstrom.cpp": ["(1.0 + ElementalWeapon::GenerationPct(player, spellId) / 100.0)"],
    }
    for path, lines in needed.items():
        flat = squeeze(files[path])
        for line in lines:
            if line not in flat:
                problems.append(f"{path} lacks {line}")
    cpp = squeeze(files["src/classes/shaman/dc_shaman_elemental_weapon.cpp"])
    sheet = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/d3/shaman_skill_values.csv") if r["skill"] == SKILL}
    for token, rune, qualifier in TOKENS:
        if f'"{token}"' not in cpp:
            problems.append(f"the code does not read {token}")
        if (rune, token, qualifier) not in sheet:
            problems.append(f"the sheet has no {token} {qualifier} for {rune or 'the skill'}")
    if "Numbers::Own(spellId, token, qualifier)" not in cpp or "Numbers::Own(spellId, token).value_or(0.0)" not in cpp:
        problems.append("a rune's number is not read from its own record")
    if re.search(r"Numbers::(Get|Num)\(", cpp.replace('Numbers::Num(spellId, "cost_resource")', "")):
        problems.append("a number is read with its base skill's as the fallback")
    if "return RowOf(spellId) ? std::optional<double>(0.0) : std::nullopt;" not in cpp:
        problems.append("the cast has a hit of its own")
    if cpp.count("|| RowOf(spellId)") < 2:
        problems.append("the imbue's own records are boosted or ride on a hit")
    if "state.frozen.insert(target->GetGUID().GetRawValue()).second" not in cpp:
        problems.append("the freeze is not once per enemy")
    if "state.frozen.clear();" not in cpp:
        problems.append("a new activation does not start the freezes over")
    if '* ItemPowers::StunFactor(player)' not in cpp:
        problems.append("the freeze is not stretched by the stun powers")
    if 'Combat::Strike(player, target, imbue, Own(imbue, "damage_pct", ""))' not in cpp:
        problems.append("Windfury does not strike again with its own percent")
    if 'PeriodicStrike::Start(player, target, imbue, Own(imbue, "damage_pct", qualifier)' not in cpp:
        problems.append("the burn is not the imbue's own percent")
    if 'Tunable("elemental_weapon_burn_tick_seconds")' not in cpp:
        problems.append("the burn's tick is not the tunable")
    if "Combat::ModifiedDurationSeconds(player, spellId," not in cpp:
        problems.append("the activation ignores the worn powers")
    if "Numbers::Num(spellId, \"cost_resource\") * Combat::CostReductionFactor(player, spellId)" not in cpp:
        problems.append("the free cast does not give back what the core charged")
    if "state.rune != Rune::MaelstromWeapon" not in cpp:
        problems.append("a free cast outlives its imbue")
    if "DealtElement(DC::Combat::Shaman::Element(player, spellId), Attunement::ElementOf(spellId))" not in cpp:
        problems.append("a hit's element is the record's school, not the dealt one")
    if cpp.count("DealtBy(player, spellId)") < 2:
        problems.append("the damage factors or the riders do not use the dealt element")
    if "button->GetAction() == row.id" not in cpp:
        problems.append("the imbue is not the skill on the bar")
    names = set(re.findall(r'Tunable\("([a-z_]+)"\)', cpp))
    numbers = combat()
    problems += [f"combat.csv has no {name}" for name in sorted(names) if name not in numbers]
    if not names:
        problems.append("the code names no tunable")
    return problems


class Wiring(unittest.TestCase):
    PATHS = ["src/classes/shaman/dc_shaman.cpp", "src/classes/shaman/dc_shaman_maelstrom.cpp",
             "src/classes/shaman/dc_shaman_elemental_weapon.cpp"]

    def files(self):
        return {path: source(path) for path in self.PATHS}

    def test_the_wiring_is_whole(self):
        self.assertEqual(wiring_problems(self.files()), [])

    def test_a_planted_gap_is_caught(self):
        plants = [
            ("src/classes/shaman/dc_shaman.cpp", "ElementalWeapon::BasePct(spellId)", "ElementalWeapon::Nothing(spellId)"),
            ("src/classes/shaman/dc_shaman.cpp", "ElementalWeapon::Cast(player, spellId);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "ElementalWeapon::Multipliers(player, spellId, out);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "ElementalWeapon::Landed(player, target, spellId);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "ElementalWeapon::Upkeep(player);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "ElementalWeapon::Forget(player);", ""),
            ("src/classes/shaman/dc_shaman_maelstrom.cpp", "ElementalWeapon::GenerationPct(player, spellId)", "0.0"),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", '"freeze_duration_seconds"', '"freeze_seconds"'),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", '"attack_speed_pct"', '"speed_pct"'),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", "Numbers::Own(spellId, token, qualifier)", "Numbers::Get(spellId, token, qualifier)"),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", "std::optional<double>(0.0)", "std::optional<double>(150.0)"),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", "|| RowOf(spellId)) return;", ") return;"),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", "state.frozen.insert(target->GetGUID().GetRawValue()).second", "true"),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", "state.frozen.clear();", ""),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", "* ItemPowers::StunFactor(player)", ""),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", 'Combat::Strike(player, target, imbue, Own(imbue, "damage_pct", ""))',
             "Combat::Strike(player, target, imbue)"),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", 'Tunable("elemental_weapon_burn_tick_seconds")', "0.5"),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", "Combat::ModifiedDurationSeconds(player, spellId,", "Combat::Nothing(player, spellId,"),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", " * Combat::CostReductionFactor(player, spellId)", ""),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", "button->GetAction() == row.id", "true"),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", "DealtElement(DC::Combat::Shaman::Element(player, spellId), Attunement::ElementOf(spellId))",
             "Attunement::ElementOf(spellId)"),
            ("src/classes/shaman/dc_shaman_elemental_weapon.cpp", "effect = EffectOf(rune, DealtBy(player, spellId), active);",
             "effect = EffectOf(rune, Attunement::ElementOf(spellId), active);"),
        ]
        for path, old, new in plants:
            with self.subTest(old):
                files = self.files()
                self.assertIn(old, squeeze(files[path]) if old not in files[path] else files[path])
                if old in files[path]:
                    files[path] = files[path].replace(old, new)
                else:
                    files[path] = squeeze(files[path]).replace(old, new)
                self.assertNotEqual(wiring_problems(files), [], f"{old!r} -> {new!r} was not caught")


class Data(unittest.TestCase):
    def test_the_buffs_are_records_that_state_the_sheets_numbers(self):
        rows = {r["identity"]: r for r in read(MODULE / "data/class_buffs.csv")}
        for identity, numbers in BUFFS.items():
            with self.subTest(identity):
                self.assertIn(identity, rows)
                self.assertEqual("shaman", rows[identity]["class"])
                for number in numbers:
                    self.assertRegex(rows[identity]["text"], r"(?<!\d)%s(?!\d)" % number)

    def test_the_imbue_buffs_are_the_ones_the_code_names(self):
        cpp = source("src/classes/shaman/dc_shaman_elemental_weapon.cpp")
        for identity in BUFFS:
            self.assertIn('"%s"' % identity, cpp)

    def test_the_tunable_is_in_the_newest_migration(self):
        migration = (MODULE / "data/sql/db-world/updates" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        self.assertIn("('combat', 'elemental_weapon_burn_tick_seconds',", migration)

    def test_the_skill_casts_on_the_shaman_and_every_rune_states_three_seconds(self):
        rows = {r["skill"]: r for r in read(MODULE / "data/d3/skill_targeting.csv")}
        self.assertEqual(rows[SKILL]["target_type"], "self")
        for rune in ("", "Flametongue", "Frostbrand", "Windfury", "Rockbiter", "Maelstrom Weapon"):
            self.assertEqual(value(rune, "duration_seconds"), "3")

    def test_the_cast_has_no_hit_of_its_own_on_purpose(self):
        self.assertNotIn('"Elemental Weapon":', source("scripts/tests/classes/test_shaman_hits.py").split("SKILLS =")[1].split("\n")[0])


if __name__ == "__main__":
    unittest.main()
