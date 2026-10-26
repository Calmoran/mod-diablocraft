"""The source-text guards of jangs envelopment: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_jangs_envelopment.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_jangs_envelopment import DAZED, MATH, SRC  # noqa: E402


def slow_guard(text):
    """The executor: the stock snare on the enemy the hit struck at -N%, the player's own taken off first, for the owner's seconds."""
    body = text[text.index("void Slow(Player* player, Unit* target, double pct, double seconds)"):]
    body = body[:body.index("\n        }\n")]
    assert "seconds <= 0 || pct <= 0 || !target->IsAlive()" in body, "no slow on the dead, for no time or of nothing"
    assert "target->RemoveAurasDueToSpell(ItemPower::SlowHold, player->GetGUID());" in body, "a new hit starts the whole time again"
    assert "player->AddAura(ItemPower::SlowHold, target)" in body, "the player's own snare"
    assert body.index("RemoveAurasDueToSpell") < body.index("AddAura"), "taken off before it goes on"
    assert "effect->ChangeAmount(ItemPower::SlowAmount(pct));" in body, "the item's percent"
    assert "SetDuration(static_cast<std::int32_t>(seconds * 1000.0))" in body, "the owner's seconds"
    assert "SetMaxDuration(static_cast<std::int32_t>(seconds * 1000.0))" in body, "the owner's seconds as its whole"
    fire = text[text.index("void Fire(Player* player, char const* event"):]
    fire = fire[:fire.index("\n        }\n")]
    assert 'one.stat == "slow_pct" && target && one.row' in fire, "the slow needs the enemy the hit struck"
    assert 'Slow(player, target, one.value, ItemPower::OwnerNumber(Data().rows, one.row->owner, "player", "slow_seconds"));' in fire, \
        "the item's roll and its own seconds"


class Hooks(unittest.TestCase):
    def powers(self):
        return item_powers_source.CPP.read_text(encoding="utf-8")

    def test_the_effect_puts_the_snare_on_the_enemy(self):
        slow_guard(self.powers())

    def test_the_source_mutants_fail_the_guard(self):
        powers = self.powers()
        for name, (old, new) in {
            "no_alive_check": ("seconds <= 0 || pct <= 0 || !target->IsAlive()", "seconds <= 0 || pct <= 0"),
            "no_restart": ("target->RemoveAurasDueToSpell(ItemPower::SlowHold, player->GetGUID());", ";"),
            "stock_amount": ("effect->ChangeAmount(ItemPower::SlowAmount(pct));", ";"),
            "stock_duration": ("aura->SetDuration(static_cast<std::int32_t>(seconds * 1000.0));", ";"),
            "no_target_needed": ('one.stat == "slow_pct" && target && one.row', 'one.stat == "slow_pct" && one.row'),
            "the_seconds_unread": ('ItemPower::OwnerNumber(Data().rows, one.row->owner, "player", "slow_seconds")', "3.0"),
        }.items():
            with self.subTest(mutant=name):
                self.assertIn(old, powers, name + " does not apply")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    # from Slow on: Control, Hellrack's, sits above it with the same duration lines
                    start = powers.index("void Slow(")
                    slow_guard(powers[:start] + powers[start:].replace(old, new, 1))

    def test_no_other_torment_code_uses_the_snare(self):
        users = [p for p in SRC.rglob("*.[ch]*") if str(DAZED) in p.read_text(encoding="utf-8", errors="replace")]
        self.assertEqual([MATH], users)

    def test_black_hole_hits_reach_the_hit_event(self):
        """A Black Hole cast resolves each enemy through ResolveHit, which reports the hit (Passives::Hit -> ItemPowers::Hit)."""
        combat = "".join(p.read_text(encoding="utf-8") for p in [SRC / "combat" / "dc_combat_internal.h", *sorted((SRC / "combat").glob("dc_combat*.cpp"))])
        resolve = combat[combat.index("bool ResolveHit(Player* player, Unit* target, Shell const& shell, SpellInfo const* info)"):]
        resolve = resolve[:resolve.index("\n        }\n")]
        self.assertIn("Passives::Hit(player,target,shell.spellId,hit.school);", resolve)
        self.assertIn("ItemPowers::Hit(p, target, spellId);", (SRC / "combat/dc_passives.cpp").read_text(encoding="utf-8"))
        self.assertIn('{83125, "Black Hole", "", 15.0}', (SRC / "combat/dc_spell_shells.h").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
