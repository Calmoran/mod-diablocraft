"""The Shaman's Thunderstorm and its five runes (diablocraft-xnrvn.16).

What this proves, and how:

  * **The rules.** tests/shaman_thunderstorm compiles the real src/classes/shaman/dc_shaman_thunderstorm.h with no core and runs
    it over the sheet's numbers: each rune by its name; the plain thunderclap and Volcanic Gale knock back; Gale Force doubles the
    knockback and stuns; Frost Storm freezes in place of the knockback; Eye of the Storm trades the knockback away; Sandstorm
    blinds an ordinary enemy and only slows an elite or a boss; the storm and the ring tick their per-second percent so the ticks add
    up to the seconds' worth; a blind misses its percent for its seconds and no longer. Every number is read from the values
    sheet and combat.csv, none typed in the harness. Planted mutations (the factor dropped, the stun or freeze on the wrong rune,
    the knockback kept on Frost Storm, an elite blinded, the tick percent not scaled by the tick, the blind never ending) must each
    make it fail.
  * **The wiring.** The engine tells the class of a cast (Shaman::Cast), asks it for a record's hit (Shaman::BasePct) and its blind
    (Shaman::MissChance); the class dispatches to Thunderstorm in its own block; every sheet token the code reads is a row of the
    rune it is read for; every tunable it names is a row of combat.csv and of the newest tunables migration; the thunderclap's
    radius is the targeting row's. Planted: each seam gone, a token renamed, a tunable renamed.

What it does not prove: anything on a running server (docs/test-diablocraft-xnrvn.16.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_thunderstorm.py
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
HEADER = "dc_shaman_thunderstorm.h"
FLAGS = ["-std=c++17", "-O1"]


def read(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def combat():
    return {row["name"]: row["value"] or row["d3_value"] for row in read(MODULE / "data/tunables/combat.csv")}


def value(rune, token, skill="Thunderstorm", qualifier=""):
    found = [r["value"] for r in read(MODULE / "data/d3/shaman_skill_values.csv")
             if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (skill, rune, token, qualifier)]
    assert len(found) == 1, (skill, rune, token, found)
    return found[0]


def args():
    numbers = combat()
    return [numbers["thunderstorm_knockback_yards"], numbers["thunderstorm_gale_force_knockback_factor"],
            value("Gale Force", "stun_duration_seconds"), value("Frost Storm", "freeze_duration_seconds"),
            numbers["thunderstorm_storm_tick_seconds"], value("Eye of the Storm", "damage_pct"),
            value("Eye of the Storm", "duration_seconds"), numbers["thunderstorm_ring_tick_seconds"],
            value("Volcanic Gale", "damage_pct"), value("Volcanic Gale", "duration_seconds"),
            value("Sandstorm", "miss_chance_pct"), value("Sandstorm", "blind_duration_seconds")]


def run_harness(mutation=None):
    text = (SHAMAN / HEADER).read_text(encoding="utf-8")
    if mutation:
        old, new = mutation
        if text.count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        text = text.replace(old, new)
    binary = harness_env.build([MODULE / "tests/shaman_thunderstorm/harness.cpp"], flags=FLAGS,
                               files={"classes/shaman/" + HEADER: text,
                                      "combat/dc_periodic_strike.h": (MODULE / "src/combat/dc_periodic_strike.h").read_text(encoding="utf-8")},
                               includes=[MODULE / "src"])
    return harness_env.run([str(binary), *map(str, args())], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        ran = run_harness()
        self.assertEqual(ran.returncode, 0, ran.stdout[-1500:])
        print("\n  thunderstorm:", ran.stdout.strip())

    def test_planted_differences_are_caught(self):
        plants = [
            ("Gale Force not doubling", "hold.knockYards = knock * factor;", "hold.knockYards = knock;"),
            ("Gale Force without the stun", "                hold.stunSeconds = stun;\n", ""),
            ("Frost Storm without the freeze", "                hold.freezeSeconds = freeze;\n", ""),
            ("Frost Storm keeping the knockback", "            case Rune::FrostStorm:\n                hold.freezeSeconds = freeze;",
             "            case Rune::FrostStorm:\n                hold.knockYards = knock;\n                hold.freezeSeconds = freeze;"),
            ("Eye of the Storm keeping the knockback", "            case Rune::EyeOfTheStorm:\n                break;",
             "            case Rune::EyeOfTheStorm:\n                hold.knockYards = knock;\n                break;"),
            ("Sandstorm without the blind", "                hold.blind = true;\n", ""),
            ("an elite blinded", "return hold.blind && !elite;", "return hold.blind;"),
            ("the tick percent not scaled by the tick", "return perSecondPct * tickSeconds;", "return perSecondPct;"),
            ("the blind never ending", "            if (found->second.until <= now)\n", "            if (false)\n"),
            ("the blind of another enemy", "            auto found = held.find(enemy);\n            if (found == held.end())\n                return 0.0;",
             "            auto found = held.begin();\n            if (found == held.end())\n                return 0.0;"),
            ("the sweep never run", "            for (auto it = held.begin(); it != held.end();)\n                it = it->second.until <= now ? held.erase(it) : std::next(it);\n", ""),
            ("Volcanic Gale losing the knockback", "            case Rune::None:\n            case Rune::VolcanicGale:", "            case Rune::None:"),
        ]
        for label, old, new in plants:
            with self.subTest(label):
                ran = run_harness((old, new))
                self.assertNotEqual(ran.returncode, 0, f"{label} was not caught: {ran.stdout[-300:]}")


def source(path):
    return (MODULE / path).read_text(encoding="utf-8")


def wiring_problems(files):
    """What is wrong with Thunderstorm's wiring in `files` ({path: text}); [] when it is right."""
    problems = []
    needed = {
        "src/combat/dc_combat_resolve.cpp": ["Shaman::Cast(player, shell.spellId, targets);"],
        "src/combat/dc_combat.cpp": ["else if (auto shaman = Shaman::BasePct(ability.id))\n                            shell.damagePct = *shaman;"],
        "src/combat/dc_combat_hooks.cpp": ["Shaman::MissChance(attacker)"],
        "src/classes/shaman/dc_shaman.cpp": ["return Thunderstorm::BasePct(spellId);", "Thunderstorm::Cast(player, spellId, targets);",
                                              "return Thunderstorm::MissChance(attacker);"],
    }
    for path, lines in needed.items():
        for line in lines:
            if line not in files[path]:
                problems.append(f"{path} lacks {line}")
    cpp = files["src/classes/shaman/dc_shaman_thunderstorm.cpp"]
    for stretched in ('double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);',
                      'double const freeze = Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player);'):
        if stretched not in cpp:
            problems.append(f"a hold is not stretched by the stun powers: {stretched}")
    sheet = {(r["rune"], r["token"]) for r in read(MODULE / "data/d3/shaman_skill_values.csv") if r["skill"] == "Thunderstorm"}
    for token, rune in (("stun_duration_seconds", "Gale Force"), ("freeze_duration_seconds", "Frost Storm"),
                        ("blind_duration_seconds", "Sandstorm"), ("miss_chance_pct", "Sandstorm"), ("slow_pct", ""),
                        ("slow_duration_seconds", ""), ("duration_seconds", "Eye of the Storm"), ("damage_pct", "Eye of the Storm"),
                        ("radius_yards", "Eye of the Storm"), ("duration_seconds", "Volcanic Gale"), ("damage_pct", "Volcanic Gale"),
                        ("radius_yards", "")):
        if f'"{token}"' not in cpp:
            problems.append(f"the code does not read {token}")
        if (rune, token) not in sheet:
            problems.append(f"the sheet has no {token} for {rune or 'the skill'}")
    names = set(re.findall(r'Tunable\("([a-z_]+)"\)', cpp))
    numbers = combat()
    problems += [f"combat.csv has no {name}" for name in sorted(names) if name not in numbers]
    if len(names) < 4:
        problems.append("the code names fewer than four tunables")
    return problems


