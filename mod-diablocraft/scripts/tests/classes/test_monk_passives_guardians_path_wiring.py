"""The source-text guards of monk passives guardians path: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_monk_passives_guardians_path.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path
import re
import struct

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_monk_passives_guardians_path import CODE, MODULE, REPO, in_additive_pool, multipliers_called  # noqa: E402


def pays_with_guardians_path(monk):
    """True if Monk::Connected's Generate call carries Passives242::GenerationFactor and SpiritFactor does not (Band of Rue's alone)."""
    connected = monk[monk.index("void Connected("):]
    connected = connected[:connected.index("\n    }\n")]
    spirit = monk[monk.index("double SpiritFactor("):]
    spirit = spirit[:spirit.index("\n    }\n")]
    call = re.search(r"Generate\(player, [^;]*GenerationFactor\(player\)\);", connected)
    return bool(call) and "Passives242::GenerationFactor" not in spirit


class Wiring(unittest.TestCase):
    def setUp(self):
        self.code = CODE.read_text(encoding="utf-8")
        self.monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        self.effects = (MODULE / "src/classes/monk/dc_monk_effects.cpp").read_text(encoding="utf-8")
        self.combat = "".join(p.read_text(encoding="utf-8") for p in [MODULE / "src/combat" / "dc_combat_internal.h", *sorted((MODULE / "src/combat").glob("dc_combat*.cpp"))])

    def test_the_monk_hands_the_passives_over(self):
        # Guardian's Path pays in the Generate call of Monk::Connected, and the check can fail: without it, or with the factor
        # only after a return inside SpiritFactor (the fold's dead line), it does not hold.
        self.assertTrue(pays_with_guardians_path(self.monk))
        self.assertFalse(pays_with_guardians_path(self.monk.replace(" * Passives242::GenerationFactor(player));", ");", 1)))
        dead = self.monk.replace(" * Passives242::GenerationFactor(player));", ");", 1).replace(
            "return row ? ItemPowers::SkillFactor(player, row->skill, \"resource_generation_pct\") : 1.0;",
            "return row ? ItemPowers::SkillFactor(player, row->skill, \"resource_generation_pct\") : 1.0;\n"
            "        Generate(player, 0, spellId, 1 * Passives242::GenerationFactor(player));", 1)
        self.assertFalse(pays_with_guardians_path(dead))
        self.assertIn("Passives242::Dodge(unit)", self.monk)  # (other skills' dodge terms sit beside it)
        # Determination and Relentless Assault are factors of their own (decisions.md 2bb8979d7), not in the additive pool.
        self.assertFalse(in_additive_pool(self.effects))
        # the victim is a parameter of the hook: no stash read across calls
        for text in (self.code, self.effects, self.monk):
            self.assertNotIn("thread_local", text)
            self.assertNotIn("Seen(", text)
        self.assertIn("void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out)", self.monk)  # (one body for both passive files)
        self.assertIn("Passives242::Multipliers(player, target, out);", self.monk)
        self.assertTrue(multipliers_called(self.combat))
        self.assertEqual(self.combat.count("Monk::Multipliers("), 1)
        self.assertIn('AddFactor(out, "Determination", pct)', self.code)
        self.assertIn('AddFactor(out, "Relentless Assault", pct)', self.code)

    def test_the_combat_code_asks_for_alacritys_speed_and_registers_the_script(self):
        self.assertIn("Primaries::AttackSpeed(player, spellId, Monk::AttackSpeed(player, spellId, hand))", self.combat)
        self.assertIn("Monk::AttackSpeed(player, spellId, sheet->attacksPerSecond)", self.combat)
        # the script registers inside the one Monk::RegisterScripts (dc_monk.cpp), not by a line of its own here
        self.assertEqual(self.combat.count("Monk::RegisterPassiveScripts();"), 0)
        monk = (MODULE / "src/classes/monk/dc_monk.cpp").read_text(encoding="utf-8")
        register = monk[monk.index("void RegisterScripts()\n    {"):]
        self.assertIn("RegisterPassiveScripts();", register[:register.index("\n    }\n")])

    def test_the_sheet_passives_go_through_the_sheet(self):
        self.assertIn("Source::Passives, Stat::ElementReduction", self.code)
        self.assertIn("Source::Passives, Stat::CooldownReduction", self.code)
        self.assertIn("Passives::RefreshModifiers(player)", self.code)
        # Passives::Has answers for the chosen passives and the ones a worn Hellfire Amulet grants.
        self.assertIn("Passives::Has(player, name)", self.code)

    def test_blind_is_blinding_flashs_dizzy(self):
        # Stock "Dizzy" (9992): one MOD_CONFUSE effect (aura 5), the blind Blinding Flash puts on an ordinary enemy.
        self.assertRegex(self.code, r"constexpr std::uint32_t Dizzy = 9992;")
        self.assertIn("target->HasAura(Dizzy)", self.code)
        dbc = REPO / "azerothcore-wotlk/build/server/data/dbc/Spell.dbc"
        if not dbc.exists():
            self.skipTest("no stock Spell.dbc in this checkout")
        data = dbc.read_bytes()
        _, count, fields, size, _ = struct.unpack("<4sIIII", data[:20])
        body = data[20:20 + count * size]
        for index in range(count):
            record = body[index * size:(index + 1) * size]
            if struct.unpack("<I", record[:4])[0] == 9992:
                row = struct.unpack("<%dI" % fields, record)
                # Spell.dbc 3.3.5: Effect_1..3 at fields 71-73, EffectAura_1..3 at 95-97.
                self.assertEqual([(e, a) for e, a in zip(row[71:74], row[95:98]) if e], [(6, 5)])
                return
        self.fail("Spell.dbc has no spell 9992")

    def test_only_the_spirit_generators_are_sped(self):
        self.assertIn('Numbers::Get(spellId, "generated_resource")', self.code)


if __name__ == "__main__":
    unittest.main()
