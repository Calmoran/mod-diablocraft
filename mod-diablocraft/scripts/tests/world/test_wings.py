"""Check cosmetic semantics, model preservation, DBC isolation and repeatability."""
import hashlib
import io
import json
import shutil
import struct
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import applied_migrations as am
import generate_wings as wings

REAL_ROOT = wings.ROOT


class DbcMergeTests(unittest.TestCase):
    def test_collision_rejected_and_other_duplicate_rows_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "sample.dbc"
            a, b = struct.pack("<2I", 7, 10), struct.pack("<2I", 7, 20)
            path.write_bytes(struct.pack("<4s4I", b"WDBC", 2, 2, 8, 1) + a + b + b"\0")
            dbc = wings.DBC(path, 2)
            with self.assertRaisesRegex(ValueError, "another record"):
                dbc.add([7, 50], set())
            dbc.add([8, "Wings"], set())
            output = dbc.encoded(set())
            self.assertEqual(output[20:36], a + b)
            path.write_bytes(output)
            again = wings.DBC(path, 2)
            again.add([8, "Wings"], {8})
            self.assertEqual(again.encoded({8}), output)

    def test_truncated_input_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "broken.dbc"
            path.write_bytes(struct.pack("<4s4I", b"WDBC", 5, 2, 8, 1) + b"\0")
            with self.assertRaisesRegex(ValueError, "length"):
                wings.DBC(path, 2)


class GeneratedWingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(wings.MANIFEST.read_text(encoding="utf-8"))
        cls.spells = wings.DBC(wings.CLIENT / "Spell.dbc", 234)

    def test_spells_are_visible_permanent_cosmetics(self):
        durations = wings.DBC(wings.BASE / "SpellDuration.dbc", 4)
        for variant in self.manifest["variants"]:
            spell = self.spells.row(int(variant["spell_id"]))
            self.assertFalse(spell[4] & 0x40, "Passive dummy auras are not sent to clients")
            self.assertTrue(spell[7] & 0x00100000, "Aura must survive death")
            self.assertEqual(spell[71:74], [6, 0, 0])
            self.assertEqual(spell[95:98], [4, 0, 0])
            self.assertEqual(spell[86:89], [1, 0, 0])
            self.assertEqual(spell[42:46], [0, 0, 0, 0])
            self.assertEqual(durations.row(spell[40])[1], 0xffffffff)
            self.assertEqual(spell[131], int(variant["visual_id"]))

    def test_stock_carrier_and_project_spells_retained(self):
        self.assertEqual(self.spells.row(43024)[131], 284)
        for ident in range(81000, 81184):
            self.assertTrue(any(struct.unpack_from("<I", r)[0] == ident for r in self.spells.records), ident)

    def test_models_preserve_geometry_animation_skin_and_dependencies(self):
        original = (wings.SOURCE / "D3AngelWing_Red.m2").read_bytes()
        original_skin = (wings.SOURCE / "D3AngelWing_Red00.skin").read_bytes()
        count, textures_offset = struct.unpack_from("<II", original, 80)
        allowed = set(range(8, 16))
        for i in range(count):
            allowed.update(range(textures_offset + i * 16 + 8, textures_offset + i * 16 + 16))
        for variant in self.manifest["variants"]:
            stem = "DCAngelicWing_" + variant["key"]
            model = (wings.ART / (stem + ".m2")).read_bytes()
            self.assertEqual((wings.ART / (stem + "00.skin")).read_bytes(), original_skin)
            self.assertEqual(len(original), sum(1 for _ in zip(original, model)))
            for i, (a, b) in enumerate(zip(original, model)):
                if i not in allowed:
                    self.assertEqual(a, b, f"{stem}: source model byte {i} changed")
            for i in range(count):
                size, location = struct.unpack_from("<II", model, textures_offset + i * 16 + 8)
                name = model[location:location + size].rstrip(b"\0").decode("ascii")
                self.assertTrue(name.startswith(wings.MODEL_PREFIX))
                self.assertTrue((wings.ART / name.split("\\")[-1]).is_file())

    def test_recolors_preserve_all_mip_alpha_and_color_indices(self):
        original = (wings.SOURCE / "D3AngelWing_Red.blp").read_bytes()
        offsets = struct.unpack_from("<16I", original, 20)
        lengths = struct.unpack_from("<16I", original, 84)
        digests = set()
        for variant in self.manifest["variants"]:
            texture = (wings.ART / ("DCAngelicWing_" + variant["key"] + ".blp")).read_bytes()
            self.assertEqual(len(texture), len(original))
            self.assertEqual(texture[:offsets[0]], original[:offsets[0]])
            if variant["recolor_mode"] == "original":
                self.assertEqual(texture, original)
            else:
                self.assertNotEqual(texture, original)
            for offset, length in zip(offsets, lengths):
                for block in range(offset, offset + length, 16):
                    self.assertEqual(texture[block:block + 8], original[block:block + 8], "Alpha changed")
                    self.assertEqual(texture[block + 12:block + 16], original[block + 12:block + 16], "Color indices changed")
            digests.add(hashlib.sha256(texture).hexdigest())
        self.assertEqual(len(digests), len(self.manifest["variants"]))

    def test_invisible_shirts_and_visual_attachment(self):
        items = wings.DBC(wings.CLIENT / "Item.dbc", 8)
        display = wings.DBC(wings.CLIENT / "ItemDisplayInfo.dbc", 25)
        visual = wings.DBC(wings.CLIENT / "SpellVisual.dbc", 32)
        attach = wings.DBC(wings.CLIENT / "SpellVisualKitModelAttach.dbc", 10)
        for variant in self.manifest["variants"]:
            item = items.row(int(variant["item_entry"]))
            self.assertEqual(item[1:3], [4, 0])
            self.assertEqual(item[6], 4)
            appearance = display.row(item[5])
            self.assertTrue(appearance[5])
            self.assertFalse(any(appearance[1:5] + appearance[6:]))
            self.assertEqual(visual.row(int(variant["visual_id"]))[4], int(variant["kit_id"]))
            attachment = attach.row(int(variant["attach_id"]))
            self.assertEqual(attachment[1:4], [int(variant["kit_id"]), int(variant["effect_id"]), 12])

    def test_manifest_matches_assets_and_sql_copies(self):
        for name, digest in self.manifest["asset_sha256"].items():
            self.assertEqual(hashlib.sha256((wings.ART / name).read_bytes()).hexdigest(), digest)
        generated = wings.ROOT / "mod-diablocraft/data/generated/cosmetic_wings.sql"
        update = wings.ROOT / "mod-diablocraft/data/sql/db-world/updates/cosmetics_0001_wings.sql"
        self.assertEqual(generated.read_bytes(), update.read_bytes())


