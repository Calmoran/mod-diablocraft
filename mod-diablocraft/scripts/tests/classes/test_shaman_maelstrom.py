"""The Shaman's Maelstrom, Overcharge and Attunement (diablocraft-xnrvn.8, Shaman 2b).

What this proves, and how:

  * **The three rules.** tests/shaman_maelstrom, tests/shaman_overcharge and tests/shaman_attunement compile the real
    src/classes/shaman/dc_shaman_{maelstrom,overcharge,attunement}.h with no core and run them: a gain splits between the bar and
    Overcharge at the maximum and loses nothing; tenths of overflow add up as a whole does; a new stack restarts the time of all and
    points short of a stack do not; the cap is the base or Storm Surge's maximum; the stacks and the points toward the next both
    expire; a Secondary takes every stack once; each element gives its own bonus and no other; only a Secondary or Primal skill
    moves the Attunement, and every skill or rune the research sheets give no element (blank, or "Attuned") keeps it. Every number
    is read from combat.csv and the passive's value sheet, none typed in the harness. Planted mutations (the overflow lost, the
    carry kept past the cap, no tolerance, a new stack not restarting the time, the cap ignored, the take leaving stacks, the
    bonus on the wrong element, a Primary moving the Attunement, Elemental Blast moving it) must each make a harness fail.
  * **The wiring.** The dispatch calls the class from the combat engine (Connected, Casting, Multipliers, RegisterScripts); a
    Primary's generation reads the rune's own `new` number before the skill's; the stats code keeps every class whose primary
    resource is on the Rage slot out of the core's rage rewards, read from the registry; every tunable the class code names is a
    row of combat.csv and of the newest tunables migration; every buff the class code names is a row of class_buffs.csv with a
    generated record; each buff's text states its number from the same tunable the server reads (Cold's fraction is pinned to the
    tunable here, as a record's $s holds a whole number only); Paragon's Maximum Resource row names Maelstrom, one a point. Planted:
    each call gone, the rune's number not read, a class named in the reward hook, a tunable renamed, a buff renamed, a text's
    number changed.

What it does not prove: anything on a running server (docs/test-diablocraft-xnrvn.8.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_maelstrom.py
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
RESEARCH = REPO / "docs/research/shaman"
FLAGS = ["-std=c++17", "-O1"]


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def combat():
    return {row["name"]: row["value"] or row["d3_value"] for row in read(MODULE / "data/tunables/combat.csv")}


def header(name):
    return (SHAMAN / name).read_text(encoding="utf-8")


def run_harness(folder, header_name, args=(), mutation=None):
    """The harness of tests/<folder> over the real header, or over its text with one planted change."""
    text = header(header_name)
    if mutation:
        old, new = mutation
        if text.count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {header_name}")
        text = text.replace(old, new)
    binary = harness_env.build([MODULE / "tests" / folder / "harness.cpp"], flags=FLAGS,
                               files={"classes/shaman/" + header_name: text}, includes=[MODULE / "src"])
    return harness_env.run([str(binary), *map(str, args)], capture_output=True, text=True)


def overcharge_args():
    numbers = combat()
    surge = {r["token"]: r["value"] for r in read(MODULE / "data/d3/shaman_passive_values.csv") if r["skill"] == "Storm Surge"}
    return [numbers["overcharge_points_per_stack"], numbers["overcharge_base_max_stacks"], surge["max_count"],
            numbers["overcharge_damage_per_stack_pct"], numbers["overcharge_seconds"]]


def keeps_lines():
    """('category|skill|rune' that carries an element, ... that does not), from the research sheets: a blank or `Attuned` cell is none."""
    sets, keeps = [], []
    skills = [r for r in read(RESEARCH / "shaman_skills.tokenised.csv") if r["category"] in ("Secondary", "Primal")]
    runes = read(RESEARCH / "shaman_runes.tokenised.csv")
    for skill in skills:
        for rune_name, element in [("", skill["element"])] + [(r["rune_name"], r["element"]) for r in runes
                                                              if r["skill_name"] == skill["skill_name"]]:
            line = f"{skill['category']}|{skill['skill_name']}|{rune_name}"
            (keeps if element in ("", "Attuned") else sets).append(line)
    return sets, keeps


def attunement_args():
    numbers = combat()
    sets, keeps = keeps_lines()
    return [numbers["attunement_fire_damage_pct"], numbers["attunement_cold_life_regen_pct"],
            numbers["attunement_physical_armor_pct"], numbers["attunement_lightning_attack_speed_pct"], *sets, "--", *keeps]


class Rules(unittest.TestCase):
    def test_maelstrom(self):
        ran = run_harness("shaman_maelstrom", "dc_shaman_maelstrom.h")
        self.assertEqual(ran.returncode, 0, ran.stdout[-1500:])
        print("\n  maelstrom:", ran.stdout.strip())

    def test_overcharge(self):
        ran = run_harness("shaman_overcharge", "dc_shaman_overcharge.h", overcharge_args())
        self.assertEqual(ran.returncode, 0, ran.stdout[-1500:])
        print("\n  overcharge:", ran.stdout.strip())

    def test_attunement(self):
        ran = run_harness("shaman_attunement", "dc_shaman_attunement.h", attunement_args())
        self.assertEqual(ran.returncode, 0, ran.stdout[-1500:])
        print("\n  attunement:", ran.stdout.strip())

    def test_the_sheets_give_both_kinds(self):
        sets, keeps = keeps_lines()
        self.assertGreater(len(sets), 20)
        # Elemental Blast and its five runes, Bloodlust and its five, Ascendance and Eternal Ascendance.
        self.assertGreaterEqual(len(keeps), 14)

    def test_planted_differences_are_caught(self):
        overcharge = [
            ("the overflow lost", "dc_shaman_overcharge.h", "        bank.carry += overflow;\n", "        bank.carry += 0;\n"),
            ("no tolerance for the tenths", "dc_shaman_overcharge.h", "bank.carry / perStack + 1e-9", "bank.carry / perStack"),
            ("the carry kept past the cap", "dc_shaman_overcharge.h", "        if (bank.stacks >= cap)\n            bank.carry = 0;\n", ""),
            ("a gain short of a stack restarting the time", "dc_shaman_overcharge.h", "        bank.carryUntil = now + ms;\n",
             "        bank.carryUntil = now + ms;\n        bank.until = now + ms;\n"),
            ("a new stack not restarting the time", "dc_shaman_overcharge.h", "            bank.until = now + ms;\n", ""),
            ("the cap ignored", "dc_shaman_overcharge.h", "            bank.stacks = std::min(bank.stacks + gained, cap);\n",
             "            bank.stacks = bank.stacks + gained;\n"),
            ("Storm Surge not raising the cap", "dc_shaman_overcharge.h", "return stormSurge ? std::max(base, stormSurgeMax) : base;",
             "return base;"),
            ("the take leaving the stacks", "dc_shaman_overcharge.h", "        bank.stacks = 0;\n        bank.until = 0;\n        return held;",
             "        return held;"),
            ("the stacks never expiring", "dc_shaman_overcharge.h", "return bank.stacks == 0 || bank.until <= now;",
             "return bank.stacks == 0;"),
            ("stale points kept", "dc_shaman_overcharge.h", "        if (bank.carryUntil <= now)\n            bank.carry = 0;\n", ""),
            ("a lost passive not cutting the stacks", "dc_shaman_overcharge.h", "return Over(bank, now) ? 0 : std::min(bank.stacks, cap);",
             "return Over(bank, now) ? 0 : bank.stacks;"),
            ("the damage per stack once", "dc_shaman_overcharge.h", "return stacks * perStackPct;", "return stacks ? perStackPct : 0;"),
        ]
        for label, name, old, new in overcharge:
            with self.subTest(label):
                ran = run_harness("shaman_overcharge", name, overcharge_args(), (old, new))
                self.assertNotEqual(ran.returncode, 0, f"{label} was not caught: {ran.stdout[-300:]}")
        maelstrom = [
            ("the overflow lost", "points - paid", "0.0"),
            ("the room ignored", "std::min(points, room)", "points"),
            ("the flat points on every category", "double const flat = primary ? std::max(0.0, primaryFlat) : 0.0;",
             "double const flat = std::max(0.0, primaryFlat);"),
            ("the percent before the flat points", "return (sheet + flat) * (1.0 + percent / 100.0);",
             "return sheet * (1.0 + percent / 100.0) + flat;"),
        ]
        for label, old, new in maelstrom:
            with self.subTest(label):
                ran = run_harness("shaman_maelstrom", "dc_shaman_maelstrom.h", mutation=(old, new))
                self.assertNotEqual(ran.returncode, 0, f"{label} was not caught: {ran.stdout[-300:]}")
        attunement = [
            ("Fire giving the Cold bonus", "bonus.damagePct = table.fireDamagePct * multiplier;", "bonus.lifeRegenPct = table.fireDamagePct * multiplier;"),
            ("Lightning giving armor", "bonus.attackSpeedPct = table.lightningAttackSpeedPct * multiplier;",
             "bonus.armorPct = table.lightningAttackSpeedPct * multiplier;"),
            ("the multiplier ignored", "bonus.armorPct = table.physicalArmorPct * multiplier;", "bonus.armorPct = table.physicalArmorPct;"),
            ("a Primary moving it", 'if (category != "Secondary" && category != "Primal")', 'if (category != "Secondary" && category != "Primal" && category != "Primary")'),
            ("a Defensive skill moving it", 'if (category != "Secondary" && category != "Primal")\n            return false;',
             'if (category != "Secondary" && category != "Primal" && category != "Defensive")\n            return false;'),
            ("Elemental Blast moving it", '        {"Elemental Blast", "*"},\n', ""),
            ("Bloodlust moving it", '        {"Bloodlust", "*"},\n', ""),
            ("Eternal Ascendance moving it", '        {"Ascendance", "Eternal Ascendance"},\n', ""),
            ("plain Ascendance moving it", '        {"Ascendance", ""},\n', ""),
            ("a keeping skill moving it", "return sets ? cast : current;", "return cast;"),
        ]
        for label, old, new in attunement:
            with self.subTest(label):
                ran = run_harness("shaman_attunement", "dc_shaman_attunement.h", attunement_args(), (old, new))
                self.assertNotEqual(ran.returncode, 0, f"{label} was not caught: {ran.stdout[-300:]}")


def source(path):
    return (MODULE / path).read_text(encoding="utf-8")


def wiring_problems(files):
    """What is wrong with the Shaman's wiring in `files` ({path: text}); [] when it is right."""
    problems = []
    for path, needed in {
        "src/combat/dc_combat_resolve.cpp": ["Shaman::Connected(player, spellId, enemies);", "Shaman::Casting(player, shell.spellId);"],
        "src/combat/dc_combat.cpp": ["Shaman::Multipliers(player, target, shell.spellId, hit.factors);", "Shaman::RegisterScripts();"],
        "src/combat/dc_combat_internal.h": ['#include "../classes/shaman/dc_shaman.h"'],
    }.items():
        for line in needed:
            if line not in files[path]:
                problems.append(f"{path} lacks {line}")
    maelstrom = files["src/classes/shaman/dc_shaman_maelstrom.cpp"]
    if 'Numbers::Get(spellId, "generated_resource", "new")' not in re.sub(r"\s+", " ", maelstrom).replace("( ", "("):
        problems.append("a Primary's generation does not read the rune's own `new` number first")
    stats = files["src/stats/dc_stats.cpp"]
    if "return !RageResource(unit->ToPlayer());" not in stats or "return row && row->power == Pulse::Rage;" not in stats:
        problems.append("the rage reward hook does not read the registry's Rage rows")
    code = "\n".join(line for line in stats.splitlines() if not line.lstrip().startswith("//"))
    if re.search(r"CLASS_SHAMAN|Shaman", code):
        problems.append("dc_stats.cpp names the Shaman")
    return problems


