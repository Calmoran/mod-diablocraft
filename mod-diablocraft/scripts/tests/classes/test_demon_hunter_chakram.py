"""Demon Hunter Chakram and its five runes (src/classes/demon_hunter/dc_demon_hunter_chakram.h and .cpp).

What this proves, and how:

  * **The logic that needs no core type.** tests/demon_hunter_chakram/harness.cpp compiles the real dc_demon_hunter_chakram.h and the
    clock with the sheets' own rune names and numbers: each rune name is its rune; a tick of Shuriken Cloud carries its share of the
    200% a second; the cloud lasts its ten minutes; held ten seconds of server updates it ticks at the half second and deals the
    sheet's damage a second. Six mutations planted in a scratch copy (two runes share a name, a tick is the whole second or has no
    share, the cloud lasts seconds not minutes or forever, the clock loses its rest) must each make it fail.
  * **The record is the cloud on the Demon Hunter.** The migration combat_0100 gives Shuriken Cloud's record the caster as its target
    with the cloud's area, where the other runes keep the line throw: the one record the client patch changes.
  * **The code reads what the sheets state.** Every token the .cpp reads is a row of demon_hunter_skill_values.csv for Chakram (or the
    rune that states it): Twin Chakrams 220%, Shuriken Cloud 200% a second for 10 minutes; every tunable is a row of
    data/tunables/demonhunter.csv, and the numbers equal the decoded Power/DemonHunter_Chakram.pow (skipped where the game archives
    are not on this machine).
  * **The wiring.** The dispatch answers the seams, the second chakram is not itself doubled, the cloud has no engine hit, starts at
    the cast and starts the rune's cooldown, and ends with its minutes, its owner's death, the map and the logout.

What it does not prove: anything on a running server. The throw, the second chakram and the cloud are
docs/test-diablocraft-vawmy.14.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_demon_hunter_chakram.py
"""

import csv
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
HEADER = "src/classes/demon_hunter/dc_demon_hunter_chakram.h"
CLOCK = "src/classes/demon_hunter/dc_demon_hunter_clock.h"
SOURCES = [HEADER, CLOCK, "tests/demon_hunter_chakram/harness.cpp"]
CODE = MODULE / "src/classes/demon_hunter/dc_demon_hunter_chakram.cpp"
SKILL = "Chakram"
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0100_demon_hunter_shuriken_cloud_on_the_demon_hunter.sql"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(rune, token, qualifier=""):
    rows = [r for r in read(D3 / "demon_hunter_skill_values.csv")
            if (r["skill"], r["rune"], r["token"], r["qualifier"]) == (SKILL, rune, token, qualifier)]
    assert len(rows) == 1, (rune, token, qualifier, len(rows))
    return float(rows[0]["value"])


