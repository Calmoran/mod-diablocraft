"""diablocraft-barbarian-skills: Furious Charge (#45), Bash - Punish (#44), sheet tooltips (#71).

A. #45 and every shell with the same defect. A record whose effect takes a
   TARGET_DEST_DEST point must carry the stock TARGET_FLAG_DEST_LOCATION, or
   the client never asks for a ground point and the core puts the destination
   on the caster. Checked on the generated spell_dbc rows, the shipped
   migration and, when it is present, the client Spell.dbc.
B. #44. Punish's buff is a real aura record built from the rune's values
   sheet rows, and the module's own Punish and DamageBonus (cut out of
   dc_barbarian_primaries.cpp) stack it to the cap, refresh its timer and read the bonus
   back from its stacks. Each fix is also put back the old way, one mutation at
   a time, and the harness must fail.
C. #71. generate_sql.py fills the tooltip tokens; the filled render of the
   three Barbarian tables is byte-for-byte the applied 0001 migrations, and an
   unfilled `{token}` stops the run before anything is written.

What no test here covers: the client's ground cursor, the charge movement,
Aura::SetStackAmount and the buff bar's own drawing. Those are
docs/test-diablocraft-barbarian-skills.md's job, live.
"""
import contextlib
import csv
import io
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import tempfile
import unittest
from pathlib import Path

import generate_sql

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
GENERATED = MODULE / "data" / "generated"
UPDATES = MODULE / "data" / "sql" / "db-world" / "updates"
SPELL_MIGRATION = UPDATES / "combat_0034_ground_targets_punish.sql"
CLIENT_DBC = REPO / "client-patch" / "dbc" / "Spell.dbc"
SERVER_DBC = REPO / "azerothcore-wotlk" / "build" / "server" / "data" / "dbc"
HARNESS = MODULE / "tests" / "barbarian_punish"
SCRATCH = REPO / "azerothcore-wotlk" / "build" / "_agent-scratch" / "barbarian_punish"
PRIMARIES = (MODULE / "src" / "classes" / "barbarian" / "dc_barbarian_primaries.cpp").read_text(encoding="utf-8")

TARGET_DEST_DEST = 87
TARGET_FLAG_DEST_LOCATION = 0x40
SPELL_ATTR0_PASSIVE = 0x40
PLACEHOLDER = re.compile(r"\{[a-z_]+(?::[a-z_]+)?\}")


def spell_rows(sql):
    """{id: {column: text}} for every spell_dbc row of one render."""
    columns = [c.strip(" `") for c in re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql)[1].split(",")]
    rows = {}
    for line in sql.splitlines():
        if line.startswith("("):
            row = next(csv.reader([line[1:line.rindex(")")]], quotechar="'", escapechar="\\"))
            rows[int(row[0])] = dict(zip(columns, row))
    return columns, rows


def dest_targeted(row):
    return any(int(row["ImplicitTarget%s_%d" % (side, slot)]) == TARGET_DEST_DEST
               for side in "AB" for slot in (1, 2, 3))


def punish_values():
    with (MODULE / "data" / "d3" / "barbarian_skill_values.csv").open(encoding="utf-8", newline="") as stream:
        rows = {row["token"]: float(row["value"]) for row in csv.DictReader(stream)
                if row["skill"] == "Bash" and row["rune"] == "Punish"}
    return rows["damage_bonus_pct"], rows["max_stacks_count"], rows["duration_seconds"]


