"""The source-text guards of eye of peshkov: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_eye_of_peshkov.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_gesture_of_orpheus import BLANK, MATH, T, read_csv
from test_item_power_gesture_of_orpheus_wiring import COMBAT, POWERS, reader_failures
from test_item_power_eye_of_peshkov import MODULE  # noqa: E402


def records():
    """{spell id: (RecoveryTime, CategoryRecoveryTime)} of every Breath of Heaven shell, from the newest migration holding its record."""
    shells = [int(m[1]) for m in re.finditer(r'\{(\d+), "Breath of Heaven", "[^"]*", [\d.]+\}', (MODULE / "src/combat/dc_spell_shells.h").read_text(encoding="utf-8"))]
    out = {}
    for path in sorted((MODULE / "data/sql/db-world/updates").glob("combat_*.sql")):
        text = path.read_text(encoding="utf-8")
        for insert in re.finditer(r"INSERT INTO `spell_dbc` \(([^)]*)\) VALUES\s*\n?(.*?);\n", text, re.S):
            cols = [c.strip(" `") for c in insert[1].split(",")]
            for spell in shells:
                row = re.search(r"\(%d,([^']*)" % spell, insert[2])
                if row:
                    cells = [str(spell)] + row[1].split(",")
                    out[spell] = (int(cells[cols.index("RecoveryTime")]), int(cells[cols.index("CategoryRecoveryTime")]))
    return shells, out


class Hooks(unittest.TestCase):
    def test_the_readers_apply_the_factor(self):
        self.assertEqual([], reader_failures(COMBAT.read_text(encoding="utf-8"), POWERS.read_text(encoding="utf-8")))

    def test_every_breath_of_heaven_shell_states_its_cooldown(self):
        # ItemPowers::Cast cuts only a cooldown the record states, and SkillCooldownMilliseconds reads RecoveryTime: the skill and its five runes
        shells, found = records()
        self.assertEqual(6, len(shells))
        self.assertEqual({spell: (15000, 15000) for spell in shells}, found)

    def test_the_monk_code_starts_no_cooldown_of_its_own(self):
        for path in (MODULE / "src/classes/monk").glob("dc_monk_breath_of_heaven*"):
            with self.subTest(path=path.name):
                self.assertNotRegex(path.read_text(encoding="utf-8"), r"(?i)cooldown")


if __name__ == "__main__":
    unittest.main()