def runes():
    rows = sorted((r for r in read(D3 / "demon_hunter_runes.csv") if r["skill_name"] == SKILL), key=lambda r: r["rune_slot"])
    return [r["rune_name"] for r in rows]


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "demonhunter.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def scratch_tree(mutate=None):
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/demon_hunter_chakram/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = runes() + [value("Shuriken Cloud", "damage_pct"), tune("chakram_cloud_tick_seconds"), value("Shuriken Cloud", "duration_minutes")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_names_and_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 9, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("two runes share a name", (HEADER, 'if (name == "Serpentine")\n            return Rune::Serpentine;', 'if (name == "Serpentine")\n            return Rune::Boomerang;')),
            ("a tick is the whole second", (HEADER, "return tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;", "return tickSeconds > 0 ? perSecondPct : 0.0;")),
            ("a tick with no length still deals", (HEADER, "return tickSeconds > 0 ? perSecondPct * tickSeconds : 0.0;", "return perSecondPct * tickSeconds;")),
            ("the cloud lasts minutes as seconds", (HEADER, "minutes * 60000.0", "minutes * 1000.0")),
            ("the cloud lasts for ever", (HEADER, "return nowMs + std::uint64_t(minutes > 0 ? minutes * 60000.0 : 0.0);", "return ~std::uint64_t(0);")),
            ("the clock loses its rest", (CLOCK, "clock -= interval;", "clock = 0;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Records(unittest.TestCase):
    def test_the_cloud_is_cast_on_the_demon_hunter_and_the_other_runes_keep_the_line(self):
        migration = MIGRATION.read_text(encoding="utf-8")
        columns = [c.strip(" `\n") for c in re.search(r"INSERT INTO `?spell_dbc`?\s*\(([^)]*)\)", migration).group(1).split(",")]
        ids = {r[1]: int(r[0]) for r in csv.reader((MODULE / "data/generated/spell_shells.csv").read_text(encoding="utf-8").splitlines())
               if r and r[0].isdigit() and r[4] in ("active", "rune")}

        def record(spell):
            row = re.search(r"\(%d,([^\n]*)\)[,;]?\n" % spell, migration)
            return dict(zip(columns, ("%d," % spell + row.group(1)).split(",")))

        cloud = record(ids["Chakram - Shuriken Cloud"])
        self.assertEqual((cloud["ImplicitTargetA_1"], cloud["RangeIndex"]), ("1", "1"))
        self.assertNotEqual(cloud["EffectRadiusIndex_1"], "0")
        for name in ("Chakram", "Chakram - Twin Chakrams", "Chakram - Boomerang", "Chakram - Serpentine", "Chakram - Razor Disk"):
            self.assertNotEqual(record(ids[name])["ImplicitTargetA_1"], "1", name)


class Sheets(unittest.TestCase):
    def test_the_five_runes(self):
        self.assertEqual(runes(), ["Twin Chakrams", "Boomerang", "Serpentine", "Razor Disk", "Shuriken Cloud"])

    def test_the_numbers_the_code_reads_are_the_researched_ones(self):
        self.assertEqual([value("", "cost_resource"), value("", "damage_pct")], [10, 380])
        self.assertEqual([value(r, "damage_pct") for r in ("Twin Chakrams", "Boomerang", "Serpentine", "Razor Disk", "Shuriken Cloud")],
                         [220, 400, 500, 380, 200])
        self.assertEqual(value("Shuriken Cloud", "duration_minutes"), 10)

    def test_the_tunables(self):
        rows = tunables()
        for name, d3, source in (("chakram_cloud_tick_seconds", "0.5", "SF_9"), ("chakram_cloud_radius_yards", "8", "SF_15"),
                                 ("chakram_cloud_cooldown_seconds", "10", "SF_8")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"]), (d3, ""), name)
            self.assertIn(source, rows[name]["notes"])
            self.assertIn("Power/DemonHunter_Chakram.pow", rows[name]["notes"])
            self.assertNotIn("PLACEHOLDER", rows[name]["notes"], name)

    def test_every_name_the_code_reads_exists_and_the_engine_can_read_it(self):
        text = CODE.read_text(encoding="utf-8")
        self.assertEqual(set(re.findall(r'Tune\(\s*"([a-z0-9_]+)"', text)), {name for name in tunables() if name.startswith("chakram_")})
        tokens = set(re.findall(r'Numbers::(?:Num|Get|Own|Inherited)\([\w()]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "demon_hunter_skill_values.csv") if r["skill"] == SKILL}
        self.assertEqual(tokens - sheet_tokens, set())
        self.assertEqual(tokens, {"damage_pct", "duration_minutes"})
        mapped = {(r["rune"], r["token"]): r for r in read(MODULE / "data/generated/spell_value_map.csv") if r["skill"] == SKILL}
        for rune in ("Twin Chakrams", "Shuriken Cloud"):
            self.assertEqual(mapped[(rune, "damage_pct")]["origin"], "own")
        self.assertEqual(mapped[("Shuriken Cloud", "duration_minutes")]["origin"], "own")

    def test_the_skill_reads_the_power_files_numbers(self):
        import decode_pow
        if not decode_pow.available():
            self.skipTest("the game archives are not on this machine")
        sf = decode_pow.parse_power(decode_pow.extract("Power/DemonHunter_Chakram.pow"))["sf"]

        def number(n):
            return float(sf[n])

        self.assertAlmostEqual(number(0) * 100, value("", "damage_pct"))
        self.assertAlmostEqual(number(2) * 100, value("Twin Chakrams", "damage_pct"))
        self.assertAlmostEqual(number(4) * 100, value("Boomerang", "damage_pct"))
        self.assertAlmostEqual(number(7) * 100, value("Serpentine", "damage_pct"))
        self.assertAlmostEqual(number(10) * 100, value("Razor Disk", "damage_pct"))
        self.assertAlmostEqual(number(13) * 100, value("Shuriken Cloud", "damage_pct"))
        self.assertAlmostEqual(float(sf[12].split("?")[1].split(":")[0]) / 60, value("Shuriken Cloud", "duration_minutes"))
        self.assertAlmostEqual(number(9), tune("chakram_cloud_tick_seconds"))
        self.assertAlmostEqual(number(15), tune("chakram_cloud_radius_yards"))
        self.assertAlmostEqual(number(8), tune("chakram_cloud_cooldown_seconds"))


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = re.sub(r"\s+", " ", CODE.read_text(encoding="utf-8"))
        self.dispatch = re.sub(r"\s+", " ", (MODULE / "src/classes/demon_hunter/dc_demon_hunter.cpp").read_text(encoding="utf-8"))

    def test_the_dispatch_answers_the_seams(self):
        self.assertEqual(self.dispatch.count("if (auto ring = Chakram::BasePct(spellId)) return ring;"), 1)
        self.assertLess(self.dispatch.index("RapidFire::BasePct(spellId)"), self.dispatch.index("Chakram::BasePct(spellId)"))
        for call in ("Chakram::Landed(player, target, spellId);", "Chakram::Cast(player, spellId, targets);", "Chakram::RegisterScripts();"):
            self.assertEqual(self.dispatch.count(call), 1, call)

    def test_the_cloud_throws_nothing_and_the_other_runes_keep_the_loaders_hit(self):
        self.assertIn("return RuneAt(spellId) == Rune::ShurikenCloud ? std::optional<double>(0.0) : std::nullopt;", self.code)

    def test_the_second_chakram_is_not_doubled_again(self):
        landed = self.code[self.code.index("void Landed("):self.code.index("void Cast(")]
        self.assertIn("if (throwing || !player || !target || RuneAt(spellId) != Rune::TwinChakrams) return;", landed)
        self.assertIn("Scope scope(throwing);", landed)
        self.assertIn('Combat::Strike(player, target, spellId, Numbers::Num(spellId, "damage_pct"));', landed)

    def test_the_cloud_starts_at_the_cast_with_its_cooldown_and_ends_with_its_owner(self):
        cast = self.code[self.code.index("void Cast("):self.code.index("void RegisterScripts(")]
        self.assertIn("RuneAt(spellId) != Rune::ShurikenCloud) return;", cast)
        self.assertIn('CloudEndsAt(Now(), Numbers::Num(spellId, "duration_minutes"))', cast)
        self.assertIn('player->AddSpellCooldown(spellId, 0, std::uint32_t(Tune("chakram_cloud_cooldown_seconds") * 1000.0), true);', cast)
        update = self.code[self.code.index("void OnPlayerUpdate("):self.code.index("void OnPlayerLogout(")]
        self.assertIn("if (!player->IsAlive() || Now() >= cloud.endsAt) {", update)
        self.assertIn('CloudTickPct(Numbers::Num(cloud.spellId, "damage_pct"), tick)', update)
        self.assertIn('Tune("chakram_cloud_radius_yards")', update)
        self.assertIn("OnPlayerMapChanged", self.code)
        self.assertIn("OnPlayerLogout", self.code)


if __name__ == "__main__":
    unittest.main()