class GroundTargetFlag(unittest.TestCase):
    """A: every DEST_DEST record carries the flag, in every place it ships."""

    def check(self, label, rows):
        missing = sorted("%d %s" % (sid, row["Name_Lang_enUS"]) for sid, row in rows.items()
                         if dest_targeted(row) and not int(row["Targets"]) & TARGET_FLAG_DEST_LOCATION)
        self.assertEqual(missing, [], "%s: ground-target records without TARGET_FLAG_DEST_LOCATION" % label)
        return [row["Name_Lang_enUS"] for row in rows.values() if dest_targeted(row)]

    def test_generated_rows(self):
        _columns, rows = spell_rows((GENERATED / "spell_shells.sql").read_text(encoding="utf-8"))
        names = self.check("spell_shells.sql", rows)
        for name in ("Furious Charge", "Furious Charge - Dreadnought", "Avalanche", "Leap", "Teleport",
                     "Arcane Orb", "Slow Time - bubble"):
            self.assertIn(name, names)

    def test_shipped_migration(self):
        _columns, rows = spell_rows(SPELL_MIGRATION.read_text(encoding="utf-8"))
        self.check(SPELL_MIGRATION.name, rows)

    def test_the_check_catches_a_missing_flag(self):
        _columns, rows = spell_rows((GENERATED / "spell_shells.sql").read_text(encoding="utf-8"))
        rows[81013]["Targets"] = "0"
        with self.assertRaises(AssertionError):
            self.check("mutated", rows)

    def test_client_dbc(self):
        if not CLIENT_DBC.is_file():
            self.skipTest("client-patch/dbc/Spell.dbc is not built here")
        columns, rows = spell_rows((GENERATED / "spell_shells.sql").read_text(encoding="utf-8"))
        data = CLIENT_DBC.read_bytes()
        _magic, count, _fields, size, _strings = struct.unpack("<4sIIII", data[:20])
        client = {}
        for index in range(count):
            record = data[20 + index * size:20 + (index + 1) * size]
            sid = struct.unpack_from("<I", record, 0)[0]
            if sid in rows:
                client[sid] = dict(rows[sid])
                for column in ["Targets"] + ["ImplicitTarget%s_%d" % (s, n) for s in "AB" for n in (1, 2, 3)]:
                    client[sid][column] = str(struct.unpack_from("<i", record, 4 * columns.index(column))[0])
        self.assertEqual(sorted(client), sorted(rows), "the client DBC lacks a generated record")
        self.check("client Spell.dbc", client)


class PunishRecord(unittest.TestCase):
    """B: the buff the player wears, built from the rune's values sheet rows."""

    def test_record_fields(self):
        pct, stacks, seconds = punish_values()
        _columns, rows = spell_rows((GENERATED / "spell_shells.sql").read_text(encoding="utf-8"))
        with (GENERATED / "spell_shells.csv").open(encoding="utf-8", newline="") as stream:
            # the Barbarian's buff, not the Crusader's Punish skill (85400, kind active), which shares the name
            ids = [int(row["spell_id"]) for row in csv.DictReader(stream)
                   if row["name"] == "Punish" and row["kind"] == "barbarian_buff"]
        self.assertEqual(len(ids), 1)
        row = rows[ids[0]]
        self.assertEqual(row["Name_Lang_enUS"], "Punish")
        self.assertFalse(int(row["Attributes"]) & SPELL_ATTR0_PASSIVE, "a passive aura is hidden from the buff bar")
        self.assertEqual((int(row["Effect_1"]), int(row["EffectAura_1"]), int(row["ImplicitTargetA_1"])),
                         (6, 4, 1), "APPLY_AURA, DUMMY, on the caster")
        self.assertEqual(int(row["EffectBasePoints_1"]) + int(row["EffectDieSides_1"]), pct)
        self.assertEqual(int(row["CumulativeAura"]), stacks)
        self.assertEqual(row["AuraDescription_Lang_enUS"], "Damage increased by $s1%.")
        self.assertEqual(row["SpellIconID"], rows[81034]["SpellIconID"], "the Punish rune's own icon")
        if (SERVER_DBC / "SpellDuration.dbc").is_file():
            data = (SERVER_DBC / "SpellDuration.dbc").read_bytes()
            _magic, count, _fields, size, _strings = struct.unpack("<4sIIII", data[:20])
            durations = {struct.unpack_from("<I", data, 20 + i * size)[0]:
                         struct.unpack_from("<i", data, 24 + i * size)[0] for i in range(count)}
            self.assertEqual(durations[int(row["DurationIndex"])], seconds * 1000)
        header = (MODULE / "src" / "combat" / "dc_spell_shells.h").read_text(encoding="utf-8")
        self.assertIn('{%d, "Punish", 0},' % ids[0], header)


