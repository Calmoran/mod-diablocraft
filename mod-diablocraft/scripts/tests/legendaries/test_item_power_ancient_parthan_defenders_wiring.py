"""The source-text guards of Ancient Parthan Defenders: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_ancient_parthan_defenders.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_ancient_parthan_defenders import MODULE  # noqa: E402

POWERS = item_powers_source.CPP
EFFECTS = item_powers_source.FOLDER / "dc_item_powers_effects.cpp"


def failures(powers, effects):
    """What is wrong with the count of stunned enemies and its reader (the source guards; [] when they are right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    reader = powers[powers.index("double IncomingFactor(Player const* player)"):]
    reader = reader[:reader.index("\n    }\n")]
    need("the damage taken is multiplied by the stunned reduction, over the situation the other terms read",
         "ItemPower::StunnedReduction(Data().rows, CountsOf(guid), situation)" in reader)
    need("nothing else reads it", powers.count("ItemPower::StunnedReduction(") == 1)
    need("the situation carries the count the update hook took", "situation.stunnedNear = mine->second.stunnedNear;" in powers)
    need("a row that wants the count turns the look on", 'loaded.stunned = loaded.stunned || row.stat == "damage_reduction_per_stunned_pct";' in powers)
    need("the one update hook looks, after the stood-still timer",
         "StandStill(player);\n                StunScan(player);" in powers and powers.count("StunScan(player);") == 1)
    body = effects[effects.index("void StunScan(Player* player)"):]
    body = body[:body.index("\n        }\n")]
    need("only when some row wants the count", "if (!Data().stunned)\n                return;" in body)
    need("only for a player in play", "if (mine == clocks.end())\n                    return;" in body)
    need("the radius and the cadence are the item's fixed rows, read under the lock for the rows in play",
         'yards = ItemPower::PlayerSetTo(Data().rows, CountsOf(guid), "stunned_radius_yards", 0.0, situation);' in body
         and 'every = ItemPower::PlayerSetTo(Data().rows, CountsOf(guid), "stunned_check_seconds", 0.0, situation);' in body)
    need("an item that is off clears the count", "mine->second.stunnedNear = 0;" in body)
    need("a look waits for its cadence and records its time", "if (!ItemPower::ScanDue(mine->second.stunScanAt, now, every))" in body
         and "mine->second.stunScanAt = now;" in body)
    need("the enemies are the hostile ones within the radius of the wearer",
         "Combat::Enemies(player, DrainRecord, player->GetPosition(), yards)" in body)
    need("an enemy is stunned by a stun aura that is not a freeze",
         "enemy->GetAuraEffectsByType(SPELL_AURA_MOD_STUN)" in body
         and "ItemPower::StunAura(info->Id, (info->GetAllEffectsMechanicMask() & (1u << MECHANIC_FREEZE)) != 0)" in body)
    need("an enemy counts once however many stuns it carries", "++stunned;\n                        break;" in body)
    need("the count is stored under the lock after the scan", "mine->second.stunnedNear = stunned;" in body
         and body.index("Combat::Enemies(") < body.index("mine->second.stunnedNear = stunned;")
         and body.rindex("std::lock_guard<std::mutex> lock(mutex);") > body.index("Combat::Enemies("))
    return wrong


class Hooks(unittest.TestCase):
    def test_the_count_and_its_reader(self):
        self.assertEqual([], failures(POWERS.read_text(encoding="utf-8"), EFFECTS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        powers = POWERS.read_text(encoding="utf-8")
        effects = EFFECTS.read_text(encoding="utf-8")
        mutants = {
            "not_in_the_damage_taken": (POWERS, " *\n               ItemPower::StunnedReduction(Data().rows, CountsOf(guid), situation)", ""),
            "other_situation": (POWERS, "ItemPower::StunnedReduction(Data().rows, CountsOf(guid), situation)", "ItemPower::StunnedReduction(Data().rows, CountsOf(guid), {})"),
            "count_not_carried": (POWERS, "situation.stunnedNear = mine->second.stunnedNear;", ""),
            "flag_never_set": (POWERS, 'loaded.stunned = loaded.stunned || row.stat == "damage_reduction_per_stunned_pct";', ""),
            "not_called": (POWERS, "                StunScan(player);\n", ""),
            "always_looks": (EFFECTS, "if (!Data().stunned)\n                return;", ""),
            "no_player_check": (EFFECTS, "if (mine == clocks.end())\n                    return;", ""),
            "wrong_radius": (EFFECTS, '"stunned_radius_yards", 0.0, situation', '"stunned_check_seconds", 0.0, situation'),
            "count_kept_when_off": (EFFECTS, "mine->second.stunnedNear = 0;", ""),
            "no_cadence": (EFFECTS, "if (!ItemPower::ScanDue(mine->second.stunScanAt, now, every))", "if (false)"),
            "cadence_not_recorded": (EFFECTS, "mine->second.stunScanAt = now;", ""),
            "friendly_too": (EFFECTS, "Combat::Enemies(player, DrainRecord, player->GetPosition(), yards)", "Combat::Enemies(player, DrainRecord, player->GetPosition(), 1)"),
            "a_freeze_counts": (EFFECTS, "ItemPower::StunAura(info->Id, (info->GetAllEffectsMechanicMask() & (1u << MECHANIC_FREEZE)) != 0)", "true"),
            "a_root_counts": (EFFECTS, "SPELL_AURA_MOD_STUN)", "SPELL_AURA_MOD_ROOT)"),
            "every_stun_counts": (EFFECTS, "++stunned;\n                        break;", "++stunned;"),
            "count_not_stored": (EFFECTS, "mine->second.stunnedNear = stunned;", ""),
        }
        for name, (where, old, new) in mutants.items():
            with self.subTest(mutant=name):
                text = powers if where == POWERS else effects
                self.assertEqual(1, text.count(old), name + " does not apply once")
                mutated = text.replace(old, new)
                self.assertTrue(failures(mutated if where == POWERS else powers, mutated if where == EFFECTS else effects), name + " survived")


if __name__ == "__main__":
    unittest.main()
