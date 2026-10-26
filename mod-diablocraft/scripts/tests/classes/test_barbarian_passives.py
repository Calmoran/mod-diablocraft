"""The Barbarian's passives live in src/classes/barbarian/dc_barbarian_passives.cpp (R1), and the shared passive code reaches them.

combat/dc_passives.cpp keeps what every class's passives share (Has, Invalidate, the gear auras, the gems' and items' share of a
hit and a hit taken) and asks the Barbarian's file for the rest through dc_barbarian_passives.h. A call dropped from that seam
compiles and runs, and the passives behind it go quiet: these pin each call in the function it belongs to.

Run from anywhere: `python3 mod-diablocraft/scripts/tests/classes/test_barbarian_passives.py`.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import barbarian_source  # noqa: E402

SRC = Path(__file__).resolve().parents[3] / "src"
SHARED = SRC / "combat" / "dc_passives.cpp"
HEADER = barbarian_source.FOLDER / "dc_barbarian_passives.h"


def body(text, marker):
    """The braces-balanced body that follows `marker`, which must be in `text` once."""
    assert text.count(marker) == 1, "%r is not in the source exactly once" % marker
    start = text.index("{", text.index(marker))
    depth, end = 1, start + 1
    while depth:
        depth += (text[end] == "{") - (text[end] == "}")
        end += 1
    return text[start:end]


class Seam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = SHARED.read_text(encoding="utf-8")
        cls.barbarian = barbarian_source.PASSIVES.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")

    def test_the_shared_code_calls_the_barbarian_where_it_did_its_work(self):
        self.assertIn("Barbarian::RegisterScripts();", body(self.shared, "void RegisterScripts()"))
        self.assertIn("Barbarian::Changed(p);", body(self.shared, "void Invalidate(Player* p)"))
        self.assertIn("Barbarian::Hit(p, target);", body(self.shared, "void Hit(Player* p, Unit* target, uint32 spellId, unsigned school)"))
        self.assertIn("Barbarian::Taken(p, school, ranged);", body(self.shared, "void Taken(Player* p, unsigned school, bool ranged, double damage)"))

    def test_the_barbarian_registers_its_three_scripts(self):
        register = body(self.barbarian, "void RegisterScripts()")
        for script in ("new World();", "new Events();", "new Update();"):
            self.assertIn(script, register)

    def test_a_change_marks_the_barbarian_state_for_the_next_update(self):
        self.assertIn(".dirty = true;", body(self.barbarian, "void Changed(Player* p)"))
        update = body(self.barbarian, "void OnPlayerUpdate(Player* p, uint32 diff) override")
        self.assertRegex(update, r"if \(sig != s\.signature \|\| s\.dirty\)\s*\{\s*s\.signature = sig;\s*Refresh\(p\);")

    def test_the_seam_is_declared_once_and_defined_in_the_class(self):
        for name in ("RegisterScripts", "Changed", "Hit", "Taken"):
            self.assertRegex(self.header, r"\bvoid %s\(" % name)
        self.assertIn("namespace DC::Combat::Passives::Barbarian", self.header)
        self.assertIn("    namespace Barbarian\n", self.barbarian)
        self.assertIn('#include "../classes/barbarian/dc_barbarian_passives.h"', self.shared)

    def test_the_shared_file_keeps_no_barbarian_state(self):
        for gone in ("contributors", "allyClock", "weaponTypes", "drApplied", "CLASS_WARRIOR", "WorldScript", "UnitScript"):
            self.assertNotIn(gone, self.shared)
        self.assertNotRegex(self.shared, r"\bdirty\b")


if __name__ == "__main__":
    unittest.main(verbosity=2)