class Wiring(unittest.TestCase):
    PATHS = ["src/combat/dc_combat_resolve.cpp", "src/combat/dc_combat.cpp", "src/combat/dc_combat_hooks.cpp",
             "src/classes/shaman/dc_shaman.cpp", "src/classes/shaman/dc_shaman_thunderstorm.cpp"]

    def files(self):
        return {path: source(path) for path in self.PATHS}

    def test_the_wiring_is_whole(self):
        self.assertEqual(wiring_problems(self.files()), [])

    def test_a_planted_gap_is_caught(self):
        plants = [
            ("src/combat/dc_combat_resolve.cpp", "            Shaman::Cast(player, shell.spellId, targets);\n", ""),
            ("src/combat/dc_combat.cpp", "                        else if (auto shaman = Shaman::BasePct(ability.id))\n                            shell.damagePct = *shaman;\n", ""),
            ("src/combat/dc_combat_hooks.cpp", "Shaman::MissChance(attacker)", "0.0"),
            ("src/classes/shaman/dc_shaman.cpp", "return Thunderstorm::BasePct(spellId);", "return std::nullopt;"),
            ("src/classes/shaman/dc_shaman.cpp", "Thunderstorm::Cast(player, spellId, targets);", ""),
            ("src/classes/shaman/dc_shaman_thunderstorm.cpp", '"stun_duration_seconds"', '"stun_seconds"'),
            ("src/classes/shaman/dc_shaman_thunderstorm.cpp", 'double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);',
             'double const stun = Numbers::Num(spellId, "stun_duration_seconds");'),
            ("src/classes/shaman/dc_shaman_thunderstorm.cpp", 'double const freeze = Numbers::Num(spellId, "freeze_duration_seconds") * ItemPowers::StunFactor(player);',
             'double const freeze = Numbers::Num(spellId, "freeze_duration_seconds");'),
            ("src/classes/shaman/dc_shaman_thunderstorm.cpp", 'Tunable("thunderstorm_knockback_yards")', 'Tunable("thunderstorm_knock_yards")'),
        ]
        for path, old, new in plants:
            with self.subTest(old):
                files = self.files()
                self.assertIn(old, files[path])
                files[path] = files[path].replace(old, new)
                self.assertNotEqual(wiring_problems(files), [], f"{old!r} -> {new!r} was not caught")

    def test_the_tunables_are_in_the_newest_migration(self):
        names = set(re.findall(r'Tunable\("([a-z_]+)"\)', source("src/classes/shaman/dc_shaman_thunderstorm.cpp")))
        migration = (MODULE / "data/sql/db-world/updates" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        for name in sorted(names):
            self.assertIn(f"('combat', '{name}',", migration, name)

    def test_the_thunderclap_reaches_the_sheets_radius(self):
        row = [r for r in read(MODULE / "data/d3/skill_targeting.csv") if r["skill"] == "Thunderstorm"][0]
        self.assertEqual(row["target_type"], "self_aoe")
        self.assertEqual(row["radius_yards"], value("", "radius_yards"))
        self.assertEqual(value("Eye of the Storm", "radius_yards"), value("", "radius_yards"))


if __name__ == "__main__":
    unittest.main()
