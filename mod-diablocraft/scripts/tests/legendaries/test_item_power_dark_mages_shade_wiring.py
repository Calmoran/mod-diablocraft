"""The source-text guards of dark mages shade: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_dark_mages_shade.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_dark_mages_shade import SRC  # noqa: E402


def damaged_guard(text):
    """The Damaged reader: listens only when a row waits, never for a killing hit, then fires the event with the Life before and after."""
    body = text[text.index("void Damaged(Player* player, std::uint32_t damage)"):]
    body = body[:body.index("\n    }\n")]
    assert 'Data().events.count("life_below")' in body, "asks when no row listens"
    assert "damage >= player->GetHealth()" in body, "a killing hit is skipped"
    assert "player->GetMaxHealth()" in body, "Life is a percent of the maximum"
    assert body.index("damage >= player->GetHealth()") < body.index('Fire(player, "life_below"'), "the kill is judged before the event"
    assert "player->GetHealth() - damage" in body, "Life after the hit"
    assert "UNITHOOK_ON_DAMAGE" in text and "new LifeEvents();" in text[text.index("void RegisterScripts()"):], "the hook is registered"
    assert 'one.stat == "cast_skill"' in text and "CastSkill(player, one.skill)" in text, "the effect casts the skill"


def cast_guard(text):
    """CastSkill: the bar's own spell (the chosen rune), as the core's triggered cast."""
    body = text[text.index("bool CastSkill(Player* player, std::string const& skill, Unit* target)"):]
    body = body[:body.index("\n    }\n")]
    assert "Classes::Bar(player)" in body, "the bar"
    assert "Shells::FindAbility(slot.spellId)" in body, "the slot's skill"
    assert "skill == shell->skill" in body, "the named skill only"
    assert "TRIGGERED_FULL_MASK" in body, "triggered: no cost, cooldown or cast event"
    assert "SPELL_CAST_OK" in body, "the core's answer"
    assert "player->IsAlive()" in body, "the living"


class Hooks(unittest.TestCase):
    def powers(self):
        return item_powers_source.CPP.read_text(encoding="utf-8")

    def combat(self):
        return "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])

    def test_the_damage_reaches_the_event_before_it_is_dealt_and_only_when_it_does_not_kill(self):
        damaged_guard(self.powers())

    def test_the_narrow_cast_is_declared_and_casts_the_bars_spell_as_a_triggered_cast(self):
        self.assertIn("bool CastSkill(Player* player, std::string const& skill, Unit* target = nullptr);",
                      (SRC / "combat/dc_combat.h").read_text(encoding="utf-8"))
        cast_guard(self.combat())

    def test_the_header_declares_damaged(self):
        self.assertIn("void Damaged(Player*, std::uint32_t damage);", (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))

    def test_the_source_mutants_fail_the_guards(self):
        powers, combat = self.powers(), self.combat()
        for name, (old, new) in {
            "no_listener_check": ('!Data().events.count("life_below")', "false"),
            "a_killing_hit_counts": ("damage >= player->GetHealth() || ", "false || "),
            "life_after_is_before": ("100.0 * (player->GetHealth() - damage) / most", "100.0 * player->GetHealth() / most"),
            "hook_not_registered": ("        new LifeEvents();\n", ""),
            "effect_not_cast": ("CastSkill(player, one.skill);", ";"),
        }.items():
            with self.subTest(mutant=name):
                self.assertIn(old, powers, name + " does not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    damaged_guard(powers.replace(old, new, 1))
        for name, (old, new) in {
            "not_the_bar": ("Classes::Bar(player)", "std::vector<Classes::Slot>{}"),
            "any_skill": ("skill == shell->skill", "true"),
            "a_pressed_cast": ("TRIGGERED_FULL_MASK", "TRIGGERED_NONE"),
            "answer_ignored": ("== SPELL_CAST_OK", "|| true"),
            "the_dead_cast": ("!player->IsAlive()", "false"),
        }.items():
            with self.subTest(mutant=name):
                self.assertIn(old, combat[combat.index("bool CastSkill(Player* player"):], name + " does not apply")
                head = combat[:combat.index("bool CastSkill(Player* player")]
                tail = combat[combat.index("bool CastSkill(Player* player"):]
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    cast_guard(head + tail.replace(old, new, 1))


if __name__ == "__main__":
    unittest.main()
