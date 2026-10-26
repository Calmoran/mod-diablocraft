"""The Shaman's Spirit Wolves and its five runes (diablocraft-xnrvn.31).

What this proves, and how:

  * **The rules.** tests/shaman_spirit_wolves compiles the real src/classes/shaman/dc_shaman_spirit_wolves.h with no core and runs it
    over the sheet's numbers: each rune by its name and the one thing each adds; the skill's wolves run down one line and Spirit
    Pack's fan evenly across its cone; a wolf's lane touches an enemy ahead of the caster within half the lane's width and the
    range, and not one beside it, behind it or beyond it; the wave's time at its speed; an arc reaches the nearest enemies up to the
    sheet's count; the trail has a patch every spacing and a pulse is a second's percent of its seconds; the Pack's Maelstrom is paid
    per enemy and stops at the cap. Planted mutations (a lane that is too wide, a fan that is not even, an arc that is not the nearest,
    a rune that adds a part it does not own, a Maelstrom that passes the cap) must each make it fail.
  * **The wiring.** The class dispatches the cast and the hit's percent to SpiritWolves; the cast hits nothing (`BasePct` 0 on purpose:
    each wolf strikes as it passes with the base skill's `damage_pct`, a rune's own being the arc's or the trail's); the strike is an
    ordinary Combat::Strike under the cast's record, so the record's element and every on-hit rider apply; the freeze is stretched
    like every stun; the trail is ground devices of the rune's record; the lane's width is the targeting row's.
  * **The data.** The tunables are in combat.csv and the newest migration; the lane's width is skill_targeting.csv's.

What it does not prove: a wave on a running server (docs/test-diablocraft-xnrvn.31.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_spirit_wolves.py
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
HEADER = "dc_shaman_spirit_wolves.h"
FLAGS = ["-std=c++17", "-O1"]
SKILL = "Spirit Wolves"


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
    tunables = combat()
    return [value("", "projectile_count"), value("Spirit Pack", "projectile_count"), value("Spirit Pack", "cone_angle_degrees"),
            value("", "radius_yards"), tunables["spirit_wolves_lane_width_yards"], tunables["spirit_wolves_speed_yards_per_second"],
            tunables["spirit_wolves_trail_spacing_yards"], value("Fiery Wolves", "damage_pct"),
            tunables["spirit_wolves_trail_tick_seconds"], value("Spirit of the Pack", "gain_resource", "per_hit"),
            value("Spirit of the Pack", "gain_resource", "cap"), value("Lightning Wolves", "target_count")]


def run_harness(mutation=None):
    text = (SHAMAN / HEADER).read_text(encoding="utf-8")
    if mutation:
        old, new = mutation
        if text.count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        text = text.replace(old, new)
    binary = harness_env.build([MODULE / "tests/shaman_spirit_wolves/harness.cpp"], flags=FLAGS,
                               files={"classes/shaman/" + HEADER: text}, includes=[MODULE / "src"])
    return harness_env.run([str(binary), *map(str, args())], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        ran = run_harness()
        self.assertEqual(ran.returncode, 0, ran.stdout[-1500:])
        print("\n  spirit wolves:", ran.stdout.strip())

    def test_planted_differences_are_caught(self):
        plants = [
            ("a lane too wide", "std::abs(aside) <= halfWidth", "std::abs(aside) <= halfWidth * 4"),
            ("a lane too narrow", "std::abs(aside) <= halfWidth", "std::abs(aside) < halfWidth / 4"),
            ("a lane behind the caster", "ahead >= 0 && ahead", "ahead >= -50 && ahead"),
            ("a lane without an end", "ahead <= range && std::abs", "std::abs"),
            ("the lane not turned to its bearing", "double const aside = -dx * std::sin(bearing) + dy * std::cos(bearing);",
             "double const aside = dy;"),
            ("a fan not even", "-half + 2.0 * half * index / (wolves - 1)", "-half + half * index / (wolves - 1)"),
            ("a fan of one wolf fewer", "std::vector<double> angles(wolves, 0.0);", "std::vector<double> angles(wolves ? wolves - 1 : 0, 0.0);"),
            ("an arc to the farthest", "return distances[a] < distances[b];", "return distances[a] > distances[b];"),
            ("an arc with no count", "if (order.size() > count)\n            order.resize(count);", ""),
            ("Frost Wolves not freezing", "inline bool Freezes(Rune rune) { return rune == Rune::FrostWolves; }",
             "inline bool Freezes(Rune rune) { return false; }"),
            ("every rune arcing", "inline bool Arcs(Rune rune) { return rune == Rune::LightningWolves; }",
             "inline bool Arcs(Rune rune) { return rune != Rune::None; }"),
            ("the trail on the wrong rune", "inline bool LeavesTrail(Rune rune) { return rune == Rune::FieryWolves; }",
             "inline bool LeavesTrail(Rune rune) { return rune == Rune::FrostWolves; }"),
            ("the Pack not paying", "inline bool Pays(Rune rune) { return rune == Rune::SpiritOfThePack; }",
             "inline bool Pays(Rune rune) { return false; }"),
            ("Maelstrom past the cap", "return std::max(0.0, std::min(perHit, cap - gained));", "return perHit;"),
            ("a patch every yard", "std::floor(range / spacing + 1e-9)", "std::floor(range + 1e-9)"),
            ("a pulse the whole second", "return perSecondPct * tickSeconds;", "return perSecondPct;"),
            ("a wave with no time", "return speed > 0 && yards > 0 ? yards / speed : 0.0;", "return 0.0;"),
            ("a rune named wrongly", 'if (name == "Fiery Wolves")', 'if (name == "Fire Wolves")'),
        ]
        for label, old, new in plants:
            with self.subTest(label):
                ran = run_harness((old, new))
                self.assertNotEqual(ran.returncode, 0, f"{label} was not caught: {ran.stdout[-300:]}")


def source(path):
    return (MODULE / path).read_text(encoding="utf-8")


def squeeze(text):
    return re.sub(r"\s+", " ", text)


TOKENS = [("projectile_count", "", ""), ("radius_yards", "", ""), ("damage_pct", "", ""), ("cone_angle_degrees", "Spirit Pack", ""),
          ("target_count", "Lightning Wolves", ""), ("damage_pct", "Lightning Wolves", ""), ("damage_pct", "Fiery Wolves", ""),
          ("duration_seconds", "Fiery Wolves", ""), ("freeze_duration_seconds", "Frost Wolves", ""),
          ("gain_resource", "Spirit of the Pack", "per_hit"), ("gain_resource", "Spirit of the Pack", "cap")]


def wiring_problems(files):
    """What is wrong with Spirit Wolves' wiring in `files` ({path: text}); [] when it is right."""
    problems = []
    flat = squeeze(files["src/classes/shaman/dc_shaman.cpp"])
    for line in ("SpiritWolves::BasePct(spellId)", "SpiritWolves::Cast(player, spellId, targets);"):
        if line not in flat:
            problems.append(f"dc_shaman.cpp lacks {line}")
    cpp = squeeze(files["src/classes/shaman/dc_shaman_spirit_wolves.cpp"])
    sheet = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/d3/shaman_skill_values.csv") if r["skill"] == SKILL}
    for token, rune, qualifier in TOKENS:
        if f'"{token}"' not in cpp:
            problems.append(f"the code does not read {token}")
        if (rune, token, qualifier) not in sheet:
            problems.append(f"the sheet has no {token} for {rune or 'the skill'}")
    if "return RowOf(spellId) ? std::optional<double>(0.0) : std::nullopt;" not in cpp:
        problems.append("the cast has a hit of its own")
    if 'wave->hitPct = Numbers::Num(BaseId(), "damage_pct");' not in cpp:
        problems.append("a wolf's hit is not the base skill's percent")
    if "Combat::Strike(player, enemy, wave->spellId, wave->hitPct);" not in cpp:
        problems.append("a wolf does not strike under the cast's record")
    if 'Combat::Strike(player, near[index], wave->spellId, Numbers::Num(wave->spellId, "damage_pct"))' not in cpp:
        problems.append("an arc is not the rune's own percent")
    if "for (unsigned wolf = 0; wolf < hits && enemy->IsAlive(); ++wolf)" not in cpp:
        problems.append("an enemy is not hit once by each wolf that touches it")
    if "* ItemPowers::StunFactor(player)" not in cpp:
        problems.append("the freeze is not stretched by the stun powers")
    if "Pay(wave->gained," not in cpp or "wave->gained += pay;" not in cpp:
        problems.append("the Maelstrom is not capped per cast")
    if "rune == Rune::SpiritPack ? Numbers::Num(spellId, \"cone_angle_degrees\") : 0.0" not in cpp:
        problems.append("a cone on a cast that is not the Pack")
    if "GroundDevice::Place(player, patch, at);" not in cpp or "GroundDevice::Mode::Periodic" not in cpp:
        problems.append("the trail is not periodic ground patches")
    if "Combat::Strike(owner, enemy, spellId, pct, true);" not in cpp:
        problems.append("a patch's pulse is not a periodic strike")
    if "Combat::ModifiedDurationSeconds(player, spellId," not in cpp:
        problems.append("the trail's seconds ignore the worn powers")
    if "AddEventAtOffset" not in cpp or "Seconds(nearest, speed)" not in cpp:
        problems.append("the wave does not take time to arrive")
    for name in ("spirit_wolves_arc_radius_yards", "spirit_wolves_lane_width_yards", "spirit_wolves_speed_yards_per_second",
                 "spirit_wolves_trail_spacing_yards", "spirit_wolves_trail_radius_yards", "spirit_wolves_trail_tick_seconds",
                 "spirit_wolves_trail_most"):
        if f'Tunable("{name}")' not in cpp:
            problems.append(f"the code does not read {name}")
    names = set(re.findall(r'Tunable\("([a-z_]+)"\)', cpp))
    numbers = combat()
    problems += [f"combat.csv has no {name}" for name in sorted(names) if name not in numbers]
    if not names:
        problems.append("the code names no tunable")
    return problems


