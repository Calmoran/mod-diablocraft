"""The Shaman's Purge and its five runes (diablocraft-xnrvn.19).

What this proves, and how:

  * **The rules.** tests/shaman_purge compiles the real src/classes/shaman/dc_shaman_purge.h with no core and runs it over the sheet's
    numbers: each rune by its name; Wind Shear interrupts every enemy and stuns what is not a boss; Greater Purge weakens a purged
    elite and nothing else; Consuming Purge burns an enemy that lost an effect and no other; the skill and the Cleanse and Earthen
    runes add nothing to an enemy; each removal pays the sheet's Maelstrom; the burn's ticks fit its seconds. Planted mutations
    (a boss stunned, Greater Purge on an ordinary enemy or on one nothing came off, the burn on every enemy, the Maelstrom not scaled by
    the removals) must each make it fail.
  * **The elite side.** `Rifts::PurgeEmpowered` is declared in the public rifts header and takes off each of the four states the
    brief names (Shielding's window, Reflects Damage's reflecting window, the Juggernaut's immunities for good, the Illusionist's copies);
    the Juggernaut passive honours the purge; the affix files, which hold the states, are the ones that change them.
  * **The wiring.** The engine tells the class of the aim before any hit lands (Shaman::Aim after Monk::Aim and before the hit loop),
    of the landing (Shaman::Cast), asks it for the cast's own hit (Shaman::BasePct); the class dispatches to Purge; every sheet token the
    code reads is a row of the rune it is read for; the stun is stretched like every other class's; Earthen Purge's cone is a targeting
    row of its own. Planted: each call gone, a token renamed, a removal gone.

What it does not prove: anything on a running server (docs/test-diablocraft-xnrvn.19.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_purge.py
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
HEADER = "dc_shaman_purge.h"
FLAGS = ["-std=c++17", "-O1"]
SKILL = "Purge"


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
    return [value("", "gain_resource"), value("Consuming Purge", "dot_duration_seconds"), combat()["purge_burn_tick_seconds"]]


def run_harness(mutation=None):
    text = (SHAMAN / HEADER).read_text(encoding="utf-8")
    if mutation:
        old, new = mutation
        if text.count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        text = text.replace(old, new)
    binary = harness_env.build([MODULE / "tests/shaman_purge/harness.cpp"], flags=FLAGS,
                               files={"classes/shaman/" + HEADER: text}, includes=[MODULE / "src"])
    return harness_env.run([str(binary), *map(str, args())], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        ran = run_harness()
        self.assertEqual(ran.returncode, 0, ran.stdout[-1500:])
        print("\n  purge:", ran.stdout.strip())

    def test_planted_differences_are_caught(self):
        plants = [
            ("a boss stunned", "effect.stun = !boss;", "effect.stun = true;"),
            ("no stun for an ordinary enemy", "effect.stun = !boss;", "effect.stun = false;"),
            ("no interrupt", "                effect.interrupt = true;\n", ""),
            ("Greater Purge on an ordinary enemy", "effect.weaken = removed > 0 && elite;", "effect.weaken = removed > 0;"),
            ("Greater Purge on an enemy nothing came off", "effect.weaken = removed > 0 && elite;", "effect.weaken = elite;"),
            ("the burn on every enemy", "effect.burn = removed > 0;", "effect.burn = true;"),
            ("the burn never", "effect.burn = removed > 0;", "effect.burn = false;"),
            ("the Maelstrom not scaled by the removals", "return removed * perEffect;", "return removed ? perEffect : 0.0;"),
            ("Greater Purge's hit not kept", "return rune == Rune::ConsumingPurge || rune == Rune::GreaterPurge;", "return rune == Rune::ConsumingPurge;"),
            ("every record claimed", "return rune == Rune::ConsumingPurge || rune == Rune::GreaterPurge;", "return rune != Rune::None;"),
            ("the burn's ticks lost", "static_cast<unsigned>(seconds / tickSeconds + 1e-9)", "0u"),
            ("a rune named wrongly", 'if (name == "Cleanse Spirit")', 'if (name == "Cleansing Spirit")'),
        ]
        for label, old, new in plants:
            with self.subTest(label):
                ran = run_harness((old, new))
                self.assertNotEqual(ran.returncode, 0, f"{label} was not caught: {ran.stdout[-300:]}")


def source(path):
    return (MODULE / path).read_text(encoding="utf-8")


TOKENS = [("gain_resource", "", ""), ("damage_pct", "", ""), ("stun_duration_seconds", "Wind Shear", ""),
          ("enemy_damage_pct", "Greater Purge", ""), ("duration_seconds", "Greater Purge", ""), ("damage_pct", "Consuming Purge", ""),
          ("dot_duration_seconds", "Consuming Purge", "")]
REMOVALS = ["pack->shieldUntil = 0;", "SetShieldImmunity(creature, state, false);", "pack->reflectUntil = now;",
            "state->juggernautPurged = true;", "SetJuggernautImmunities(creature, false);", "copy->DespawnOrUnsummon();"]


def wiring_problems(files):
    """What is wrong with Purge's wiring in `files` ({path: text}); [] when it is right."""
    problems = []
    needed = {
        "src/combat/dc_combat_resolve.cpp": ["Shaman::Aim(player, shell.spellId, targets);"],
        "src/classes/shaman/dc_shaman.cpp": ["Purge::Aim(player, spellId, targets);", "Purge::Cast(player, spellId, targets);",
                                              "Purge::BasePct(spellId)", "Purge::Forget(player);"],
        "src/rifts/dc_rifts.h": ["unsigned PurgeEmpowered(Creature* creature);"],
        "src/monsters/affixes/dc_affix_juggernaut.cpp": ["&& !state.juggernautPurged)", "void SetJuggernautImmunities(Creature* elite, bool on)"],
    }
    for path, lines in needed.items():
        for line in lines:
            if line not in files[path]:
                problems.append(f"{path} lacks {line}")
    resolve = files["src/combat/dc_combat_resolve.cpp"]
    if "Shaman::Aim(" in resolve and resolve.index("Shaman::Aim(") > resolve.index("connected += ResolveHit(player, target, punch.pct"):
        problems.append("the aim comes after the hits")
    affix = files["src/monsters/affixes/dc_affix_purge.cpp"]
    for removal in REMOVALS:
        if removal not in affix:
            problems.append(f"the elite side does not remove: {removal}")
    for behaviour in ("shielding", "reflects_damage", "juggernaut", "illusionist"):
        if f'HasAffix(*state, "{behaviour}")' not in affix:
            problems.append(f"the elite side does not look for the {behaviour} affix")
    cpp = files["src/classes/shaman/dc_shaman_purge.cpp"]
    sheet = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/d3/shaman_skill_values.csv") if r["skill"] == SKILL}
    for token, rune, qualifier in TOKENS:
        if f'"{token}"' not in cpp:
            problems.append(f"the code does not read {token}")
        if (rune, token, qualifier) not in sheet:
            problems.append(f"the sheet has no {token} for {rune or 'the skill'}")
    if 'double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);' not in cpp:
        problems.append("the stun is not stretched by the stun powers")
    if "DC::Rifts::PurgeEmpowered(" not in cpp:
        problems.append("the class does not ask the elite side")
    names = set(re.findall(r'Tunable\("([a-z_]+)"\)', cpp))
    numbers = combat()
    problems += [f"combat.csv has no {name}" for name in sorted(names) if name not in numbers]
    if not names:
        problems.append("the code names no tunable")
    return problems