class CompanionMigrationGuardTests(unittest.TestCase):
    """A frozen cosmetics_0001 migration holds every wing client output.

    decisions.md 2026-09-23 (F2): the client DBCs, art, manifest and generated
    mirror are companions of `cosmetics_0001_wings.sql`; they may follow a
    changed sheet only with a new migration carrying the same change.
    """

    LAYOUTS = ("Spell.dbc", "SpellVisual.dbc", "SpellVisualKit.dbc",
               "SpellVisualEffectName.dbc", "SpellVisualKitModelAttach.dbc",
               "Item.dbc", "ItemDisplayInfo.dbc")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            prefix="wings-guard-", dir=REAL_ROOT / "azerothcore-wotlk/build/_agent-scratch")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.saved = {name: getattr(wings, name) for name in
                      ("ROOT", "DATA", "SOURCE", "BASE", "CLIENT", "ART", "MANIFEST")}
        self.addCleanup(self.restore)
        self.client = self.root / "client-patch/dbc"
        self.art = self.root / "client-patch/art/Item/ObjectComponents/Wings/DiabloCraft"
        self.variants = self.root / "mod-diablocraft/data/d3/wing_variants.csv"
        self.mirror = self.root / "mod-diablocraft/data/generated/cosmetic_wings.sql"
        self.migration = self.root / "mod-diablocraft/data/sql/db-world/updates/cosmetics_0001_wings.sql"
        self.authority = self.root / "mod-diablocraft/data/sql/applied_migrations.csv"
        shutil.copytree(REAL_ROOT / "client-patch/source/wings",
                        self.root / "client-patch/source/wings")
        shutil.copyfile(REAL_ROOT / "client-patch/wings-manifest.json",
                        self.root / "client-patch/wings-manifest.json")
        self.client.mkdir(parents=True)
        for name in self.LAYOUTS:
            shutil.copyfile(REAL_ROOT / "client-patch/dbc" / name, self.client / name)
        schema = self.root / "azerothcore-wotlk/data/sql/base/db_world"
        schema.mkdir(parents=True)
        shutil.copyfile(REAL_ROOT / "azerothcore-wotlk/data/sql/base/db_world/spell_dbc.sql",
                        schema / "spell_dbc.sql")
        (self.root / "mod-diablocraft/data/d3").mkdir(parents=True)
        (self.root / "mod-diablocraft/data/sql/db-world/updates").mkdir(parents=True)
        (self.root / "mod-diablocraft/data/generated").mkdir(parents=True)
        shutil.copyfile(REAL_ROOT / "mod-diablocraft/data/d3/wing_variants.csv", self.variants)
        self.write_authority([])
        wings.ROOT = self.root
        wings.DATA = self.variants
        wings.SOURCE = self.root / "client-patch/source/wings"
        wings.BASE = REAL_ROOT / "azerothcore-wotlk/build/server/data/dbc"
        wings.CLIENT = self.client
        wings.ART = self.art
        wings.MANIFEST = self.root / "client-patch/wings-manifest.json"

    def restore(self):
        for name, value in self.saved.items():
            setattr(wings, name, value)

    def write_authority(self, rows):
        lines = ["path,sha1,provenance"] + [",".join(row) for row in rows]
        self.authority.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def run_generate(self, migration=None):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            manifest = wings.generate(migration)
        return manifest, buffer.getvalue()

    def mutate_first_variant_name(self):
        self.variants.write_text(
            self.variants.read_text(encoding="utf-8").replace(
                "Angelic Wings - Original,", "Angelic Wings - Mutated,", 1),
            encoding="utf-8")

    def snapshot(self):
        paths = [p for p in self.client.rglob("*") if p.is_file()]
        paths += [p for p in self.art.rglob("*") if p.is_file()]
        paths += [self.mirror, self.migration, wings.MANIFEST]
        return {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths if p.is_file()}

    def listed(self, digest):
        self.write_authority([["db-world/updates/cosmetics_0001_wings.sql", digest, "test"]])

    def test_unchanged_run_leaves_the_applied_migration_alone(self):
        self.run_generate()
        applied = self.migration.read_bytes()
        self.listed(hashlib.sha1(applied).hexdigest().upper())
        _, output = self.run_generate()
        self.assertNotIn("WARNING", output)
        self.assertEqual(self.migration.read_bytes(), applied)

    def test_frozen_migration_holds_every_companion_output(self):
        self.run_generate()
        applied = self.migration.read_bytes()
        before = self.snapshot()
        self.listed(hashlib.sha1(applied).hexdigest().upper())
        self.mutate_first_variant_name()
        _, output = self.run_generate()
        self.assertIn("WARNING", output)
        self.assertIn("cosmetics_0001_wings.sql", output)
        self.assertEqual(self.snapshot(), before,
                         "a frozen migration must hold every wing companion output")

    def test_new_migration_permits_the_companion_update(self):
        self.run_generate()
        applied = self.migration.read_bytes()
        before = self.snapshot()
        self.listed(hashlib.sha1(applied).hexdigest().upper())
        self.mutate_first_variant_name()
        new_migration = self.root / "mod-diablocraft/data/sql/db-world/updates/cosmetics_0002_wings.sql"
        _, output = self.run_generate(new_migration)
        self.assertNotIn("WARNING", output)
        self.assertEqual(self.migration.read_bytes(), applied,
                         "the applied migration stays frozen")
        self.assertTrue(new_migration.is_file(), "the new migration carries the change")
        self.assertNotEqual(self.snapshot()[self.mirror], before[self.mirror],
                            "the companion mirror follows the new migration")

    def test_a_migration_outside_updates_refuses_before_any_write(self):
        updates = self.root / "mod-diablocraft/data/sql/db-world/updates"
        bad = [self.root / "mod-diablocraft/data/generated/cosmetics_0002_wings.sql",
               self.root / "mod-diablocraft/data/sql/db-world/cosmetics_0002_wings.sql",
               self.root / "mod-diablocraft/data/sql/db-characters/updates/cosmetics_0002_wings.sql",
               updates / "cosmetics_0002_wings.txt",
               updates / "cosmetics_0002_wings",
               updates / "cosmetics_0002_wings.SQL"]
        before = self.snapshot()
        for path in bad:
            with self.subTest(path=path):
                with self.assertRaises(am.CompanionMigrationError):
                    with redirect_stdout(io.StringIO()):
                        wings.generate(path)
                self.assertFalse(path.exists(), "the refused migration was written")
        self.assertEqual(self.snapshot(), before, "a refused migration still published a companion")


if __name__ == "__main__":
    unittest.main()