class Wiring(unittest.TestCase):
    PATHS = ["src/classes/shaman/dc_shaman.cpp", "src/classes/shaman/dc_shaman_spirit_wolves.cpp"]

    def files(self):
        return {path: source(path) for path in self.PATHS}

    def test_the_wiring_is_whole(self):
        self.assertEqual(wiring_problems(self.files()), [])

    def test_a_planted_gap_is_caught(self):
        plants = [
            ("src/classes/shaman/dc_shaman.cpp", "SpiritWolves::BasePct(spellId)", "SpiritWolves::Nothing(spellId)"),
            ("src/classes/shaman/dc_shaman.cpp", "SpiritWolves::Cast(player, spellId, targets);", ""),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", '"cone_angle_degrees"', '"cone_angle"'),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", '"freeze_duration_seconds"', '"freeze_seconds"'),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", "std::optional<double>(0.0)", "std::optional<double>(900.0)"),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", 'wave->hitPct = Numbers::Num(BaseId(), "damage_pct");',
             'wave->hitPct = Numbers::Num(spellId, "damage_pct");'),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", "Combat::Strike(player, enemy, wave->spellId, wave->hitPct);",
             "Combat::Strike(player, enemy, BaseId(), wave->hitPct);"),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", "wolf < hits &&", "wolf < 1 &&"),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", " * ItemPowers::StunFactor(player)", ""),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", "wave->gained += pay;", ""),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", 'rune == Rune::SpiritPack ? Numbers::Num(spellId, "cone_angle_degrees") : 0.0',
             'Numbers::Num(spellId, "cone_angle_degrees")'),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", "GroundDevice::Place(player, patch, at);", ""),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", "Combat::Strike(owner, enemy, spellId, pct, true);",
             "Combat::Strike(owner, enemy, spellId, pct);"),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", "Combat::ModifiedDurationSeconds(player, spellId,", "Combat::Nothing(player, spellId,"),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", "Seconds(nearest, speed)", "0"),
            ("src/classes/shaman/dc_shaman_spirit_wolves.cpp", 'Tunable("spirit_wolves_arc_radius_yards")', "10.0"),
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
    def test_the_tunables_are_in_the_newest_migration(self):
        migration = (MODULE / "data/sql/db-world/updates" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        for name in ("spirit_wolves_speed_yards_per_second", "spirit_wolves_lane_width_yards", "spirit_wolves_arc_radius_yards",
                     "spirit_wolves_trail_spacing_yards", "spirit_wolves_trail_radius_yards", "spirit_wolves_trail_tick_seconds",
                     "spirit_wolves_trail_most"):
            self.assertIn(f"('combat', '{name}',", migration)

    def test_the_lane_is_the_targeting_rows_line(self):
        rows = {r["skill"]: r for r in read(MODULE / "data/d3/skill_targeting.csv")}
        row = rows[SKILL]
        self.assertEqual(row["target_type"], "line_pierce")
        self.assertEqual(float(row["width_yards"]), float(combat()["spirit_wolves_lane_width_yards"]))
        self.assertEqual(float(row["range_yards"]), float(value("", "radius_yards")))

    def test_the_trail_patches_cover_the_lane(self):
        tunables = combat()
        self.assertGreaterEqual(2 * float(tunables["spirit_wolves_trail_radius_yards"]), float(tunables["spirit_wolves_lane_width_yards"]))
        self.assertGreaterEqual(2 * float(tunables["spirit_wolves_trail_radius_yards"]), float(tunables["spirit_wolves_trail_spacing_yards"]))

    def test_the_cast_has_no_hit_of_its_own_on_purpose(self):
        self.assertNotIn('"Spirit Wolves":', source("scripts/tests/classes/test_shaman_hits.py").split("SKILLS =")[1].split("\n")[0])


if __name__ == "__main__":
    unittest.main()
