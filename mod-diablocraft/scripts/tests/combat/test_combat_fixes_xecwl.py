"""diablocraft-xecwl (the designer's Queue batches of 2026-10-11, Combat items).

Whirlwind keeps channelling through another cast; Blizzard reaches 45 yards, D3's own number; the Barbarian learns
the stock Dual Wield; an open character screen redraws when a gem changes the sheet (Esoteric Alteration).
"""
import csv
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_sql  # noqa: E402

ROOT = Path(__file__).resolve().parents[4]
MODULE = ROOT / "mod-diablocraft"
SHELLS_SQL = MODULE / "data/generated/spell_shells.sql"
MIGRATION = MODULE / "data/sql/db-world/updates/combat_0055_whirlwind_blizzard_shells.sql"
SERVER_DBC = ROOT / "azerothcore-wotlk/build/server/data/dbc"
CORE = ROOT / "azerothcore-wotlk/src/server"
MPQ = ROOT / "client-patch/patch-4.MPQ"
D3_CORE2 = ROOT / "reference/blizzless-diiis/src/DiIiS-NA/DataBase/MPQ/Core2.mpq"
ALLOW_ACTION_DURING_CHANNEL = 0x1  # SharedDefines.h SPELL_ATTR5_ALLOW_ACTION_DURING_CHANNEL
ATTRIBUTES_EX5, RANGE_INDEX, EFFECT_1, FAMILY = 9, 46, 71, 208  # Spell.dbc 3.3.5a field indices
ATTACK_RADIUS = 329808  # D3 PowerKeys.AttackRadius


def spell_rows(sql):
    """{id: (name, AttributesEx5, RangeIndex)} from the spell_dbc INSERT."""
    columns = [c.strip(" `") for c in re.search(r"INSERT INTO `spell_dbc` \((.*?)\) VALUES", sql)[1].split(",")]
    at = {name: i for i, name in enumerate(columns)}
    rows = {}
    for match in re.finditer(r"^\((\d+),(.*)\)[,;]$", sql, re.M):
        values = re.findall(r"'(?:[^'\\]|\\.)*'|[^,]+", match[0][1:-2])
        rows[int(values[0])] = (values[at["Name_Lang_enUS"]].strip("'"), int(values[at["AttributesEx5"]]),
                                int(values[at["RangeIndex"]]))
    return rows


def dbc_records(data):
    _, count, fields, size, _ = struct.unpack("<4sIIII", data[:20])
    return {struct.unpack_from("<I", data, 20 + i * size)[0]: struct.unpack_from("<%dI" % fields, data, 20 + i * size)
            for i in range(count)}


def extract(archive, name, into):
    subprocess.run(["smpq", "-x", str(archive), name], cwd=into, check=True, capture_output=True)
    return (Path(into) / name.replace("\\", "/")).read_bytes()


def general_formulas(pow_bytes):
    """{tag: formula text} of a D3 .pow's General tag map (the layout PowerKeys reads)."""
    offset, size = struct.unpack_from("<ii", pow_bytes, 96 + 16)
    out = {}
    if size <= 0:
        return out
    cursor = offset + 16
    count = struct.unpack_from("<i", pow_bytes, cursor)[0]
    cursor += 4
    for _ in range(count):
        kind, tag = struct.unpack_from("<ii", pow_bytes, cursor)
        cursor += 8
        if kind == 4:
            header = struct.unpack_from("<8i", pow_bytes, cursor)
            cursor += 32
            end = pow_bytes.index(b"\0", cursor)
            out[tag] = pow_bytes[cursor:end].decode("latin1")
            cursor = end + 1 + (4 - header[5] % 4) % 4 + header[7]
        else:
            cursor += 4
    return out


