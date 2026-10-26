"""The Shaman's Spirit Link and its five runes (diablocraft-xnrvn.29).

What this proves, and how:

  * **The rules.** tests/shaman_spirit_link compiles the real src/classes/shaman/dc_shaman_spirit_link.h with no core and runs it over the
    sheet's numbers: each rune by its name; a cast links the target first and then the nearest, the skill's count (Ancestral Chains'
    more); the share an ordinary enemy takes, the smaller one an elite or a boss takes, Thunder Link's larger share; a share is never
    shared again and the link's own damage is not shared; Spirit Harvest's extension grows by its seconds per death and stops at its
    cap; the link's tick is the second's percent in ticks of the aura's or the burn's seconds. Planted mutations (the target not first,
    no cap, the elite share missing, a share shared again, the link's damage shared, no cap on the extension, a tick that is not scaled)
    must each make it fail.
  * **The wiring.** The damage event (Combat::DealHit, after the hit is dealt) tells the class (Shaman::Dealt); the class dispatches
    to SpiritLink for the cast, the hit's percent, the damage, the upkeep and the logout; every sheet token the code reads is a row of
    the rune it is read for; the echo is a fixed hit dealt through DealHit under the link's own record with a guard against being shared
    again; the elite share is a tunable. Planted: each call gone, a token renamed, the guard gone.
  * **The tunables.** The three rows are in combat.csv and the newest migration.

What it does not prove: a link, a share or a death on a running server (docs/test-diablocraft-xnrvn.29.md).

    python mod-diablocraft/scripts/tests/classes/test_shaman_spirit_link.py
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
HEADER = "dc_shaman_spirit_link.h"
FLAGS = ["-std=c++17", "-O1"]
SKILL = "Spirit Link"


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
    return [value("", "target_count"), value("Ancestral Chains", "target_count"), value("", "damage_share_pct"),
            value("Thunder Link", "damage_share_pct", "new"), tunables["spirit_link_elite_share_pct"],
            value("Spirit Harvest", "duration_seconds", "extend"), value("Spirit Harvest", "duration_seconds", "cap"),
            value("", "damage_pct"), tunables["spirit_link_tick_seconds"], tunables["spirit_link_burn_tick_seconds"]]


def run_harness(mutation=None):
    text = (SHAMAN / HEADER).read_text(encoding="utf-8")
    if mutation:
        old, new = mutation
        if text.count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {HEADER}")
        text = text.replace(old, new)
    binary = harness_env.build([MODULE / "tests/shaman_spirit_link/harness.cpp"], flags=FLAGS,
                               files={"classes/shaman/" + HEADER: text}, includes=[MODULE / "src"])
    return harness_env.run([str(binary), *map(str, args())], capture_output=True, text=True)


class Rules(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        ran = run_harness()
        self.assertEqual(ran.returncode, 0, ran.stdout[-1500:])
        print("\n  spirit link:", ran.stdout.strip())

    def test_planted_differences_are_caught(self):
        plants = [
            ("the nearest not first", "return distances[a] < distances[b];", "return distances[a] > distances[b];"),
            ("no cap on the count", "if (order.size() > cap)\n            order.resize(cap);", ""),
            ("the elite share missing", "(elite ? elitePct / 100.0 : 1.0)", "1.0"),
            ("the elite share on everyone", "(elite ? elitePct / 100.0 : 1.0)", "(elitePct / 100.0)"),
            ("Thunder Link has the skill's share", "rune == Rune::ThunderLink ? thunder : skill", "skill"),
            ("a share is shared again", "return !echoing && !linksOwnDamage;", "return !linksOwnDamage;"),
            ("the link's damage is shared", "return !echoing && !linksOwnDamage;", "return !echoing;"),
            ("no cap on the extension", "return std::min(cap, extra + perDeath);", "return extra + perDeath;"),
            ("a death adds nothing", "return std::min(cap, extra + perDeath);", "return extra;"),
            ("a tick is the whole second", "return perSecondPct * tickSeconds;", "return perSecondPct;"),
            ("Searing Link pulses as an aura", "return rune == Rune::SearingLink ? burn : aura;", "return aura;"),
            ("a rune named wrongly", 'if (name == "Frozen Link")', 'if (name == "Freezing Link")'),
            ("damage of nothing shared", "if (damage <= 0 || sharePct <= 0)\n            return 0.0;", ""),
        ]
        for label, old, new in plants:
            with self.subTest(label):
                ran = run_harness((old, new))
                self.assertNotEqual(ran.returncode, 0, f"{label} was not caught: {ran.stdout[-300:]}")


def source(path):
    return (MODULE / path).read_text(encoding="utf-8")


def squeeze(text):
    return re.sub(r"\s+", " ", text)


TOKENS = [("target_count", "", ""), ("radius_yards", "", ""), ("duration_seconds", "", ""), ("damage_share_pct", "", ""),
          ("damage_pct", "", ""), ("damage_share_pct", "Thunder Link", "new"), ("chill_pct", "Frozen Link", ""),
          ("freeze_duration_seconds", "Frozen Link", ""), ("gain_resource", "Spirit Harvest", ""),
          ("duration_seconds", "Spirit Harvest", "extend"), ("duration_seconds", "Spirit Harvest", "cap"),
          ("damage_pct", "Searing Link", "")]


def wiring_problems(files):
    """What is wrong with Spirit Link's wiring in `files` ({path: text}); [] when it is right."""
    problems = []
    needed = {
        "src/combat/dc_combat.cpp": ["Shaman::Dealt(player, target, spellId, hit.school, hit.critical, adjusted);"],
        "src/classes/shaman/dc_shaman.h": ["void Dealt(Player* player, Unit* target, std::uint32_t spellId, unsigned school, bool critical, double damage);"],
        "src/classes/shaman/dc_shaman.cpp": ["SpiritLink::BasePct(spellId)", "SpiritLink::Cast(player, spellId, targets);",
                                              "SpiritLink::Dealt(player, target, spellId, school, critical, damage);",
                                              "SpiritLink::Upkeep(player);", "SpiritLink::Forget(player);"],
    }
    for path, lines in needed.items():
        for line in lines:
            if line not in files[path]:
                problems.append(f"{path} lacks {line}")
    combat_text = files["src/combat/dc_combat.cpp"]
    if "Shaman::Dealt(" in combat_text and combat_text.index("Shaman::Dealt(") < combat_text.index("player->DealSpellDamage(&log, true);"):
        problems.append("the share is told before the hit is dealt")
    cpp = squeeze(files["src/classes/shaman/dc_shaman_spirit_link.cpp"])
    sheet = {(r["rune"], r["token"], r["qualifier"]) for r in read(MODULE / "data/d3/shaman_skill_values.csv") if r["skill"] == SKILL}
    for token, rune, qualifier in TOKENS:
        if f'"{token}"' not in cpp:
            problems.append(f"the code does not read {token}")
        if (rune, token, qualifier) not in sheet:
            problems.append(f"the sheet has no {token} for {rune or 'the skill'}")
    if "thread_local bool echoing = false;" not in cpp:
        problems.append("no echo guard")
    if "if (!IsShaman(player) || !target || echoing) return;" not in cpp:
        problems.append("a share can be shared again")
    if "echoing = true;" not in cpp or "echoing = false; }" not in cpp:
        problems.append("the guard is never set or never cleared")
    if "Combat::DealHit(player, enemy, linkId, echo, true);" not in cpp:
        problems.append("the share is not a fixed hit under the link's record")
    if "Shares(echoing, RowOf(spellId) != nullptr)" not in cpp:
        problems.append("the link's own damage can be shared")
    if 'Tunable("spirit_link_elite_share_pct")' not in cpp:
        problems.append("the elite share is not the tunable")
    if "Shaman::IsElite(enemy)" not in cpp:
        problems.append("the elite is not asked")
    if "Combat::ModifiedDurationSeconds(player, spellId," not in cpp:
        problems.append("the duration ignores the worn powers")
    if "Combat::Strike(player, enemy, spellId, pct, true);" not in cpp:
        problems.append("the link's damage is not a periodic strike")
    if 'return RowOf(spellId) ? std::optional<double>(0.0) : std::nullopt;' not in cpp:
        problems.append("the cast has a hit of its own")
    names = set(re.findall(r'Tunable\("([a-z_]+)"\)', cpp))
    numbers = combat()
    problems += [f"combat.csv has no {name}" for name in sorted(names) if name not in numbers]
    if not names:
        problems.append("the code names no tunable")
    return problems


