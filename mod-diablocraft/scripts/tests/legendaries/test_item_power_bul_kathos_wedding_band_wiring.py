"""The source-text guards of bul kathos wedding band: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_bul_kathos_wedding_band.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import struct

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_bul_kathos_wedding_band import REPO, SRC  # noqa: E402


POWERS = item_powers_source.CPP


RECORD = 18817


def clock_guard(powers, header):
    """The clock's hook, the effect's dispatch and the drain."""
    cache = powers[powers.index("class Cache final : public PlayerScript"):]
    cache = cache[:cache.index("\n        };\n")]
    assert "PLAYERHOOK_ON_UPDATE" in cache, "the update hook is asked for"
    update = cache[cache.index("void OnPlayerUpdate(Player* player, std::uint32_t) override"):]
    assert 'Fire(player, "tick", "", 1.0);' in update[:update.index("}")], "every update asks the clock"
    assert "new Cache();" in powers[powers.index("void RegisterScripts()"):], "the hook is registered"
    assert 'one.stat == "drain_life"' in powers and "Drain(player, one.value);" in powers, "the effect drains"
    drain = powers[powers.index("void Drain(Player* player, double pct)"):]
    drain = drain[:drain.index("\n        }\n")]
    assert "constexpr std::uint32_t DrainRecord = %d;" % RECORD in powers, "the stock Drain Life record"
    assert "!player->IsInCombat()" in drain, "only in combat"
    assert "!player->IsAlive()" in drain, "only the living"
    for name in ("bul_kathos_drain_radius_yards", "bul_kathos_drain_max_weapon_damage", "bul_kathos_drain_max_heal_pct"):
        assert 'Tune("%s")' % name in drain, name + " is read"
    assert "Combat::Enemies(player, DrainRecord, player->GetPosition(), radius)" in drain, "the enemies around the player"
    assert "static_cast<double>(enemy->GetMaxHealth())" in drain, "the real maximum Life (the core holds it whole)"
    assert "Combat::WeaponRange(player, false)" in drain and "(range.first + range.second) / 2.0" in drain, "the main hand's average"
    assert "Stat::WeaponFlatDamage" in drain, "the sheet's flat weapon damage"
    assert "ItemPower::DrainPulse(most, pct, weapon," in drain, "the rule"
    assert "Combat::DealHit(player, enemies[i], DrainRecord, hit, true);" in drain, "dealt as it stands, as the player's"
    assert "hit.total = pulse.taken[i];" in drain, "each enemy its own share"
    assert "player->HealBySpell(heal, false);" in drain and "pulse.healed" in drain, "the heal"
    assert "std::pair<double, double> WeaponRange(Player* player, bool offHand);" in header, "declared"


def stock_record_name(dbc, spell_id):
    """Name_Lang_enUS of a record of a 3.3.5 Spell.dbc (field 136)."""
    data = dbc.read_bytes()
    count, _, size, _ = struct.unpack("<4I", data[4:20])
    strings = 20 + count * size
    for i in range(count):
        record = data[20 + i * size:20 + (i + 1) * size]
        if struct.unpack("<I", record[:4])[0] == spell_id:
            offset = struct.unpack("<I", record[136 * 4:137 * 4])[0]
            return data[strings + offset:data.index(b"\0", strings + offset)].decode("utf-8")
    return None


class Hooks(unittest.TestCase):
    def texts(self):
        return POWERS.read_text(encoding="utf-8"), (SRC / "combat/dc_combat.h").read_text(encoding="utf-8")

    def test_the_clock_and_the_drain_are_wired(self):
        clock_guard(*self.texts())

    def test_the_record_is_the_stock_drain_life(self):
        for dbc in (REPO / "client-patch/dbc/Spell.dbc", Path("/home/user/diablocraft/azerothcore-wotlk/build/server/data/dbc/Spell.dbc")):
            if dbc.exists():
                self.assertEqual("Drain Life", stock_record_name(dbc, RECORD))
                return
        self.skipTest("no Spell.dbc on this machine")

    def test_the_source_mutants_fail_the_guard(self):
        powers, header = self.texts()
        for name, (old, new) in {
            "no_update_hook": ("PLAYERHOOK_ON_CREATURE_KILL, PLAYERHOOK_ON_UPDATE}", "PLAYERHOOK_ON_CREATURE_KILL}"),
            "no_tick": ('Fire(player, "tick", "", 1.0);', ";"),
            "not_registered": ("        new Cache();\n", ""),
            "no_dispatch": ("Drain(player, one.value);", ";"),
            "out_of_combat_too": (" || !player->IsInCombat()", ""),
            "the_dead_drain": (" || !player->IsAlive()", ""),
            "radius_renamed": ('Tune("bul_kathos_drain_radius_yards")', 'Tune("bul_kathos_drain_radius")'),
            "current_life": ("static_cast<double>(enemy->GetMaxHealth())", "static_cast<double>(enemy->GetHealth())"),
            "multiplied": ("Combat::DealHit(player, enemies[i], DrainRecord, hit, true);", "Combat::DealHit(player, enemies[i], DrainRecord, hit);"),
            "no_heal": ("player->HealBySpell(heal, false);", ";"),
            "another_record": ("DrainRecord = %d;" % RECORD, "DrainRecord = 689;"),
            "no_flat_damage": ("weapon += (*sheet)[Stat::WeaponFlatDamage];", ";"),
        }.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, powers.count(old), name + " does not apply once")
                with self.assertRaises(AssertionError, msg=name + " survived"):
                    clock_guard(powers.replace(old, new), header)


if __name__ == "__main__":
    unittest.main()
