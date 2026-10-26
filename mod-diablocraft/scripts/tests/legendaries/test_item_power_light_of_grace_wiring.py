"""The source-text guards of light of grace: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_light_of_grace.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_light_of_grace import SRC  # noqa: E402


COMBAT = SRC / "combat/dc_combat.cpp"


def beam_failures(text):
    """What is wrong with ChannelTargets' single_enemy branch in `text` (the source guards; [] when it is right)."""
    start = text.index("std::vector<Unit*> ChannelTargets(")
    body = text[start:text.index("if (row.Line())", start)]
    wrong = []
    blast = body.index("out.push_back(aim);")
    pierce = body.index("Light of Grace")

    def need(why, ok):
        if not ok:
            wrong.append(why)

    need("the pierce comes after the blast list is built", pierce > blast)
    need("the flag is the item's pierces row, read for the shell's skill", 'ItemPowers::SkillSetTo(player, shell.skill, "pierces", 0) > 0' in body)
    need("Sleet Storm has no beam", 'shell.rune != "Sleet Storm"' in body)
    need("the width is asked of the tunable", body.count('"ray_of_frost_pierce_width_yards"') == 3)
    need("a missing tunable turns it off", 'Tunables::Has("wizard", "ray_of_frost_pierce_width_yards")' in body)
    need("a zero width turns it off", 'Tunables::Get("wizard", "ray_of_frost_pierce_width_yards") > 0)' in body)
    need("the line runs from the player to the aimed enemy", "origin.GetAbsoluteAngle(aim->GetPositionX(), aim->GetPositionY())" in body)
    need("the line is the skill's range long", "row.range,\n                        static_cast<float>(Tunables::Get(" in body)
    need("enemies only", "TARGET_CHECK_ENEMY" in body)
    need("the candidates are within the range", "AreaList(player, info, origin, row.range)" in body)
    need("every unit once", "check(unit) && std::find(out.begin(), out.end(), unit) == out.end()" in body)
    need("the line's units join the blast list", "out.push_back(unit);" in body[pierce:])
    need("the blast is kept", "AreaList(player, info, aim->GetPosition(), row.radius)" in body)
    need("the tunables header is included", '#include "../common/dc_tunables.h"' in text)
    return wrong


class Hooks(unittest.TestCase):
    def test_channel_targets_adds_the_line_to_the_blast(self):
        self.assertEqual([], beam_failures("".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))])))

    def test_the_source_guards_fail_their_mutants(self):
        real = "".join(p.read_text(encoding="utf-8") for p in [COMBAT.parent / "dc_combat_internal.h", *sorted(COMBAT.parent.glob("dc_combat*.cpp"))])
        mutants = {
            "no_flag": ('ItemPowers::SkillSetTo(player, shell.skill, "pierces", 0) > 0', "true"),
            "flag_for_another_stat": ('"pierces", 0) > 0', '"damage_increase_pct", 0) > 0'),
            "sleet_storm_pierces": ('shell.rune != "Sleet Storm" && ', ""),
            "width_a_literal": ('static_cast<float>(Tunables::Get("wizard", "ray_of_frost_pierce_width_yards"))', "4.0f"),
            "no_has_guard": ('Tunables::Has("wizard", "ray_of_frost_pierce_width_yards") &&\n                    ', ""),
            "zero_width_allowed": ('Tunables::Get("wizard", "ray_of_frost_pierce_width_yards") > 0)', 'Tunables::Get("wizard", "ray_of_frost_pierce_width_yards") >= 0)'),
            "heading_from_the_channel": ("origin.GetAbsoluteAngle(aim->GetPositionX(), aim->GetPositionY())", "channel.direction"),
            "friends_too": ("TARGET_CHECK_ENEMY", "TARGET_CHECK_DEFAULT"),
            "units_twice": ("check(unit) && std::find(out.begin(), out.end(), unit) == out.end()", "check(unit)"),
            "line_not_added": ("                            out.push_back(unit);", "                            continue;"),
            "short_line": ("row.range,\n                        static_cast<float>", "row.radius,\n                        static_cast<float>"),
            "blast_dropped": ("AreaList(player, info, aim->GetPosition(), row.radius)", "std::vector<Unit*>{}"),
        }
        start = real.index("std::vector<Unit*> ChannelTargets(")
        end = real.index("if (row.Line())", start)
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real[start:end].count(old), name + " does not apply once to the pierce")
                self.assertTrue(beam_failures(real[:start] + real[start:end].replace(old, new) + real[end:]), name + " survived")


if __name__ == "__main__":
    unittest.main()
