"""The Shaman's Ghost Wolf and its five runes (diablocraft-xnrvn.18).

What this proves, and how:

  * **The rules.** tests/shaman_ghost_wolf compiles the real src/classes/shaman/dc_shaman_ghost_wolf.h with no core and runs it
    over the sheet's numbers: each rune by its name; the form lasts the skill's seconds and only Spirit Walk its own; each rune's
    part (control stripped, a heal, an explosion, a trail) is its own and no other's; the trail lays a patch every drop for the
    form's seconds and pulses the per-second percent of a pulse; the heal is a share of the maximum Life; another skill's cast
    ends the form and Ghost Wolf's own does not; Wind Rush stores the sheet's charges, one recharging at a time, and the button is
    held only when none is left. Planted mutations (Spirit Walk's seconds on every rune, a part on the wrong rune, the pulse not
    scaled, a cast of Ghost Wolf ending its own form, the heal off the maximum) must each make it fail.
  * **The wiring.** The class dispatches Ghost Wolf's cast (Casting, Cast, BasePct), its upkeep and logout; the cast ends the form
    for any other skill; every sheet token the code reads is a row of the rune it is read for; every tunable it names is a row
    of combat.csv and of the newest tunables migration; the shared control immunity piece has the Strip the rune calls. Planted:
    each call gone, a token renamed, a tunable renamed.

What it does not prove: anything on a running server (docs/test-diablocraft-xnrvn.18.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_ghost_wolf.py
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
HEADER = "dc_shaman_ghost_wolf.h"
FLAGS = ["-std=c++17", "-O1"]
SKILL = "Ghost Wolf"


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
    numbers = combat()
    return [value("", "duration_seconds"), value("Spirit Walk", "duration_seconds"), value("Wind Rush", "charge_count"),
            value("Wind Rush", "charge_recharge_seconds"), value("Spectral Recovery", "heal_pct"),
            value("Thunderous Paws", "damage_pct"), numbers["ghost_wolf_trail_tick_seconds"], numbers["ghost_wolf_trail_drop_seconds"]]


def run_harness(mutation=None):
    text = (SHAMAN / HEADER).read_text(encoding="utf-8")
    if mutation:
        old, new = mutation
        if text.count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        text = text.replace(old, new)
    binary = harness_env.build([MODULE / "tests/shaman_ghost_wolf/harness.cpp"], flags=FLAGS,
                               files={"classes/shaman/" + HEADER: text,
                                      "combat/dc_charge_store.h": (MODULE / "src/combat/dc_charge_store.h").read_text(encoding="utf-8")},
                               includes=[MODULE / "src"])
    return harness_env.run([str(binary), *map(str, args())], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        ran = run_harness()
        self.assertEqual(ran.returncode, 0, ran.stdout[-1500:])
        print("\n  ghost wolf:", ran.stdout.strip())

    def test_planted_differences_are_caught(self):
        plants = [
            ("Spirit Walk's seconds on every rune", "return rune == Rune::SpiritWalk ? own : skill;", "return own;"),
            ("Spirit Walk not lasting longer", "return rune == Rune::SpiritWalk ? own : skill;", "return skill;"),
            ("control stripped by every rune", "return rune == Rune::SpiritWalk;\n    }\n    inline bool HealsAtEnd",
             "return rune != Rune::None;\n    }\n    inline bool HealsAtEnd"),
            ("the heal on Blazing Spirit", "return rune == Rune::SpectralRecovery;", "return rune == Rune::BlazingSpirit;"),
            ("the explosion on Spectral Recovery", "return rune == Rune::BlazingSpirit;\n    }\n    inline bool LaysTrail",
             "return rune == Rune::SpectralRecovery;\n    }\n    inline bool LaysTrail"),
            ("the trail on every rune", "return rune == Rune::ThunderousPaws;\n    }\n\n    // The patches",
             "return rune != Rune::None;\n    }\n\n    // The patches"),
            ("the pulse not scaled", "return perSecondPct * tickSeconds;", "return perSecondPct;"),
            ("no patch for the form", "std::floor(formSeconds / dropSeconds + 1e-9)", "std::floor(formSeconds / dropSeconds + 5.0)"),
            ("the heal off the wrong base", "return maxLife * pct / 100.0;", "return pct / 100.0;"),
            ("Ghost Wolf ending its own form", "return formStands && !castIsGhostWolf;", "return formStands;"),
            ("another skill not ending the form", "return formStands && !castIsGhostWolf;", "return false;"),
            ("a rune named wrongly", 'if (name == "Wind Rush")', 'if (name == "Windrush")'),
        ]
        for label, old, new in plants:
            with self.subTest(label):
                ran = run_harness((old, new))
                self.assertNotEqual(ran.returncode, 0, f"{label} was not caught: {ran.stdout[-300:]}")


def source(path):
    return (MODULE / path).read_text(encoding="utf-8")


TOKENS = [("duration_seconds", "", ""), ("duration_seconds", "Spirit Walk", ""), ("movement_speed_pct", "", ""),
          ("charge_count", "Wind Rush", ""), ("charge_recharge_seconds", "Wind Rush", ""), ("damage_pct", "Thunderous Paws", ""),
          ("heal_pct", "Spectral Recovery", ""), ("damage_pct", "Blazing Spirit", ""), ("radius_yards", "Blazing Spirit", "")]


def wiring_problems(files):
    """What is wrong with Ghost Wolf's wiring in `files` ({path: text}); [] when it is right."""
    problems = []
    needed = {
        "src/classes/shaman/dc_shaman.cpp": ["GhostWolf::Casting(player, spellId);", "GhostWolf::Cast(player, spellId);",
                                              "GhostWolf::BasePct(spellId)", "GhostWolf::Upkeep(player);", "GhostWolf::Forget(player);"],
        "src/combat/dc_control_immunity.h": ["void Strip(Player* player);"],
        "src/combat/dc_control_immunity.cpp": ["player->RemoveAurasWithMechanic(ControlImpairing);"],
    }
    for path, lines in needed.items():
        for line in lines:
            if line not in files[path]:
                problems.append(f"{path} lacks {line}")
    cpp = files["src/classes/shaman/dc_shaman_ghost_wolf.cpp"]
    if "ControlImmunity::Strip(player);" not in cpp:
        problems.append("Spirit Walk does not strip control")
    if "constexpr std::uint32_t FormAura = 2645;" not in cpp:
        problems.append("the form is not the stock Ghost Wolf aura")
    sheet = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/d3/shaman_skill_values.csv") if r["skill"] == SKILL}
    for token, rune, qualifier in TOKENS:
        if f'"{token}"' not in cpp:
            problems.append(f"the code does not read {token}")
        if (rune, token, qualifier) not in sheet:
            problems.append(f"the sheet has no {token} for {rune or 'the skill'}")
    names = set(re.findall(r'Tunable\("([a-z_]+)"\)', cpp))
    numbers = combat()
    problems += [f"combat.csv has no {name}" for name in sorted(names) if name not in numbers]
    if len(names) < 4:
        problems.append("the code names fewer than four tunables")
    return problems


