"""Whirlwind spins with the warrior Bladestorm visual (diablocraft-vz49.3, ruling 2026-10-11, brief hold-to-channel-2026-10-11 bead 3).

Whirlwind's six records (81004, 81043-81047) carry stock Bladestorm's (46924) SpellVisualID_1 and _2, read from the stock Spell.dbc here as the
generator reads them, in the generated SQL and, when it is built, the client Spell.dbc. Nothing else of a record moved for it: the six records still
share every visual field, so a rune keeps what sets it apart (its school, the module's Dust Devils). The look itself is the designer's check on dev
(docs/test-diablocraft-vz49.3.md).
"""
import struct
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_spells
import test_spell_records as records

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
WHIRLWIND = (81004, 81043, 81044, 81045, 81046, 81047)
VISUALS = ("SpellVisualID_1", "SpellVisualID_2")


class Bladestorm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (generate_spells.DBC / "Spell.dbc").is_file():
            raise unittest.SkipTest("no stock Spell.dbc on this machine")
        cls.names, cls.spells = records.parse((MODULE / "data/generated/spell_shells.sql").read_text(encoding="utf-8"), every_class=True)
        stock, _, _, _ = generate_spells.load_dbc("Spell.dbc")
        cls.storm = tuple(struct.unpack_from("<I", stock[46924], cls.names.index(c) * 4)[0] for c in VISUALS)

    def test_the_six_records_carry_bladestorms_visual(self):
        self.assertNotEqual((0, 0), self.storm, "46924 states a visual")
        for spell in WHIRLWIND:
            self.assertEqual(self.storm, tuple(int(self.spells[spell][self.names.index(c)]) for c in VISUALS), spell)

    def test_no_other_shell_took_it(self):
        index = self.names.index("SpellVisualID_1")
        # The Monk's Sweeping Wind (83663 and its rune, 3mk78) wears Bladestorm by monk_visuals.csv; its block starts at 83650.
        wearing = sorted(s for s, row in self.spells.items() if int(row[index]) == self.storm[0] and s < 83650)
        self.assertEqual(list(WHIRLWIND), wearing)

    def test_the_client_spell_dbc_carries_it_when_built(self):
        dbc = REPO / "client-patch/dbc/Spell.dbc"
        if not dbc.is_file():
            self.skipTest("client Spell.dbc not built here")
        data = dbc.read_bytes()
        count, _, size = struct.unpack_from("<III", data, 4)
        body = data[20:20 + count * size]
        rows = {struct.unpack_from("<I", body, i * size)[0]: body[i * size:(i + 1) * size] for i in range(count)}
        for spell in WHIRLWIND:
            self.assertEqual(self.storm, tuple(struct.unpack_from("<I", rows[spell], self.names.index(c) * 4)[0] for c in VISUALS), spell)


if __name__ == "__main__":
    unittest.main()
