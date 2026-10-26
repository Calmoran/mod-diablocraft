"""diablocraft-i7ixi (Monk 2.4.3): the passives Harmony, Combination Strike, Near Death Experience, Unity, Momentum, Mythic Rhythm.

What this proves, and how:

  * **The rules that need no core type.** tests/monk_passives_harmony/harness.cpp compiles the real dc_monk_passives_harmony.h with
    the sheets' numbers: Harmony moves 40% of each element's item resistance onto All Resistance, Combination Strike buffs only
    the OTHER generators once per different generator and lets each run out, Mythic Rhythm primes on the third generator hit and
    a spender spends it once, Momentum adds yards and starts at 25, Unity is 5% an ally up to 20% (an ally's side stops at its
    stacks), Near Death Experience saves fatal damage once per cooldown with its immunity window. Sixteen mutations planted in
    a scratch copy, at least two for most passives, must each make it fail.
  * **The code reads what the sheets state.** Every number dc_monk_passives_harmony.cpp reads by name is a row of
    monk_passive_values.csv for the six passives or a tunable of data/tunables/monk.csv with the power file's value. Combination
    Strike's duration is the power file's 3 seconds (the sheet said 10; PM ruling 966827a2).
  * **The wiring.** dc_monk.cpp calls Connected and Cast first, dc_monk_effects.cpp adds the passives to the Monk's damage bonus,
    dc_combat.cpp registers the scripts, and the script file holds the fatal-damage rule and the update that samples distance and
    puts Harmony's resistances on the sheet.

What it does not prove: anything on a running server. The stat lines, the damage numbers and the saved death are
docs/test-diablocraft-i7ixi.md's, live.

    python mod-diablocraft/scripts/tests/classes/test_monk_passives_harmony.py
"""

import csv
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env

REPO = Path(__file__).resolve().parents[4]
MODULE = REPO / "mod-diablocraft"
D3 = MODULE / "data" / "d3"
SOURCES = ["src/classes/monk/dc_monk_passives_harmony.h", "tests/monk_passives_harmony/harness.cpp"]
HEADER = "src/classes/monk/dc_monk_passives_harmony.h"
CPP = "src/classes/monk/dc_monk_passives_harmony.cpp"
PASSIVES = ["Harmony", "Combination Strike", "Near Death Experience", "Unity", "Momentum", "Mythic Rhythm"]


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def value(skill, token, qualifier=""):
    rows = [r for r in read(D3 / "monk_passive_values.csv")
            if (r["skill"], r["token"], r["qualifier"]) == (skill, token, qualifier)]
    assert len(rows) == 1, (skill, token, qualifier, len(rows))
    return float(rows[0]["value"])


def tunables():
    return {r["name"]: r for r in read(MODULE / "data" / "tunables" / "monk.csv")}


def tune(name):
    row = tunables()[name]
    return float(row["value"] or row["d3_value"])


def scratch_tree(mutate=None):
    """The headers one build stages ({path under src/: text}); the mutation edits one of them."""
    files = {source[len("src/"):]: (MODULE / source).read_text(encoding="utf-8") for source in SOURCES if source.startswith("src/")}
    if mutate:
        path, old, new = mutate
        key = path[len("src/"):]
        if files[key].count(old) != 1:
            raise AssertionError(f"mutation target {old!r} not found exactly once in {path}")
        files[key] = files[key].replace(old, new)
    return files


