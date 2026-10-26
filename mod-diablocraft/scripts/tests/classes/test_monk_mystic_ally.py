"""diablocraft-a0vq0 (Monk 2.3.13, Mystic Ally and its five runes).

What this proves, and how:

  * **The maths.** tests/monk_mystic_ally/harness.cpp compiles the real dc_monk_mystic_ally.h: the ally follows the bar
    (summoned when slotted, sent away when not, replaced when the rune changes, reborn exactly when its respawn time is up),
    Water Ally's wave is a strip ahead of the ally that turns with its facing, Air Ally's Spirit is paid a whole second at
    a time and keeps the rest, and Earth Ally's knock-up lifts the power file's height on the core's parabola. Planted
    mutations in a scratch copy must each make it fail.
  * **The data.** monk_summons.csv has one creature per record (the six entries the code summons), each a donor that exists
    in the pinned core with a model and no difficulty entry, in no other summon sheet's entries; combat_0067 is the
    generator's render and holds all six; the Wizard's templates render as before; the records' cooldowns are the sheet's
    (30 s, Enduring Ally 50 s); every tunable the code reads is in monk.csv and reaches tunables_0012.
  * **The wiring.** dc_monk.cpp hands a Mystic Ally record over first in BasePct and Cast and calls its Landed;
    Monk::DamageBonus adds Fire Ally's Passive; dc_combat.cpp registers the Monk's scripts once, beside the Wizard's.

What it does not prove: anything on a running server (the ally's following, fighting and the Actives); the test sheet's
checks do.

    python mod-diablocraft/scripts/tests/classes/test_monk_mystic_ally.py
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
HEADER = "src/classes/monk/dc_monk_mystic_ally.h"
SOURCES = [HEADER, "tests/monk_mystic_ally/harness.cpp"]
GLUE = MODULE / "src/classes/monk/dc_monk_mystic_ally.cpp"
CORE_SQL = REPO / "azerothcore-wotlk/data/sql/base/db_world"
UPDATES = MODULE / "data/sql/db-world/updates"
MIGRATION = UPDATES / "combat_0067_monk_summons.sql"
SKILL = "Mystic Ally"


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
    binary = harness_env.build([MODULE / "tests/monk_mystic_ally/harness.cpp"], flags=["-std=c++20", "-O1"], files=tree)
    return harness_env.run([str(binary)], capture_output=True, text=True)


def sheet(name):
    with (MODULE / "data" / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def values():
    """{(rune, token, qualifier): value} of Mystic Ally in monk_skill_values.csv."""
    return {(r["rune"], r["token"], r["qualifier"]): float(r["value"])
            for r in sheet("d3/monk_skill_values.csv") if r["skill"] == SKILL}


def records():
    """{name: {column: value}} of the Mystic Ally spell_dbc rows in the Monk records migration."""
    text = (UPDATES / "combat_0066_monk_records.sql").read_text(encoding="utf-8")
    out = {}
    for insert in re.finditer(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES(.*?);\n", text, re.S):
        columns = [c.strip(" `") for c in insert.group(1).split(",")]
        for row in re.finditer(r"^\((.*)\),?$", insert.group(2), re.M):
            record = dict(zip(columns, re.findall(r"'(?:[^'\\]|\\.)*'|[^,]+", row.group(1))))
            name = record.get("Name_Lang_enUS", "").strip("'")
            if name == SKILL or (name.startswith(SKILL + " - ") and name.count(" - ") == 1):  # not the token storage
                out[name] = record
    return out


class Harness(unittest.TestCase):
    def test_the_upkeep_the_wave_the_spirit_and_the_knock(self):
        out = build_and_run(scratch_tree())
        self.assertEqual(out.returncode, 0, out.stdout[-2000:])
        cases = int(out.stdout.split("cases=")[1].split()[0])
        self.assertGreaterEqual(cases, 22, out.stdout)
        print(f"\n  harness: {out.stdout.strip()}")

    def test_a_planted_difference_is_caught(self):
        mutations = [
            ("reborn a millisecond late", (HEADER, "return now >= rebornAt ? Act::Summon : Act::Keep;",
                                           "return now > rebornAt ? Act::Summon : Act::Keep;")),
            ("a rune change keeps the old ally", (HEADER, "return summoned == slotted ? Act::Keep : Act::Replace;",
                                                  "return Act::Keep;")),
            ("an ally stays off the bar", (HEADER, "return summoned ? Act::Despawn : Act::Keep;", "return Act::Keep;")),
            ("the wave reaches behind", (HEADER, "return along >= 0 && along <= lengthYards", "return along <= lengthYards")),
            ("the wave ignores its side", (HEADER, " && std::fabs(across) <= radiusYards;", ";")),
            ("Spirit drops the leftover", (HEADER, "clockMs %= 1000;", "clockMs = 0;")),
            ("the knock-up height is off", (HEADER, "std::sqrt(2 * gravity * heightYards)", "std::sqrt(gravity * heightYards)")),
            ("a straight-up knock is refused by the core", (HEADER, "CoreMinimumSpeedXY * 1.1", "0.0")),
        ]
        for label, mutation in mutations:
            with self.subTest(label):
                try:
                    tree = scratch_tree(mutation)
                except AssertionError as error:
                    self.fail(str(error))
                out = build_and_run(tree)
                self.assertNotEqual(out.returncode, 0, f"{label} was not caught: {out.stdout[-500:]}")


class Data(unittest.TestCase):
    def test_one_creature_per_record_from_a_real_donor(self):
        rows = sheet("d3/monk_summons.csv")
        runes = [r["rune_name"] for r in sheet("d3/monk_runes.csv") if r["skill_name"] == SKILL]
        self.assertEqual(sorted(r["rune"] for r in rows), sorted([""] + runes))
        self.assertEqual({r["script"] for r in rows}, {"dc_monk_ally"})
        glue = GLUE.read_text(encoding="utf-8")
        for r in rows:
            with self.subTest(r["summon"]):
                # the entry the code summons for that record is the sheet's
                if r["rune"]:
                    self.assertRegex(glue, rf'if \(rune == "{r["rune"]}"\)\s+return {r["entry"]};')
                else:
                    self.assertRegex(glue, rf"return {r['entry']};\s+}}\s+Creature\* AllyOf")
        templates = (CORE_SQL / "creature_template.sql").read_text(encoding="utf-8")
        models = (CORE_SQL / "creature_template_model.sql").read_text(encoding="utf-8")
        for donor in sorted({r["donor_creature"] for r in rows}):
            with self.subTest(donor=donor):
                row = re.search(rf"^\({donor},(\d+),(\d+),(\d+),", templates, re.M)
                self.assertIsNotNone(row, donor)
                self.assertEqual(row.groups(), ("0", "0", "0"))  # difficulty_entry_1..3: the clone would claim them
                self.assertRegex(models, rf"(?m)^\({donor},0,\d+,")

    def test_no_entry_is_another_summons(self):
        mine = {int(r["entry"]) for r in sheet("d3/monk_summons.csv")}
        others = ({int(r["entry"]) for r in sheet("d3/wizard_summons.csv")} |
                  {int(r["entry"]) for r in sheet("legendary_summons.csv")} | set(range(900100, 900103)))
        self.assertEqual(len(mine), 6)
        self.assertFalse(mine & others)
        self.assertIn("'data/d3/monk_summons.csv'",
                      (MODULE / "scripts/generate/legendaries/generate_legendary_summons.py").read_text(encoding="utf-8"))

    def test_the_migration_is_the_generators_render(self):
        sys.path.insert(0, str(MODULE / "scripts"))
        import generate_spells
        sql = MIGRATION.read_text(encoding="utf-8")
        templates = generate_spells.generate_wizard_summon_templates()
        self.assertTrue(sql.endswith(templates), "combat_0067 ends with the summon render")
        for r in sheet("d3/monk_summons.csv"):
            with self.subTest(r["summon"]):
                self.assertIn(f"SET entry={r['entry']},name='{r['summon']}',subname='',npcflag=0,unit_flags=0,", sql)
                self.assertIn(f"INSERT INTO creature_template_model SELECT {r['entry']},Idx,", sql)
        self.assertEqual(sql.count("ScriptName='dc_monk_ally'"), 6)
        # the Wizard's part is what combat_0040 rendered before
        old = (UPDATES / "combat_0040_proc_coefficient_tunables.sql").read_text(encoding="utf-8")
        wizard = old[old.index("-- The Wizard's summons"):]
        self.assertTrue(templates.startswith(wizard), "the Wizard's templates are unchanged")
        names = sorted(p.name for p in UPDATES.glob("combat_*.sql"))
        self.assertGreater(names.index(MIGRATION.name), names.index("combat_0066_monk_records.sql"))

    def test_the_records_cooldowns_are_the_sheets(self):
        found = {name: int(record["RecoveryTime"]) for name, record in records().items()}
        v = values()
        self.assertEqual(len(found), 6)
        for name, ms in found.items():
            rune = name[len(SKILL) + 3:] if " - " in name else ""
            self.assertEqual(ms, int(v.get((rune, "cooldown_seconds", ""), v[("", "cooldown_seconds", "")]) * 1000), name)
        self.assertEqual(found[SKILL + " - Enduring Ally"], 50000)

    def test_every_tunable_the_code_reads_is_in_the_sheet_and_the_migration(self):
        names = set(re.findall(r'Tune\("([a-z0-9_]+)"\)', GLUE.read_text(encoding="utf-8")))
        rows = {r["name"]: r for r in sheet("tunables/monk.csv")}
        sql = (UPDATES / "tunables_0014.sql").read_text(encoding="utf-8")
        self.assertEqual(len(names), 14, sorted(names))
        for name in sorted(names):
            with self.subTest(name):
                self.assertIn(name, rows)
                self.assertTrue(rows[name]["d3_value"] or rows[name]["value"])
                self.assertIn(f"('monk', '{name}',", sql)
        # The Crudest Boots's "active forms longer" (diablocraft-x1tg0) has no number in any source: the designer's value, card q-1014-20 (c)
        boots = rows["mystic_ally_boots_form_duration_pct"]
        self.assertEqual((boots["d3_value"], boots["value"], boots["unit"], "q-1014-20" in boots["notes"]), ("", "50", "percent", True))
        # the two numbers no source gives are values (the designer's), not D3 values: card q-1014-05
        # final since bead 760kv (the designer's answer to the card): 15 yards and 8 yards a second
        for name, alex in (("mystic_ally_water_wave_length_yards", "15"), ("mystic_ally_earth_speed_yards_per_second", "8")):
            self.assertEqual((rows[name]["d3_value"], rows[name]["value"], "q-1014-05" in rows[name]["notes"],
                              "final" in rows[name]["notes"]), ("", alex, True, True))

    def test_the_sheet_numbers_the_code_reads(self):
        v = values()
        self.assertEqual(v[("", "damage_pct", "")], 130)
        self.assertEqual(v[("", "duration_seconds", "respawn")], 5)
        self.assertEqual(v[("Fire Ally", "pet_count", "")], 2)  # the sheet, not the power file's 5 (PM: the live tooltip)
        self.assertEqual(v[("Earth Ally", "damage_pct", "")], 4500)


if __name__ == "__main__":
    unittest.main()
