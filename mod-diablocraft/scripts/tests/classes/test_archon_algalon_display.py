"""Archon form wears Algalon the Observer at a player's size, from the first frame (diablocraft-ie3xd, ruling 2026-10-11/12).

  * client-patch/dbc/build_creaturedisplayinfo.py is driven on the stock table and the sheet's Archon rows: the stock rows byte for
    byte, the string block unchanged, and one row at form_display_id that is display_id's row with its display scale times scale;
    the committed CreatureDisplayInfo.dbc is that build; it refuses a stock id, a missing source, a scale that is no shrink;
  * the generated server numbers: form_display_id on Archon's record and every rune (exact rows, inherited), and nothing else of the
    look (display_id and scale reach only the client builder);
  * the module: EnterArchon swaps the display id only (no scale argument), LeaveArchon restores, both from the aura's own apply and
    removal, and the Archon records do not outlive death;
  * the core path the size rests on, pinned: SetDisplayId sets the object scale to its default 1, and a float field that keeps its
    value sends nothing, so at scale 1 the morph is one display id change and no scale change the client could tween.
The look and the instant size are the designer's checks on dev (docs/test-diablocraft-ie3xd.md).
"""
import importlib.util
import struct
import unittest
from pathlib import Path
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import wizard_source  # noqa: E402

import test_spell_records as records

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
BUILDER = REPO / "client-patch/dbc/build_creaturedisplayinfo.py"
CORE = REPO / "azerothcore-wotlk/src/server"
ARCHON = (83124, 83246, 83247, 83248, 83249, 83250)

spec = importlib.util.spec_from_file_location("build_creaturedisplayinfo", BUILDER)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def table(data):
    count, _, size, _ = struct.unpack_from("<IIII", data, 4)
    body = data[20:20 + count * size]
    return {struct.unpack_from("<I", body, i * size)[0]: body[i * size:(i + 1) * size] for i in range(count)}, data[20 + count * size:]


@unittest.skipUnless(builder.STOCK.is_file(), "no stock CreatureDisplayInfo.dbc on this machine")
class ClientRow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = builder.STOCK.read_bytes()
        cls.rows = builder.archon_rows()

    def test_the_sheet_carries_alexs_numbers(self):
        self.assertEqual(("29553", "0.2", "33000"), (self.rows["display_id"], self.rows["scale"], self.rows["form_display_id"]))

    def test_one_row_added_from_the_source_at_its_shrunk_size(self):
        before, strings = table(self.stock)
        after, built_strings = table(builder.build(self.stock, self.rows))
        self.assertEqual(strings, built_strings)
        self.assertEqual({k: before[k] for k in before}, {k: after[k] for k in before}, "every stock row byte for byte")
        self.assertEqual([33000], sorted(set(after) - set(before)))
        source, form = before[29553], after[33000]
        self.assertEqual([0, 4], [i for i in range(16) if source[i * 4:i * 4 + 4] != form[i * 4:i * 4 + 4]], "only the id and the scale")
        self.assertAlmostEqual(struct.unpack_from("<f", source, 16)[0] * 0.2, struct.unpack_from("<f", form, 16)[0], places=5)
        model = struct.unpack_from("<I", form, 4)[0]
        self.assertEqual(struct.unpack_from("<I", before[28641], 4)[0], model, "Algalon the Observer's own model (32871 wears 28641)")

    def test_the_committed_file_is_the_build(self):
        self.assertEqual(builder.build(self.stock, self.rows), builder.OUT.read_bytes())

    def test_it_refuses_what_it_cannot_stand_behind(self):
        for bad in ({"form_display_id": "29553"}, {"form_display_id": "32999"}, {"display_id": "40000"}, {"scale": "1.5"}, {"scale": "0"}):
            with self.assertRaises(SystemExit, msg=bad):
                builder.build(self.stock, dict(self.rows, **bad))


class ServerSide(unittest.TestCase):
    def test_the_form_id_is_on_archon_and_every_rune_and_nothing_else_of_the_look(self):
        header = (MODULE / "src/combat/dc_spell_values.h").read_text(encoding="utf-8")
        for spell in ARCHON:
            origin = "Own" if spell == 83124 else "Inherited"
            self.assertIn('{%d, "form_display_id", "", Source::Exact, %d, 0, Origin::%s, 83124},' % (spell, spell, origin), header)
        sql = (MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8")
        for spell in ARCHON:
            self.assertIn("(%d,'form_display_id','',33000)" % spell, sql)
        self.assertNotIn("'display_id'", sql)
        self.assertNotIn("(83124,'scale'", sql)

    def test_enter_swaps_the_display_only_and_leave_restores(self):
        wizard = wizard_source.CPP.read_text(encoding="utf-8")
        enter = wizard[wizard.index("void EnterArchon(Player* player, uint32 form)"):wizard.index("void LeaveArchon(")]
        self.assertIn('player->SetDisplayId(uint32(Num(form, "form_display_id")));', enter)
        self.assertNotIn("SetObjectScale", enter)
        leave = wizard[wizard.index("void LeaveArchon(Player* player)"):wizard.index("} // namespace DC::Combat::Wizard::Archon")]
        self.assertIn("player->RestoreDisplayId();", leave)
        applied = wizard[wizard.index("void Applied(AuraEffect const*, AuraEffectHandleModes)"):wizard.index("void Removed(AuraEffect const*")]
        self.assertIn('if (IsSkill(id, "Archon"))\n                    Archon::EnterArchon(player, id);', applied)
        removed = wizard[wizard.index("void Removed(AuraEffect const*"):wizard.index("void Register() override", wizard.index("void Removed(AuraEffect const*"))]
        self.assertIn('if (IsSkill(id, "Archon"))\n                    Archon::LeaveArchon(player);', removed)

    def test_death_takes_the_aura(self):
        names, spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), every_class=True)
        for spell in ARCHON:
            self.assertFalse(int(spells[spell][names.index("AttributesEx3")]) & 0x00100000, "%d: SPELL_ATTR3_ALLOW_AURA_WHILE_DEAD" % spell)

    @unittest.skipUnless((CORE / "game/Entities/Unit/Unit.cpp").is_file(), "no core source")
    def test_the_core_sends_no_scale_when_it_keeps_its_value(self):
        unit_h = (CORE / "game/Entities/Unit/Unit.h").read_text(encoding="utf-8")
        self.assertIn("virtual void SetDisplayId(uint32 modelId, float displayScale = 1.f);", unit_h)
        self.assertNotIn("SetObjectScale", unit_h, "Unit does not override the base SetObjectScale")
        unit = (CORE / "game/Entities/Unit/Unit.cpp").read_text(encoding="utf-8")
        display = unit[unit.index("void Unit::SetDisplayId(uint32 modelId, float displayScale /*=1.f*/)"):unit.index("void Unit::RestoreDisplayId()")]
        self.assertIn("SetUInt32Value(UNIT_FIELD_DISPLAYID, modelId);", display)
        self.assertIn("SetObjectScale(displayScale);", display)
        obj_h = (CORE / "game/Entities/Object/Object.h").read_text(encoding="utf-8")
        self.assertIn("virtual void SetObjectScale(float scale) { SetFloatValue(OBJECT_FIELD_SCALE_X, scale); }", obj_h)
        obj = (CORE / "game/Entities/Object/Object.cpp").read_text(encoding="utf-8")
        setter = obj[obj.index("void Object::SetFloatValue(uint16 index, float value)"):]
        setter = setter[:setter.index("\n}\n")]
        self.assertIn("if (m_floatValues[index] != value)", setter)


if __name__ == "__main__":
    unittest.main()