def tunable_names(text):
    return set(re.findall(r'Tunable\("([a-z_]+)"\)', text))


class Wiring(unittest.TestCase):
    PATHS = ["src/combat/dc_combat_resolve.cpp", "src/combat/dc_combat.cpp", "src/combat/dc_combat_internal.h",
             "src/classes/shaman/dc_shaman_maelstrom.cpp", "src/stats/dc_stats.cpp"]

    def files(self):
        return {path: source(path) for path in self.PATHS}

    def test_the_wiring_is_whole(self):
        self.assertEqual(wiring_problems(self.files()), [])

    def test_a_planted_gap_is_caught(self):
        plants = [
            ("src/combat/dc_combat_resolve.cpp", "        Shaman::Connected(player, spellId, enemies);\n", ""),
            ("src/combat/dc_combat_resolve.cpp", "                Shaman::Casting(player, shell.spellId);\n", ""),
            ("src/combat/dc_combat.cpp", "        Shaman::Multipliers(player, target, shell.spellId, hit.factors);\n", ""),
            ("src/combat/dc_combat.cpp", "        Shaman::RegisterScripts();\n", ""),
            ("src/classes/shaman/dc_shaman_maelstrom.cpp", '"generated_resource", "new"', '"generated_resource", "old"'),
            ("src/stats/dc_stats.cpp", "return !RageResource(unit->ToPlayer());", "return !(unit->ToPlayer() && unit->ToPlayer()->getClass() == CLASS_WARRIOR);"),
            ("src/stats/dc_stats.cpp", "return row && row->power == Pulse::Rage;", "return row && row->power == Pulse::Rage || unit_is_shaman;"),
        ]
        for path, old, new in plants:
            with self.subTest(old):
                files = self.files()
                self.assertIn(old, files[path])
                files[path] = files[path].replace(old, new)
                self.assertNotEqual(wiring_problems(files), [], f"{old!r} -> {new!r} was not caught")

    def test_every_tunable_the_class_names_is_a_row(self):
        numbers = combat()
        names = set()
        for path in SHAMAN.glob("*.cpp"):
            names |= tunable_names(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(names), 8, names)
        self.assertEqual(sorted(n for n in names if n not in numbers), [])
        migration = (MODULE / "data/sql/db-world/updates" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        for name in sorted(names | {"maelstrom_decay_per_second", "maelstrom_decay_wait_seconds"}):
            self.assertIn(f"('combat', '{name}',", migration, name)

    def test_a_renamed_tunable_is_caught(self):
        numbers = combat()
        names = tunable_names(source("src/classes/shaman/dc_shaman_overcharge.cpp"))
        planted = tunable_names(source("src/classes/shaman/dc_shaman_overcharge.cpp").replace("overcharge_seconds", "overcharge_secs"))
        self.assertNotEqual(sorted(n for n in names if n not in numbers), sorted(n for n in planted if n not in numbers))

    def test_every_buff_the_class_names_is_a_generated_record(self):
        names = set()
        for path in SHAMAN.glob("*.cpp"):
            names |= set(re.findall(r'"((?:Overcharge|Attunement)[^"]* - buff)"', path.read_text(encoding="utf-8")))
        names |= {f"Attunement - {element} - buff" for element in ("Fire", "Cold", "Physical", "Lightning")}
        rows = {r["identity"]: r for r in read(MODULE / "data/class_buffs.csv")
                if r["class"] == "shaman" and r["identity"].startswith(("Overcharge", "Attunement"))}
        with (MODULE / "data/generated/spell_helper_ids.csv").open(encoding="utf-8") as stream:
            helpers = {r[0]: int(r[1]) for r in csv.reader(stream) if r and r[1].isdigit()}
        self.assertEqual(sorted(names), sorted(rows))
        for name in sorted(names):
            self.assertIn(name, helpers, name)
            self.assertTrue(86500 <= helpers[name] <= 86599, helpers[name])

    def test_the_texts_state_the_tunables(self):
        numbers = combat()
        rows = {r["identity"]: r for r in read(MODULE / "data/class_buffs.csv")
                if r["class"] == "shaman" and r["identity"].startswith(("Overcharge", "Attunement"))}
        # A whole number is a record's $s, read from the tunable by the generator; the fraction is written in the text.
        for identity, tunable in (("Overcharge - buff", "overcharge_damage_per_stack_pct"),
                                  ("Attunement - Fire - buff", "attunement_fire_damage_pct"),
                                  ("Attunement - Physical - buff", "attunement_physical_armor_pct"),
                                  ("Attunement - Lightning - buff", "attunement_lightning_attack_speed_pct")):
            self.assertEqual(rows[identity]["amount_1"], f"tunable:combat/{tunable}", identity)
            self.assertIn("$s1", rows[identity]["text"], identity)
            self.assertTrue(float(numbers[tunable]).is_integer(), tunable)
        cold = rows["Attunement - Cold - buff"]
        self.assertEqual(cold["amount_1"], "")
        self.assertNotIn("$s", cold["text"])
        self.assertEqual(re.findall(r"[0-9.]+(?=%)", cold["text"]), [f"{float(numbers['attunement_cold_life_regen_pct']):g}"])
        self.assertEqual(rows["Overcharge - buff"]["max_stacks"], "passive:Storm Surge/max_count")

    def test_a_changed_text_number_is_caught(self):
        numbers = combat()
        text = {r["identity"]: r for r in read(MODULE / "data/class_buffs.csv") if r["class"] == "shaman"}["Attunement - Cold - buff"]["text"]
        self.assertNotEqual(re.findall(r"[0-9.]+(?=%)", text.replace("0.5%", "5%")), [f"{float(numbers['attunement_cold_life_regen_pct']):g}"])

    def test_paragon_gives_maelstrom_a_point(self):
        rows = [r for r in read(MODULE / "data/d3/paragon.csv") if r["stat_key"] == "resource"]
        self.assertEqual(len(rows), 1)
        self.assertIn("maelstrom", rows[0]["resource_keys"].split(";"))
        self.assertEqual(rows[0]["per_point"], "1")
        self.assertIn('"Maelstrom", Role::Primary, 1, "Rage", 1.0, 100.0, 0.0, Decay::Timed, 0x558FF2, 1.0, false, "MAELSTROM", true}',
                      source("src/classes/dc_resource_data.h"))


if __name__ == "__main__":
    unittest.main()