def definition(marker, source, keyword="{"):
    """One definition, braces balanced, exactly as the module has it."""
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index(keyword, start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def extract(primaries=PRIMARIES):
    return ("// Generated by scripts/tests/classes/test_barbarian_skills.py from dc_barbarian_primaries.cpp. Do not edit.\n"
            "#pragma once\nnamespace DC::Combat::Primaries\n{\nnamespace D = PrimaryData;\n"
            "using B = D::Behavior;\n"
            + definition("struct Buffs", primaries) + ";\n"
            "inline std::mutex mutex;\ninline std::unordered_map<uint64, Buffs> buffs;\n"
            + definition("bool Alive(uint32 start, uint32 duration)", primaries) + "\n"
            + definition("uint32 PunishAura()", primaries) + "\n"
            + definition("D::Row const* PunishRow()", primaries) + "\n"
            + definition("void Punish(Player* player, D::Row const& row)", primaries) + "\n"
            + definition("bool Given(Player const* player, D::Row const& row)", primaries) + "\n"
            + definition("D::Row const* Effect(Player const* player, D::Row const& active, B behavior)", primaries) + "\n"
            + definition("double DamageBonus(Player* player)", primaries) + "\n}\n")


MUTATIONS = {
    "stacks without the cap": (
        "std::min(unsigned(aura->GetStackAmount()) + 1, row.cap)", "unsigned(aura->GetStackAmount()) + 1"),
    "timer not refreshed": ("aura->SetDuration(int32(row.duration));", ""),
    "bonus ignores the stacks": ("aura->GetStackAmount() * punish->magnitude", "punish->magnitude"),
    "bonus not read from the aura": (
        "if (Aura const* aura = player->GetAura(PunishAura()))", "if (Aura const* aura = nullptr)"),
}


class PunishHarness(unittest.TestCase):
    """B: the module's own functions, compiled against doubles."""

    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("c++") or shutil.which("g++")
        if not cls.compiler:
            raise unittest.SkipTest("no C++ compiler")
        pct, stacks, seconds = punish_values()
        cls.arguments = ["%g" % pct, "%d" % stacks, "%d" % round(seconds * 1000)]

    def build(self, name, text):
        folder = SCRATCH / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "punish_extract.h").write_text(text, encoding="utf-8")
        binary = folder / "punish_harness"
        built = subprocess.run(
            [self.compiler, "-std=c++20", "-O0", "-Wall", "-include", str(HARNESS / "punish_shim.h"),
             "-I", str(folder), "-I", str(HARNESS), "-I", str(MODULE / "src" / "combat"), "-I", str(MODULE / "src" / "classes" / "barbarian"),
             str(HARNESS / "punish_harness.cpp"), "-o", str(binary)],
            capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, "%s did not compile:\n%s" % (name, built.stderr[-6000:]))
        return harness_env.run([str(binary)] + self.arguments, capture_output=True, text=True)

    def test_production_functions(self):
        run = self.build("production", extract())
        self.assertEqual(run.returncode, 0, "a case failed:\n" + run.stderr[-4000:])
        self.assertEqual(run.stdout.strip(), "ok")

    def test_each_old_bug_fails_the_harness(self):
        for name, (old, new) in MUTATIONS.items():
            with self.subTest(mutation=name):
                self.assertEqual(PRIMARIES.count(old), 1, "mutation target %r is gone" % old)
                run = self.build("mutation_" + re.sub(r"\W+", "_", name), extract(PRIMARIES.replace(old, new)))
                self.assertNotEqual(run.returncode, 0, "the harness passed with %r" % name)
                self.assertIn("FAIL:", run.stderr)

    def test_the_cast_applies_it(self):
        """Begin puts the buff on for the Punish rune: "after using Bash"."""
        begin = definition("void Begin()", PRIMARIES)
        self.assertIn("if (row && row->behavior == B::punish)\n                    Punish(player, *row);", begin)


