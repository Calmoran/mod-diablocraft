"""The source-text guards of tzo krins gaze: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_tzo_krins_gaze.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_tzo_krins_gaze import MODULE  # noqa: E402


WAVE = MODULE / "src/classes/monk/dc_monk_wave_of_light.cpp"


def cast_failures(text):
    """What is wrong with WaveOfLight::Cast in `text` (the source guards; [] when it is right)."""
    start = text.index("void Cast(Player* player, std::uint32_t spellId, Position const& aimed)")
    body = text[start:]
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    flag = 'bool const atEnemy = ItemPowers::SkillSetTo(player, std::string(Skill), "cast_at_enemy", 0) > 0;'
    need("the flag is the item's cast_at_enemy row, read for Wave of Light", flag in body)
    need("the flag is read before any area is struck", flag in body and body.index(flag) < body.index("Combat::Enemies("))
    need("the item powers header is included", '#include "../../combat/dc_item_powers.h"' in text)
    need("the pillar falls at the aimed point with the flag, ahead without it",
         'atEnemy ? Position(aimed) : At(Ahead(monk, heading, Tune("wave_of_light_pillar_offset_yards")), z);' in body)
    need("the bell falls at the aimed point with the flag, Explosive Light too",
         "Position const where = atEnemy     ? Position(aimed)\n                                   : explosive ? At(monk, z)\n" in body)
    need("without the flag the bell is ahead of the Monk",
         ': At(Ahead(monk, heading, Tune("wave_of_light_bell_offset_yards")), z);' in body)
    line = body[body.index('if (rune == "Shattering Light"'):]
    need("Shattering Light's line still runs from the Monk", "atEnemy" not in line and "InLine(monk, heading," in line)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_cast_puts_the_bell_and_pillar_at_the_enemy(self):
        self.assertEqual([], cast_failures(WAVE.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        real = WAVE.read_text(encoding="utf-8")
        mutants = {
            "no_flag": ('ItemPowers::SkillSetTo(player, std::string(Skill), "cast_at_enemy", 0) > 0', "true"),
            "flag_for_another_stat": ('"cast_at_enemy", 0) > 0', '"pierces", 0) > 0'),
            "pillar_ignores_it": ('atEnemy ? Position(aimed) : At(Ahead(monk, heading, Tune("wave_of_light_pillar_offset_yards")), z);',
                                  'At(Ahead(monk, heading, Tune("wave_of_light_pillar_offset_yards")), z);'),
            "bell_ignores_it": ("atEnemy     ? Position(aimed)\n                                   : explosive", "false ? Position(aimed)\n                                   : explosive"),
            "explosive_stays_on_the_monk": ("Position const where = atEnemy     ? Position(aimed)\n                                   : explosive ? At(monk, z)\n",
                                            "Position const where = explosive ? At(monk, z) : atEnemy ? Position(aimed)\n"),
            "bell_always_at_the_aim": (': At(Ahead(monk, heading, Tune("wave_of_light_bell_offset_yards")), z);', ": Position(aimed);"),
            "line_moved_too": ("InLine(monk, heading,", "InLine(atEnemy ? PointOf(aimed) : monk, heading,"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                self.assertTrue(cast_failures(real.replace(old, new)), name + " survived")


if __name__ == "__main__":
    unittest.main()