class Whirlwind(unittest.TestCase):
    def test_only_whirlwind_allows_an_action_during_its_channel(self):
        rows = spell_rows(SHELLS_SQL.read_text(encoding="utf-8"))
        flagged = {i for i, (_, ex5, _) in rows.items() if ex5 & ALLOW_ACTION_DURING_CHANNEL}
        # The castable records: the skill and its five runes (the manifest's ability_aura markers are not cast).
        with (MODULE / "data/generated/spell_shells.csv").open(encoding="utf-8") as stream:
            whirlwind = {int(row["spell_id"]) for row in csv.DictReader(stream)
                         if row["name"].split(" - ")[0] == "Whirlwind" and row["kind"] in ("active", "rune")}
        self.assertEqual(len(whirlwind), 6)
        self.assertEqual(flagged, whirlwind)

    def test_the_migration_is_the_generated_render(self):
        # A later spell migration rerenders the whole range (combat_0056, diablocraft-lm0si), so the bytes move on;
        # every record 0055 carries keeps the render's name, AttributesEx5 and RangeIndex.
        migration = spell_rows(MIGRATION.read_text(encoding="utf-8"))
        render = spell_rows(SHELLS_SQL.read_text(encoding="utf-8"))
        self.assertEqual(migration, {i: render[i] for i in migration})

    @unittest.skipUnless(shutil.which("smpq"), "smpq is not installed")
    def test_the_client_patch_agrees(self):
        server = spell_rows(SHELLS_SQL.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as folder:
            client = dbc_records(extract(MPQ, "DBFilesClient\\Spell.dbc", folder))
        for identifier, (name, ex5, range_index) in server.items():
            self.assertEqual((client[identifier][ATTRIBUTES_EX5], client[identifier][RANGE_INDEX]), (ex5, range_index),
                             name)

    def test_the_core_keeps_such_a_channel_through_a_cast(self):
        unit = (CORE / "game/Entities/Unit/Unit.cpp").read_text(encoding="utf-8")
        generic = unit[unit.index("case CURRENT_GENERIC_SPELL:"):unit.index("case CURRENT_CHANNELED_SPELL:")]
        self.assertIn("if (!s->GetSpellInfo()->IsActionAllowedChannel())", generic)
        info = (CORE / "game/Spells/SpellInfo.cpp").read_text(encoding="utf-8")
        self.assertIn("return IsChanneled() && HasAttribute(SPELL_ATTR5_ALLOW_ACTION_DURING_CHANNEL);", info)
        defines = (CORE / "shared/SharedDefines.h").read_text(encoding="utf-8")
        self.assertRegex(defines, r"SPELL_ATTR5_ALLOW_ACTION_DURING_CHANNEL\s*= 0x00000001")

    def test_the_module_no_longer_stops_it_on_another_cast(self):
        combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])
        start = combat.index("void OnSpellCast(Spell* spell, Unit* caster, SpellInfo const* info, bool) override")
        body = combat[start:combat.index("void OnSpellCheckCast", start)]
        self.assertNotIn("StopWhirlwind", body)


class Blizzard(unittest.TestCase):
    def test_every_blizzard_shell_reaches_45_yards(self):
        sql = SHELLS_SQL.read_text(encoding="utf-8")
        blizzard = {i: r for i, r in spell_rows(sql).items() if r[0].split(" - ")[0] == "Blizzard"}
        self.assertEqual(len(blizzard), 6)
        ranges = dbc_records((SERVER_DBC / "SpellRange.dbc").read_bytes())
        for identifier, (name, _, range_index) in blizzard.items():
            self.assertEqual(struct.unpack("<f", struct.pack("<I", ranges[range_index][4]))[0], 45.0, name)
            self.assertIn("INSERT INTO dc_spell_targeting VALUES (%d,'ground_area','NUMERIC',45.0,12.0,0.0);"
                          % identifier, sql)

    @unittest.skipUnless(shutil.which("smpq") and D3_CORE2.is_file(), "D3's Core2.mpq or smpq is missing")
    def test_45_is_d3s_attack_radius(self):
        with tempfile.TemporaryDirectory() as folder:
            power = extract(D3_CORE2, "Power\\Wizard_Blizzard.pow", folder)
        self.assertEqual(general_formulas(power)[ATTACK_RADIUS], "45")


class DualWield(unittest.TestCase):
    def test_the_barbarian_and_the_monk_learn_it(self):
        profiles = generate_sql.class_start_rows(MODULE / "data/d3/class_starts.csv")
        holders = {cid for cid, p in profiles.items() if {"spell_id": 674, "skill_id": 118} in p["skills"]}
        self.assertEqual(holders, {1, 12})  # the Monk joined 2026-10-12 (the designer: just dual fist weapons)

    def test_its_migration_runs_after_world_0021(self):
        text = (MODULE / "data/sql/db-world/updates" / generate_sql.CLASS_START_MIGRATION).read_text(encoding="utf-8")
        self.assertEqual(text, (MODULE / "data/generated/class_starts.sql").read_text(encoding="utf-8"))
        self.assertIn("INSERT INTO dc_class_start_skill VALUES (1,674,118);", text)
        self.assertNotIn("ALTER TABLE", text)  # world_0021 added those columns; a second ALTER fails

    def test_674_is_the_stock_dual_wield_and_survives_the_class_sweep(self):
        spell = dbc_records((SERVER_DBC / "Spell.dbc").read_bytes())[674]
        self.assertEqual(spell[EFFECT_1], 40)  # SPELL_EFFECT_DUAL_WIELD
        self.assertEqual(spell[FAMILY], 0)     # IsClassSpell strips only the class's own family


class EsotericSheet(unittest.TestCase):
    def test_a_changed_gem_sheet_is_pushed_to_the_screen(self):
        gems = (MODULE / "src/combat/dc_gem_powers.cpp").read_text(encoding="utf-8")
        start = gems.index("void Sync(Player* player, int wreath = -1)")
        body = gems[start:gems.index("void SetControlImmunity", start)]
        self.assertLess(body.index("if (want == before)"), body.index("Inventory::PushSheet(player);"))
        self.assertLess(body.index("publish(Stat::SingleResistance"), body.index("Inventory::PushSheet(player);"))


if __name__ == "__main__":
    unittest.main()
