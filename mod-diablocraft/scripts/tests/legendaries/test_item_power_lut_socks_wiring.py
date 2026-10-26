"""The source-text guards of lut socks: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_lut_socks.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_lut_socks import SRC  # noqa: E402


POWERS = item_powers_source.CPP


def body(text, start, end):
    at = text.index(start)
    return text[at:text.index(end, at)]


class Hooks(unittest.TestCase):
    def check(self, powers=None):
        """The guards on the text of ItemPowers::Cast, the window helpers and the logout hook; raises AssertionError on a mutant."""
        text = POWERS.read_text(encoding="utf-8") if powers is None else powers
        cast = body(text, "void Cast(Player* player, std::uint32_t spellId)", "// The yards are read the way DistanceFactor reads them")
        assert 'SkillSetTo(player, skill, "reuse_casts", 0)' in text and 'SkillSetTo(player, skill, "reuse_window_seconds", 0)' in text, "both numbers are read"
        assert re.search(r"if \(ReuseCast\(player, spellId, skill->skill\)\)\s*return;", cast), "a cast the window keeps open takes no In-geom cut"
        assert cast.index("ReuseCast(") < cast.index("CooldownCut(player)"), "the window is looked at before the cooldown is cut"
        cut = body(text, "double CooldownCut(", "void StartCooldown(")
        assert '"cooldown_reduction_seconds"' in cut and "ItemPower::PlayerSum(" in cut, "the In-geom seconds, in one place"
        start = body(text, "void StartCooldown(", "void ReuseEnded(")
        assert "Combat::SkillCooldownMilliseconds(player, spellId)" in start and "CooldownCut(player)" in start, "the cooldown is the skill's own, cut as In-geom cuts it"
        assert "Combat::SendSkillCooldown(player, spellId," in start, "installed on every rune of the skill"
        ended = body(text, "void ReuseEnded(", "bool ReuseCast(")
        assert "ItemPower::ReuseEnded(" in ended and "StartCooldown(player, spellId);" in ended, "the end installs the cooldown"
        reuse = body(text, "bool ReuseCast(", "void ReuseLogout(")
        assert "Combat::SendSkillCooldown(player, spellId, 0);" in reuse, "the cooldown the core just installed is cleared"
        assert "ItemPower::ReuseCast(" in reuse and "m_Events.AddEventAtOffset(" in reuse, "the rule decides and the end is scheduled"
        assert re.search(r"if \(step\.opened\)", reuse), "only the cast that opens the window schedules its end"
        assert "step.token" in reuse and "Milliseconds(" in reuse, "the end event carries its window's token and the window's length"
        logout_fn = body(text, "void ReuseLogout(", "void StandStill(")
        assert "StartCooldown(player, spellId);" in logout_fn, "a window still open at logout installs the cooldown"
        assert "PLAYERHOOK_ON_BEFORE_LOGOUT" in text and "void OnPlayerBeforeLogout(Player* player) override" in text, "a logout inside the window"
        hook = body(text, "void OnPlayerBeforeLogout(Player* player) override", "void OnPlayerLogout(Player* player) override")
        assert "ReuseLogout(player);" in hook, "before the character is saved"

    def test_the_cast_keeps_the_skill_open_and_the_end_and_logout_install_the_cooldown(self):
        self.check()

    def test_the_guards_fail_their_mutants(self):
        real = POWERS.read_text(encoding="utf-8")
        mutants = {
            "cut_taken_on_an_open_window": real.replace("if (ReuseCast(player, spellId, skill->skill))\n            return;\n", "ReuseCast(player, spellId, skill->skill);\n", 1),
            "cooldown_not_cleared": real.replace("Combat::SendSkillCooldown(player, spellId, 0);", "", 1),
            "end_not_scheduled": real.replace("m_Events.AddEventAtOffset([player, spellId, skill, token", "m_Events.AddEventAtOffsetX([player, spellId, skill, token", 1),
            "every_cast_schedules_an_end": real.replace("if (step.opened)", "if (true)", 1),
            "end_without_token": real.replace("step.token", "0", 1),
            "end_installs_nothing": real.replace("StartCooldown(player, spellId);", "", 1),
            "logout_installs_nothing": real.replace("for (std::uint32_t spellId : open)\n                StartCooldown(player, spellId);", "", 1),
            "end_forgets_the_in_geom_cut": real.replace("double const cut = CooldownCut(player) * 1000.0;", "double const cut = 0;", 1),
            "one_number_read": real.replace('SkillSetTo(player, skill, "reuse_window_seconds", 0)', "2.0", 1),
            "no_logout_hook": real.replace("PLAYERHOOK_ON_BEFORE_LOGOUT", "PLAYERHOOK_ON_LOGOUT", 1),
            "logout_forgets_the_window": real.replace("ReuseLogout(player);", "", 1),
        }
        for name, mutant in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, mutant, name + " did not apply")
                with self.assertRaises((AssertionError, ValueError), msg=name + " survived"):
                    self.check(mutant)


if __name__ == "__main__":
    unittest.main()
