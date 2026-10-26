"""The source-text guards of hellrack: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_hellrack.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_hellrack import EARTHGRAB, MATH, SRC  # noqa: E402


def control_guard(text):
    """The executor: the stock hold on the enemy the hit struck, the player's own taken off first, for the row's seconds."""
    body = text[text.index("void Control(Player* player, Unit* target, std::uint32_t hold, double seconds)"):]
    body = body[:body.index("\n        }\n")]
    assert "!hold || seconds <= 0 || !target->IsAlive()" in body, "no hold on the dead, for no time or with no aura"
    assert "target->RemoveAurasDueToSpell(hold, player->GetGUID());" in body, "a new fire starts the whole time again"
    assert "player->AddAura(hold, target)" in body, "the player's own hold"
    assert body.index("RemoveAurasDueToSpell") < body.index("AddAura"), "taken off before it goes on"
    assert "SetDuration(static_cast<std::int32_t>(seconds * 1000.0))" in body, "the row's seconds"
    assert "SetMaxDuration(static_cast<std::int32_t>(seconds * 1000.0))" in body, "the row's seconds as its whole"
    fire = text[text.index("void Fire(Player* player, char const* event"):]
    fire = fire[:fire.index("\n        }\n")]
    assert 'one.stat == "root_seconds" && target' in fire, "a control effect needs the enemy the event is about"
    assert "Control(player, target, ItemPower::ControlSpell(one.stat), one.value);" in fire, "the effect calls the executor with its aura and the row's seconds"


def event_guard(text):
    """The control events: an aura a player put on a monster fires that player's `control_<kind>` with the monster, only when a row listens."""
    body = text[text.index("class ControlEvents final : public UnitScript"):]
    body = body[:body.index("\n        };\n")]
    assert "UNITHOOK_ON_AURA_APPLY" in body, "the aura hook"
    assert "!Data().controls" in body, "nothing looked at when no row listens"
    assert "unit->IsPlayer()" in body, "a monster, not a player"
    assert "aura->GetCaster()" in body and "->ToPlayer()" in body, "the player who put it on"
    for aura in ("SPELL_AURA_MOD_STUN", "SPELL_AURA_MOD_CONFUSE", "SPELL_AURA_MOD_ROOT"):
        assert aura in body, aura
    assert "1u << MECHANIC_FREEZE" in body, "the Freeze mechanic"
    assert "ItemPower::ControlEvent(" in body, "the kind from the rule"
    assert "Fire(player, event, \"\", 1.0, unit);" in body, "the event with the monster as its target"
    assert "new ControlEvents();" in text[text.index("void RegisterScripts()"):], "registered"
    data = text[text.index("Table const& Data()"):text.index("std::mutex mutex;")]
    assert 'row.fireOn.rfind("control_", 0) == 0' in data, "the listen flag is set by a control row"


class Hooks(unittest.TestCase):
    def powers(self):
        return item_powers_source.CPP.read_text(encoding="utf-8")

    def test_the_effect_puts_the_hold_on_the_enemy(self):
        control_guard(self.powers())

    def test_the_aura_hook_fires_the_control_events(self):
        event_guard(self.powers())

    def test_the_source_mutants_fail_the_guards(self):
        powers = self.powers()
        for guard, cases in ((control_guard, {
            "no_alive_check": ("!hold || seconds <= 0 || !target->IsAlive()", "!hold || seconds <= 0"),
            "no_restart": ("target->RemoveAurasDueToSpell(hold, player->GetGUID());", ";"),
            "stock_duration": ("aura->SetDuration(static_cast<std::int32_t>(seconds * 1000.0));", ";"),
            "no_target_needed": ('one.stat == "root_seconds" && target', 'one.stat == "root_seconds"'),
            "effect_not_done": ("Control(player, target, ItemPower::ControlSpell(one.stat), one.value);", ";"),
        }), (event_guard, {
            "always_listens": ("!Data().controls", "false"),
            "players_too": ("unit->IsPlayer()", "false"),
            "no_freeze_mechanic": ("bool const freeze = (info->GetAllEffectsMechanicMask() & (1u << MECHANIC_FREEZE)) != 0;", "bool const freeze = (info->GetAllEffectsMechanicMask() & (1u << MECHANIC_STUN)) != 0;"),
            "no_target": ('Fire(player, event, "", 1.0, unit);', 'Fire(player, event, "", 1.0);'),
            "not_registered": ("        new ControlEvents();\n", ""),
            "listen_flag_unset": ('row.fireOn.rfind("control_", 0) == 0', "false"),
        })):
            for name, (old, new) in cases.items():
                with self.subTest(mutant=name):
                    self.assertIn(old, powers, name + " does not apply")
                    with self.assertRaises(AssertionError, msg=name + " survived"):
                        guard(powers.replace(old, new, 1))

    def test_the_header_names_the_stock_root(self):
        self.assertIn("constexpr std::uint32_t RootHold = %d;" % EARTHGRAB, MATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
