"""Per-hit, per-cast, per-tick and per-spawn logs stay off the default log (brief G1 gaps, task 1).

The worldserver printed two INFO lines on every hit and cast (f97e97a4 leftovers).
These tests read the sources: the hot paths may log at DEBUG on the module logger
only, never INFO or WARN. Each names the change that must make it fail.
"""
import re
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_class_parity import SRC, definition, mutate

COMBAT = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
PRIMARIES = (SRC / "classes/barbarian/dc_barbarian_primaries.cpp").read_text(encoding="utf-8")
SUSTAIN = (SRC / "stats/dc_sustain.cpp").read_text(encoding="utf-8")
DIFFICULTY = (SRC / "difficulty/dc_difficulty.cpp").read_text(encoding="utf-8")
LOUD = re.compile(r"LOG_(INFO|WARN)\s*\(")
# Tags of the lines that fire per hit, cast, tick, spawn or kill.
HOT_TAGS = ("[DC target]", "[DC targets]", "[DC Rend]", "[DC sustain]", "[DC tier creature]")


def loud_tagged(source):
    """(level, tag) of every INFO/WARN call whose text carries a hot-path tag."""
    found = []
    for call in re.finditer(r"LOG_(INFO|WARN)\s*\((.*?)\);", source, re.S):
        found += [(call.group(1), tag) for tag in HOT_TAGS if tag in call.group(2)]
    return found


class HotPathLogs(unittest.TestCase):
    def test_resolve_hit_has_no_info_log(self):
        body = definition(COMBAT, "bool ResolveHit(Player* player, Unit* target")
        self.assertIsNone(LOUD.search(body))
        # Fails when the removed line goes back in.
        put_back = mutate(body, "shell.spellId, target->GetGUID().ToString());",
                          "shell.spellId, target->GetGUID().ToString());LOG_INFO(\"x\",\"y\");")
        self.assertIsNotNone(LOUD.search(put_back))

    def test_hot_tags_are_never_info(self):
        for source in (COMBAT, SUSTAIN, DIFFICULTY):
            self.assertEqual(loud_tagged(source), [])
        self.assertEqual(loud_tagged(COMBAT.replace('LOG_DEBUG("module.dc.combat", "[DC targets]',
                                                    'LOG_INFO("server.loading", "[DC targets]')),
                         [("INFO", "[DC targets]")])

    def test_tier_creature_log_is_debug_and_the_load_lines_stay_info(self):
        # LogCreature fires on every creature spawn and rescale (bead diablocraft-nbw8).
        self.assertIn('LOG_DEBUG("module.dc.combat", "[DC tier creature]', DIFFICULTY)
        put_back = DIFFICULTY.replace('LOG_DEBUG("module.dc.combat", "[DC tier creature]',
                                      'LOG_INFO("server.loading", "[DC tier creature]')
        self.assertEqual(loud_tagged(put_back), [("INFO", "[DC tier creature]")])

    def test_primaries_and_sustain_log_only_at_debug(self):
        for source in (PRIMARIES, SUSTAIN):
            self.assertIsNone(LOUD.search(source))
        self.assertIsNotNone(LOUD.search(PRIMARIES.replace("LOG_DEBUG(", "LOG_INFO(", 1)))


if __name__ == "__main__":
    unittest.main()