class Tooltips(unittest.TestCase):
    """C: the filled sheets are the applied migrations; nothing unfilled is written."""

    def render(self, root, name):
        spec = generate_sql.TABLES[name]
        path = generate_sql.source_csv(root, name)
        return generate_sql.render_table(path, spec,
                                         source_rows=generate_sql.fill_tooltips(root, name, path, spec))[0]

    def test_filled_render_is_the_applied_migration_byte_for_byte(self):
        for name in generate_sql.TOOLTIP_CELLS:
            with self.subTest(table=name):
                applied = (UPDATES / ("0001_dc_%s.sql" % name)).read_bytes()
                self.assertEqual(self.render(MODULE, name).encode("utf-8"), applied)
                self.assertEqual((GENERATED / ("%s.sql" % name)).read_bytes(), applied)

    def test_the_sheets_really_are_tokenised(self):
        """Otherwise the byte-for-byte test above would prove nothing about filling."""
        for name, (column, *_rest) in generate_sql.TOOLTIP_CELLS.items():
            with (MODULE / "data" / "d3" / ("%s.csv" % name)).open(encoding="utf-8", newline="") as stream:
                cells = [row[column] for row in csv.DictReader(stream)]
            self.assertTrue(any(PLACEHOLDER.search(cell) for cell in cells), name)

    def test_no_committed_output_holds_a_placeholder(self):
        found = []
        for folder in (GENERATED, MODULE / "data" / "sql"):
            for path in sorted(folder.rglob("*")):
                if path.suffix in (".sql", ".csv") and PLACEHOLDER.search(path.read_text(encoding="utf-8",
                                                                                          errors="replace")):
                    found.append(str(path.relative_to(MODULE)))
        self.assertEqual(found, [])

    def test_refuse_placeholders(self):
        generate_sql.refuse_placeholders("clean", "INSERT ... 'Deal 600% weapon damage.'")
        with self.assertRaisesRegex(generate_sql.DataError, r"\{damage_pct\}"):
            generate_sql.refuse_placeholders("dirty", "INSERT ... 'Deal {damage_pct} weapon damage.'")


class TooltipGenerator(unittest.TestCase):
    """C, end to end: the real generate() on a copy of the module's inputs."""

    def setUp(self):
        scratch = REPO / "azerothcore-wotlk" / "build" / "_agent-scratch"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="barbarian-tooltips-", dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(MODULE / "data" / "d3", self.root / "data" / "d3")
        shutil.copytree(MODULE / "data" / "tunables", self.root / "data" / "tunables")
        updates = self.root / "data" / "sql" / "db-world" / "updates"
        updates.mkdir(parents=True)
        # The applied files generate() reads, as test_generate_sql seeds them.
        for frozen in ("0002_dc_base_item.sql", "0002_dc_item_template.sql",
                       "items_0007_unidentified_shells.sql") + generate_sql.CLASS_START_APPLIED:
            shutil.copyfile(UPDATES / frozen, updates / frozen)
        # The three applied tooltip migrations, listed as applied.
        rows = ["path,sha1,provenance"]
        with (MODULE / "data" / "sql" / "applied_migrations.csv").open(encoding="utf-8", newline="") as stream:
            manifest = {row["path"]: row for row in csv.DictReader(stream)}
        for name in generate_sql.TOOLTIP_CELLS:
            key = "db-world/updates/0001_dc_%s.sql" % name
            shutil.copyfile(UPDATES / ("0001_dc_%s.sql" % name), updates / ("0001_dc_%s.sql" % name))
            rows.append("%s,%s,%s" % (key, manifest[key]["sha1"], "fixture: copied from the module manifest"))
        (self.root / "data" / "sql" / "applied_migrations.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")

    def outputs(self):
        return {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob("*.sql")}

    def test_a_run_matches_the_applied_files_and_does_not_warn(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            generate_sql.generate(self.root)
        self.assertNotIn("barbarian", "\n".join(line for line in out.getvalue().splitlines() if "WARNING" in line))
        for name in generate_sql.TOOLTIP_CELLS:
            self.assertEqual((self.root / "data" / "generated" / ("%s.sql" % name)).read_bytes(),
                             (UPDATES / ("0001_dc_%s.sql" % name)).read_bytes())

    def test_an_unstated_token_stops_the_run_before_any_write(self):
        path = self.root / "data" / "d3" / "barbarian_runes.csv"
        text = path.read_text(encoding="utf-8")
        path.write_text(text.replace("{damage_bonus_pct}", "{no_such_token}", 1), encoding="utf-8")
        before = self.outputs()
        with contextlib.redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(generate_sql.DataError, r"\{no_such_token\}"):
            generate_sql.generate(self.root)
        self.assertEqual(self.outputs(), before)

    def test_without_the_fill_nothing_is_written(self):
        """The old writer, put back: tokens reach the render, and the guard refuses it."""
        before = self.outputs()
        saved = dict(generate_sql.TOOLTIP_CELLS)
        generate_sql.TOOLTIP_CELLS.clear()
        try:
            with contextlib.redirect_stdout(io.StringIO()), \
                    self.assertRaisesRegex(generate_sql.DataError, "unfilled placeholders"):
                generate_sql.generate(self.root)
        finally:
            generate_sql.TOOLTIP_CELLS.update(saved)
        self.assertEqual(self.outputs(), before)


if __name__ == "__main__":
    unittest.main()