class Wiring(unittest.TestCase):
    PATHS = ["src/classes/shaman/dc_shaman.cpp", "src/classes/shaman/dc_shaman_ghost_wolf.cpp", "src/combat/dc_control_immunity.h",
             "src/combat/dc_control_immunity.cpp"]

    def files(self):
        return {path: source(path) for path in self.PATHS}

    def test_the_wiring_is_whole(self):
        self.assertEqual(wiring_problems(self.files()), [])

    def test_a_planted_gap_is_caught(self):
        plants = [
            ("src/classes/shaman/dc_shaman.cpp", "GhostWolf::Casting(player, spellId);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "GhostWolf::Cast(player, spellId);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "GhostWolf::Upkeep(player);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "GhostWolf::Forget(player);", ""),
            ("src/combat/dc_control_immunity.cpp", "player->RemoveAurasWithMechanic(ControlImpairing);", ""),
            ("src/classes/shaman/dc_shaman_ghost_wolf.cpp", "ControlImmunity::Strip(player);", ""),
            ("src/classes/shaman/dc_shaman_ghost_wolf.cpp", '"charge_recharge_seconds"', '"recharge_seconds"'),
            ("src/classes/shaman/dc_shaman_ghost_wolf.cpp", 'Tunable("ghost_wolf_trail_radius_yards")', 'Tunable("ghost_wolf_radius")'),
            ("src/classes/shaman/dc_shaman_ghost_wolf.cpp", "FormAura = 2645", "FormAura = 2646"),
        ]
        for path, old, new in plants:
            with self.subTest(old):
                files = self.files()
                self.assertIn(old, files[path])
                files[path] = files[path].replace(old, new)
                self.assertNotEqual(wiring_problems(files), [], f"{old!r} -> {new!r} was not caught")

    def test_the_tunables_are_in_the_newest_migration(self):
        names = set(re.findall(r'Tunable\("([a-z_]+)"\)', source("src/classes/shaman/dc_shaman_ghost_wolf.cpp")))
        migration = (MODULE / "data/sql/db-world/updates" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        for name in sorted(names):
            self.assertIn(f"('combat', '{name}',", migration, name)

    def test_the_skill_is_a_self_cast_with_no_hit_of_its_own(self):
        row = [r for r in read(MODULE / "data/d3/skill_targeting.csv") if r["skill"] == SKILL][0]
        self.assertEqual(row["target_type"], "self")
        self.assertIn("return RowOf(spellId) ? std::optional<double>(0.0) : std::nullopt;", source("src/classes/shaman/dc_shaman_ghost_wolf.cpp"))


if __name__ == "__main__":
    unittest.main()