class Wiring(unittest.TestCase):
    PATHS = ["src/combat/dc_combat_resolve.cpp", "src/classes/shaman/dc_shaman.cpp", "src/rifts/dc_rifts.h",
             "src/monsters/affixes/dc_affix_juggernaut.cpp", "src/monsters/affixes/dc_affix_purge.cpp", "src/classes/shaman/dc_shaman_purge.cpp"]

    def files(self):
        return {path: source(path) for path in self.PATHS}

    def test_the_wiring_is_whole(self):
        self.assertEqual(wiring_problems(self.files()), [])

    def test_a_planted_gap_is_caught(self):
        plants = [
            ("src/combat/dc_combat_resolve.cpp", "            Shaman::Aim(player, shell.spellId, targets);\n", ""),
            ("src/classes/shaman/dc_shaman.cpp", "Purge::Aim(player, spellId, targets);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "Purge::Cast(player, spellId, targets);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "Purge::Forget(player);", ""),
            ("src/rifts/dc_rifts.h", "unsigned PurgeEmpowered(Creature* creature);", ""),
            ("src/monsters/affixes/dc_affix_juggernaut.cpp", "&& !state.juggernautPurged)", ")"),
            ("src/monsters/affixes/dc_affix_purge.cpp", "pack->shieldUntil = 0;", ""),
            ("src/monsters/affixes/dc_affix_purge.cpp", "pack->reflectUntil = now;", ""),
            ("src/monsters/affixes/dc_affix_purge.cpp", "SetJuggernautImmunities(creature, false);", ""),
            ("src/monsters/affixes/dc_affix_purge.cpp", "copy->DespawnOrUnsummon();", ""),
            ("src/monsters/affixes/dc_affix_purge.cpp", 'HasAffix(*state, "illusionist")', 'HasAffix(*state, "illusion")'),
            ("src/classes/shaman/dc_shaman_purge.cpp", '"enemy_damage_pct"', '"damage_pct_less"'),
            ("src/classes/shaman/dc_shaman_purge.cpp", 'double const stun = Numbers::Num(spellId, "stun_duration_seconds") * ItemPowers::StunFactor(player);',
             'double const stun = Numbers::Num(spellId, "stun_duration_seconds");'),
            ("src/classes/shaman/dc_shaman_purge.cpp", "DC::Rifts::PurgeEmpowered(", "Count("),
        ]
        for path, old, new in plants:
            with self.subTest(old):
                files = self.files()
                self.assertIn(old, files[path])
                files[path] = files[path].replace(old, new)
                self.assertNotEqual(wiring_problems(files), [], f"{old!r} -> {new!r} was not caught")

    def test_the_aim_precedes_the_hits_in_the_real_engine(self):
        resolve = source("src/combat/dc_combat_resolve.cpp")
        self.assertLess(resolve.index("Shaman::Aim("), resolve.index("connected += ResolveHit(player, target, punch.pct"))
        self.assertLess(resolve.index("Monk::Aim("), resolve.index("Shaman::Aim("))

    def test_the_tunable_is_in_the_newest_migration(self):
        migration = (MODULE / "data/sql/db-world/updates" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        self.assertIn("('combat', 'purge_burn_tick_seconds',", migration)

    def test_the_skill_is_single_target_and_earthen_purge_is_a_cone_of_the_sheets_radius(self):
        rows = {r["skill"]: r for r in read(MODULE / "data/d3/skill_targeting.csv")}
        self.assertEqual(rows["Purge"]["target_type"], "single_enemy")
        self.assertEqual(rows["Purge - Earthen Purge"]["target_type"], "cone_enemies")
        self.assertEqual(rows["Purge - Earthen Purge"]["range_yards"], value("Earthen Purge", "radius_yards"))

    def test_consuming_purge_keeps_the_skills_hit(self):
        code = source("src/classes/shaman/dc_shaman_purge.cpp")
        self.assertIn('return Numbers::Num(BaseId(), "damage_pct");', code)
        self.assertNotEqual(value("Consuming Purge", "damage_pct"), value("", "damage_pct"))


if __name__ == "__main__":
    unittest.main()
