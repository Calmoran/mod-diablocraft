"""The source-text guards of rabid strike: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_rabid_strike.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_item_power_rabid_strike import EPIPHANY, MODULE  # noqa: E402


MONK = MODULE / "src/classes/monk/dc_monk.cpp"


PALM = MODULE / "src/classes/monk/dc_monk_exploding_palm.cpp"


COMBAT = MODULE / "src/combat/dc_combat.cpp"


def wiring_failures(epiphany, monk, palm, combat):
    """What is wrong with the copy's wiring (the source guards; [] when it is right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    dash = epiphany[epiphany.index("bool Dash(Player* player, std::uint32_t spellId, Unit* target)"):]
    dash = dash[:dash.index("\n    }\n")]
    teleport = "player->NearTeleportTo("
    call = "MimicNearby(player, spellId, target);"
    need("the copy comes after the teleport", call in dash and teleport in dash and dash.index(teleport) < dash.index(call))
    helper = epiphany[epiphany.index("void MimicNearby(Player* player, std::uint32_t spellId, Unit* target)"):]
    helper = helper[:helper.index("\n        }\n")]
    read = 'double const mimic = ItemPowers::SkillSetTo(player, std::string(Skill), "mimic_damage_pct", 0);'
    need("the copy reads the item's roll", read in helper)
    need("only a Spirit spender is copied", 'if (!Mimics(mimic, Numbers::Num(spellId, "cost_resource")))' in helper)
    need("nearby is the tunable around the Monk",
         'Combat::Enemies(player, spellId, player->GetPosition(), Tune("rabid_strike_search_radius_yards"))' in helper)
    need("the dash's own target is marked", "if (enemy == target)\n                    primary = int(distances.size());" in helper)
    need("the copy's enemy is MimicTarget's", "int const pick = MimicTarget(distances, primary);" in helper)
    set_factor = "factor = before * MimicFactor(mimic);"
    copy = "Monk::Mimic(player, spellId, near[std::size_t(pick)]);"
    reset = "factor = before;"
    need("the copy runs under the multiplier and puts it back",
         all(s in helper for s in (set_factor, copy, reset)) and helper.index(set_factor) < helper.index(copy) < helper.rindex(reset))
    mimic = monk[monk.index("void Mimic(Player* player, std::uint32_t spellId, Unit* target)"):]
    mimic = mimic[:mimic.index("\n    }\n")]
    need("Exploding Palm's copy is its palm", "if (ExplodingPalm::Is(spellId))\n            return ExplodingPalm::Cast(player, spellId, {target});" in mimic)
    need("another skill's copy is its own hit", "Combat::Strike(player, target, spellId, pct);" in mimic)
    need("the copy never dashes (no Begin, no Dash)", "Begin(" not in mimic and "Dash(" not in mimic)
    need("the hit's legendary term takes the copy's multiplier", 'ItemPowers::DealtFactor(player) * CopyFactor();' in combat)
    need("the multiplier is per thread", "thread_local double factor = 1.0;" in combat)
    need("the palm's run takes the multiplier into its ticks", "double const pct = TickPct(totalPct, ticks) * Combat::CopyFactor();" in palm)
    return wrong


class Hooks(unittest.TestCase):
    def texts(self):
        return [p.read_text(encoding="utf-8") for p in (EPIPHANY, MONK, PALM, COMBAT)]

    def test_the_wiring_is_right(self):
        self.assertEqual([], wiring_failures(*self.texts()))

    def test_the_source_guards_fail_their_mutants(self):
        real = self.texts()
        mutants = {
            "no_read": (0, '"mimic_damage_pct", 0);', '"damage_increase_pct", 0);'),
            "any_skill": (0, 'if (!Mimics(mimic, Numbers::Num(spellId, "cost_resource")))', "if (!Mimics(mimic, 1))"),
            "around_the_target": (0, 'Combat::Enemies(player, spellId, player->GetPosition(), Tune("rabid_strike_search_radius_yards"))',
                                  'Combat::Enemies(player, spellId, target->GetPosition(), Tune("rabid_strike_search_radius_yards"))'),
            "no_multiplier": (0, "factor = before * MimicFactor(mimic);", "factor = before;"),
            "never_reset": (0, "Monk::Mimic(player, spellId, near[std::size_t(pick)]);\n            factor = before;",
                            "Monk::Mimic(player, spellId, near[std::size_t(pick)]);"),
            "copy_on_the_dash_target": (0, "Monk::Mimic(player, spellId, near[std::size_t(pick)]);", "Monk::Mimic(player, spellId, target);"),
            "palm_as_a_hit": (1, "if (ExplodingPalm::Is(spellId))\n            return ExplodingPalm::Cast(player, spellId, {target});\n", ""),
            "hit_not_dealt": (1, "Combat::Strike(player, target, spellId, pct);", "(void)pct;"),
            "hit_term_unchanged": (3, 'ItemPowers::DealtFactor(player) * CopyFactor();', 'ItemPowers::DealtFactor(player);'),
            "shared_factor": (3, "thread_local double factor = 1.0;", "static double factor = 1.0;"),
            "palm_ticks_plain": (2, "double const pct = TickPct(totalPct, ticks) * Combat::CopyFactor();", "double const pct = TickPct(totalPct, ticks);"),
        }
        for name, (where, old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real[where].count(old), name + " does not apply once")
                texts = list(real)
                texts[where] = texts[where].replace(old, new)
                self.assertTrue(wiring_failures(*texts), name + " survived")


if __name__ == "__main__":
    unittest.main()