def build_and_run(tree):
    binary = harness_env.build([MODULE / "tests/monk_passives_harmony/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    numbers = [value("Harmony", "resistance_share_pct"), value("Combination Strike", "damage_bonus_pct"),
               value("Combination Strike", "duration_seconds"), value("Near Death Experience", "internal_cooldown_seconds"),
               value("Near Death Experience", "duration_seconds"), value("Near Death Experience", "heal_pct"),
               value("Unity", "damage_bonus_pct", "self"), value("Unity", "max_bonus_pct"),
               value("Unity", "damage_bonus_pct", "ally"), tune("unity_ally_max_stacks"),
               value("Momentum", "distance_yards"), value("Momentum", "damage_bonus_pct"), value("Momentum", "duration_seconds"),
               tune("mythic_rhythm_generator_hits"), value("Mythic Rhythm", "damage_bonus_pct")]
    return harness_env.run([str(binary)] + [str(n) for n in numbers], capture_output=True, text=True)


class Harness(unittest.TestCase):
    def test_the_rules_over_the_sheets_numbers(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 35, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("Harmony adds the largest share, not the sum", (HEADER, "out.all += moved;", "out.all = std::max(out.all, moved);")),
            ("Harmony takes nothing off the element", (HEADER, "out.single[i] = -moved;", "out.single[i] = 0;")),
            ("Combination Strike counts a run-out generator", (HEADER, "if (now < entry.second)", "if (true)")),
            ("Combination Strike does not stack", (HEADER, "return Active(now) * pct;", "return Active(now) ? pct : 0.0;")),
            ("Combination Strike does not renew", (HEADER, "until[generator] = now + ms;", "until.emplace(generator, now + ms);")),
            ("Mythic Rhythm arms on every hit", (HEADER, "hits = (hits + 1) % hitCount;", "hits = 0;")),
            ("Mythic Rhythm is never spent", (HEADER, "armed = false;\n            return was;", "return was;")),
            ("Mythic Rhythm's spend restarts the count", (HEADER, "armed = false;\n            return was;",
                                                         "armed = false;\n            hits = 0;\n            return was;")),
            ("Mythic Rhythm's bonus is there unarmed", (HEADER, "return (delayed ? carried : armed) ? pct : 0.0;", "return pct;")),
            ("Seven-Sided Strike's cast spends nothing", (HEADER, "carried = Spend();", "carried = armed;")),
            ("Seven-Sided Strike's strikes read the armed bonus", (HEADER, "return (delayed ? carried : armed) ? pct : 0.0;",
                                                                  "return armed ? pct : 0.0;")),
            ("Seven-Sided Strike's strikes carry nothing", (HEADER, "return (delayed ? carried : armed) ? pct : 0.0;",
                                                           "return (delayed ? false : armed) ? pct : 0.0;")),
            ("Momentum forgets the yards over", (HEADER, "yards = std::fmod(yards, needed);", "yards = 0;")),
            ("Momentum outlasts its seconds", (HEADER, "return now < until;", "return now <= until;")),
            ("Unity has no maximum", (HEADER, "return std::min(maxPct, allies * perAlly);", "return allies * perAlly;")),
            ("Unity's ally side has no stack cap", (HEADER, "return std::min(monks, maxStacks) * perMonk;", "return monks * perMonk;")),
            ("Near Death needs more than the Life", (HEADER, "if (damage < health || now < readyAt)", "if (damage <= health || now < readyAt)")),
            ("Near Death has no cooldown", (HEADER, "readyAt = now + cooldownMs;", "readyAt = now;")),
            ("Near Death heals past the maximum", (HEADER, "return std::min<std::uint64_t>(maxHealth, health + wanted);",
                                                   "return health + wanted;")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Sheets(unittest.TestCase):
    def test_the_numbers_the_code_reads_are_the_sheets(self):
        self.assertEqual(value("Harmony", "resistance_share_pct"), 40)
        self.assertEqual((value("Combination Strike", "damage_bonus_pct"), value("Combination Strike", "duration_seconds")), (10, 3))
        nde = [value("Near Death Experience", t) for t in ("heal_pct", "gain_pct", "duration_seconds", "internal_cooldown_seconds")]
        self.assertEqual(nde, [35, 35, 2, 60])
        self.assertEqual((value("Unity", "damage_bonus_pct", "self"), value("Unity", "max_bonus_pct"),
                          value("Unity", "damage_bonus_pct", "ally")), (5, 20, 5))
        self.assertEqual((value("Momentum", "distance_yards"), value("Momentum", "damage_bonus_pct"),
                          value("Momentum", "duration_seconds")), (25, 20, 6))
        self.assertEqual(value("Mythic Rhythm", "damage_bonus_pct"), 40)

    def test_combination_strike_s_duration_is_the_power_file_s_and_says_so(self):
        row = next(r for r in read(D3 / "monk_passive_values.csv")
                   if (r["skill"], r["token"]) == ("Combination Strike", "duration_seconds"))
        self.assertIn("Monk_Passive_CombinationStrike.pow SF_1", row["source"])
        self.assertIn("966827a2", row["source"])

    def test_combination_strike_s_damage_is_the_power_file_s_and_says_so(self):
        row = next(r for r in read(D3 / "monk_passive_values.csv")
                   if (r["skill"], r["token"]) == ("Combination Strike", "damage_bonus_pct"))
        self.assertIn("Monk_Passive_CombinationStrike.pow SF_0", row["source"])
        self.assertIn("2bb8979d7", row["source"])

    def test_the_tunables_are_the_power_files(self):
        self.assertEqual(tune("harmony_check_seconds"), 1)
        self.assertEqual(tune("momentum_tick_seconds"), 0.1)
        self.assertEqual(tune("unity_ally_max_stacks"), 4)
        # "Every third hit from a Spirit Generator": the count the sheet leaves out (the power file's SF_1 3)
        self.assertEqual(tune("mythic_rhythm_generator_hits"), 3)
        self.assertIn("Every third hit from a Spirit Generator", tunables()["mythic_rhythm_generator_hits"]["notes"])
        self.assertEqual(tune("near_death_experience_knockback_radius_yards"), 25)
        self.assertEqual(tune("near_death_experience_knockback_yards"), 15)

    def test_every_name_the_code_reads_exists(self):
        text = (MODULE / CPP).read_text(encoding="utf-8")
        read_tunables = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', text))
        mine = ("harmony_", "momentum_", "unity_", "mythic_rhythm_", "near_death_experience_")
        self.assertEqual(read_tunables, {n for n in tunables() if n.startswith(mine)})
        tokens = set(re.findall(r'Numbers::Num\([^,]+, "([a-z_]+)"', text))
        sheet_tokens = {r["token"] for r in read(D3 / "monk_passive_values.csv") if r["skill"] in PASSIVES}
        self.assertEqual(tokens - sheet_tokens, {"radius_yards"})  # radius_yards is the slotted Mantra's own
        self.assertEqual(tokens, {"resistance_share_pct", "damage_bonus_pct", "duration_seconds", "internal_cooldown_seconds",
                                  "heal_pct", "gain_pct", "max_bonus_pct", "distance_yards", "radius_yards"})

    def test_the_six_passives_are_records_and_sheet_rows(self):
        shells = (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8")
        sheet = {r["passive_name"] for r in read(D3 / "monk_passives.csv")}
        for name in PASSIVES:
            self.assertRegex(shells, r'\{\d+, "%s"\}' % name)
            self.assertIn(name, sheet)


def spell_columns():
    """The spell_dbc columns in Spell.dbc's order, read from the core's schema as generate_spells.py reads them."""
    columns, inside = [], False
    for line in (REPO / "azerothcore-wotlk/data/sql/base/db_world/spell_dbc.sql").read_text(
            encoding="utf-8", errors="replace").splitlines():
        if line.startswith("CREATE TABLE `spell_dbc`"):
            inside = True
        elif inside and line.startswith(")"):
            break
        elif inside and line.strip().startswith("`"):
            columns.append(line.strip().split("`")[1])
    return columns


class Tooltip(unittest.TestCase):
    """diablocraft-2wf3x: Mythic Rhythm's tooltip is D3's sentence (decisions.md 2026-10-15), not the old Spirit text."""

    OLD = "Spirit to your next Spirit Generator hits"

    def setUp(self):
        self.row = next(r for r in read(D3 / "monk_passives.csv") if r["passive_name"] == "Mythic Rhythm")
        self.id = next(r["spell_id"] for r in read(MODULE / "data/generated/spell_shells.csv")
                       if r["name"] == "Mythic Rhythm" and r["kind"] == "passive")
        mapped = [r for r in read(MODULE / "data/generated/spell_value_map.csv")
                  if r["spell_id"] == self.id and r["token"] == "damage_bonus_pct"]
        self.assertEqual(1, len(mapped))
        self.assertEqual("base_points", mapped[0]["source"])
        sentence = self.row["full_text"].split(" | ")[0]
        # the record's text: the sheet's sentence with the client's own $sN where the value goes
        self.record = re.compile(re.escape(sentence).replace(re.escape("{damage_bonus_pct}"), r"\$s[1-3]%"))

    def shipped(self, render):
        line = next(l for l in render.read_text(encoding="utf-8").splitlines() if l.startswith(f"({self.id},"))
        self.assertNotIn(self.OLD, line)
        found = [m.group(0) for m in re.finditer(r"'([^']*)'", line) if self.record.fullmatch(m.group(1))]
        self.assertEqual(1, len(found), line)
        return found[0][1:-1]

    def test_the_sheet_says_d3_s_sentence(self):
        import json
        tip = json.loads((REPO / "reference/d3planner/data.json").read_text(encoding="utf-8"))["passivetips"]["monk"]["mythicrhythm"]
        d3 = re.sub(r"<[^>]+>", "", tip[tip.index("<p>"):tip.index("</p>")])
        sentence = self.row["full_text"].split(" | ")[0]
        self.assertEqual(d3, sentence.replace("{damage_bonus_pct}", "%g%%" % value("Mythic Rhythm", "damage_bonus_pct")))
        self.assertEqual(value("Mythic Rhythm", "damage_bonus_pct"), 40)
        # the rows the old text read are gone with it: the passive pays no Spirit and has no stacks
        tokens = {r["token"] for r in read(D3 / "monk_passive_values.csv") if r["skill"] == "Mythic Rhythm"}
        self.assertEqual({"damage_bonus_pct"}, tokens)

    def test_the_server_record_and_the_newest_migration_carry_it(self):
        renders = [MODULE / "data/generated/spell_shells.sql"]
        migrations = sorted((MODULE / "data/sql/db-world/updates").glob("combat_*.sql"))
        renders.append(next(m for m in reversed(migrations) if f"\n({self.id}," in m.read_text(encoding="utf-8")))
        texts = []
        for render in renders:
            with self.subTest(render.name):
                texts.append(self.shipped(render))
        self.assertEqual(1, len(set(texts)), texts)

    def test_the_committed_archive_carries_it(self):
        import struct
        import tempfile
        if not shutil.which("smpq"):
            self.skipTest("no smpq")
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["smpq", "-x", str(REPO / "client-patch/patch-4.MPQ"), "DBFilesClient/Spell.dbc"],
                           cwd=tmp, check=True, capture_output=True)
            data = (Path(tmp) / "DBFilesClient/Spell.dbc").read_bytes()
        _, records, fields, size, _ = struct.unpack("<4sIIII", data[:20])
        strings = data[20 + records * size:]
        field = spell_columns().index("Description_Lang_enUS")
        for n in range(records):
            if struct.unpack_from("<I", data, 20 + n * size)[0] == int(self.id):
                offset = struct.unpack_from("<I", data, 20 + n * size + 4 * field)[0]
                text = strings[offset:strings.index(b"\0", offset)].decode("utf-8")
                # the client draws the same text the server's record carries
                self.assertEqual(self.shipped(MODULE / "data/generated/spell_shells.sql"), text)
                return
        self.fail(f"no Spell.dbc record {self.id} in the committed patch-4.MPQ")


if __name__ == "__main__":
    unittest.main()