class Wiring(unittest.TestCase):
    PATHS = ["src/combat/dc_combat.cpp", "src/classes/shaman/dc_shaman.h", "src/classes/shaman/dc_shaman.cpp",
             "src/classes/shaman/dc_shaman_spirit_link.cpp"]

    def files(self):
        return {path: source(path) for path in self.PATHS}

    def test_the_wiring_is_whole(self):
        self.assertEqual(wiring_problems(self.files()), [])

    def test_a_planted_gap_is_caught(self):
        plants = [
            ("src/combat/dc_combat.cpp", "Shaman::Dealt(player, target, spellId, hit.school, hit.critical, adjusted);", ""),
            ("src/classes/shaman/dc_shaman.h", "void Dealt(Player* player, Unit* target, std::uint32_t spellId, unsigned school, bool critical, double damage);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "SpiritLink::BasePct(spellId)", "SpiritLink::Nothing(spellId)"),
            ("src/classes/shaman/dc_shaman.cpp", "SpiritLink::Cast(player, spellId, targets);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "SpiritLink::Dealt(player, target, spellId, school, critical, damage);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "SpiritLink::Upkeep(player);", ""),
            ("src/classes/shaman/dc_shaman.cpp", "SpiritLink::Forget(player);", ""),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", "thread_local bool echoing = false;", ""),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", "if (!IsShaman(player) || !target || echoing)", "if (!IsShaman(player) || !target)"),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", "echoing = true;", ""),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", "Combat::DealHit(player, enemy, linkId, echo, true);", "Combat::DealHit(player, enemy, linkId, echo);"),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", "Shares(echoing, RowOf(spellId) != nullptr)", "Shares(echoing, false)"),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", 'Tunable("spirit_link_elite_share_pct")', "50.0"),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", "Shaman::IsElite(enemy)", "false"),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", '"freeze_duration_seconds"', '"freeze_seconds"'),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", '"gain_resource"', '"gain"'),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", "Combat::ModifiedDurationSeconds(player, spellId,", "Combat::Nothing(player, spellId,"),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", "Combat::Strike(player, enemy, spellId, pct, true);", "Combat::Strike(player, enemy, spellId, pct);"),
            ("src/classes/shaman/dc_shaman_spirit_link.cpp", "std::optional<double>(0.0)", "std::optional<double>(100.0)"),
        ]
        for path, old, new in plants:
            with self.subTest(old):
                files = self.files()
                self.assertIn(old, squeeze(files[path]) if old not in files[path] else files[path])
                files[path] = files[path].replace(old, new)
                self.assertNotEqual(wiring_problems(files), [], f"{old!r} -> {new!r} was not caught")

    def test_the_share_comes_after_the_hit_in_the_real_engine(self):
        text = source("src/combat/dc_combat.cpp")
        self.assertLess(text.index("player->DealSpellDamage(&log, true);"), text.index("Shaman::Dealt("))

    def test_the_tunables_are_in_the_newest_migration(self):
        migration = (MODULE / "data/sql/db-world/updates" / (MODULE / "data/tunables/current_migration.txt").read_text().strip()).read_text(encoding="utf-8")
        for name in ("spirit_link_tick_seconds", "spirit_link_burn_tick_seconds", "spirit_link_elite_share_pct"):
            self.assertIn(f"('combat', '{name}',", migration)

    def test_the_cast_targets_one_enemy_and_the_runes_scale_the_sheets_radius(self):
        rows = {r["skill"]: r for r in read(MODULE / "data/d3/skill_targeting.csv")}
        self.assertEqual(rows["Spirit Link"]["target_type"], "single_enemy")
        self.assertGreater(float(value("Ancestral Chains", "radius_yards")), float(value("", "radius_yards")))

    def test_the_cast_has_no_hit_of_its_own_on_purpose(self):
        hits = source("scripts/tests/classes/test_shaman_hits.py")
        self.assertNotIn('"Spirit Link":', hits)


if __name__ == "__main__":
    unittest.main()
