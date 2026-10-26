"""The source-text guards of bindings lesser gods: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_bindings_lesser_gods.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_bindings_lesser_gods import SRC  # noqa: E402


POWERS = item_powers_source.CPP


COMBAT = SRC / "combat/dc_combat.cpp"


def firing_failures(text):
    """What is wrong with the module's marking and reading in dc_item_powers.cpp `text` (the source guards; [] when it is right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    mark = text[text.index("void MarkEnemy("):]
    mark = mark[:mark.index("\n        }\n") + 11]
    need("the record is the owner's mark_enemy buff", "Shells::PowerBuffFor(row.owner.c_str(), row.stat.c_str())" in mark)
    need("a dead target is not marked", "!target->IsAlive()" in mark)
    need("the player is the caster, so the mark is hers", "player->AddAura(id, target)" in mark)
    need("her own mark is renewed, not stacked", "target->GetAura(id, player->GetGUID())" in mark)
    need("the rolled percent is the aura's amount", "effect->ChangeAmount(static_cast<std::int32_t>(pct))" in mark)
    need("the row's seconds are the duration", "row.stackSeconds * 1000.0" in mark and "aura->SetDuration(ms)" in mark and "aura->SetMaxDuration(ms)" in mark)
    need("an effect row of the stat marks the hit's target with the rolled value",
         'one.stat == "mark_enemy" && target && one.row)\n                    MarkEnemy(player, target, *one.row, one.value);' in text)
    reader = text[text.index("double MarkFactor(Player const* player"):]
    reader = reader[:reader.index("\n    }\n") + 7]
    need("only the player's own mark is read", "target->GetAura(buff.id, player->GetGUID())" in reader)
    need("only the mark_enemy buffs", 'std::string(buff.stat) != "mark_enemy"' in reader)
    need("only for the skill the row names", "row.owner == buff.owner && row.skill == skill" in reader)
    need("the percent is the aura's amount", "effect->GetAmount()" in reader)
    need("a split hit reads the owner's split factor, base 1", 'SkillSetTo(player, skill, "mark_split_factor", 1.0)' in reader and "split ?" in reader)
    need("the pure rule gives the factor", "ItemPower::MarkFactor(effect->GetAmount(), times)" in reader)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_module_marks_and_reads(self):
        self.assertEqual([], firing_failures(POWERS.read_text(encoding="utf-8")))

    def test_combat_multiplies_the_mark_in_with_fire_ally_as_the_split(self):
        combat = COMBAT.read_text(encoding="utf-8")
        self.assertIn('hit.legendary *= ItemPowers::MarkFactor(player, target, petName, shell.rune == "Fire Ally");', combat)
        # the skill is the hit's own name (Mystic Ally for every rune's strike), read where the other legendary factors are
        self.assertLess(combat.index("hit.legendary = ItemPowers::SkillFactor("), combat.index("ItemPowers::MarkFactor("))
        self.assertLess(combat.index("ItemPowers::MarkFactor("), combat.index("hit.total = Total("))

    def test_the_mark_is_not_a_player_buff(self):
        # the loops over PowerBuffs that act on the wearer (sheet armor, attack speed, drops) read their own stats only
        text = POWERS.read_text(encoding="utf-8")
        for stat in ("armor_pct", "movement_speed_pct"):
            self.assertIn('std::string(buff.stat) == "%s"' % stat, text)

    def test_the_header_declares_it(self):
        header = (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8")
        self.assertIn("double MarkFactor(Player const*, Unit const* target, std::string const& skill, bool split);", header)

    def test_the_source_guards_fail_their_mutants(self):
        real = POWERS.read_text(encoding="utf-8")
        mutants = {
            "enemy_is_the_caster": ("player->AddAura(id, target)", "target->AddAura(id, target)"),
            "stacks_marks": ("target->GetAura(id, player->GetGUID())", "nullptr"),
            "no_amount": ("effect->ChangeAmount(static_cast<std::int32_t>(pct))", "(void) effect"),
            "no_seconds": ("effect->ChangeAmount(static_cast<std::int32_t>(pct));\n            std::int32_t const ms = static_cast<std::int32_t>(row.stackSeconds * 1000.0);",
                           "effect->ChangeAmount(static_cast<std::int32_t>(pct));\n            std::int32_t const ms = 0;"),
            "marks_the_player": ("MarkEnemy(player, target, *one.row, one.value);", "MarkEnemy(player, player, *one.row, one.value);"),
            "anyones_mark": ("target->GetAura(buff.id, player->GetGUID())", "target->GetAura(buff.id)"),
            "any_skill": ("row.owner == buff.owner && row.skill == skill", "row.owner == buff.owner"),
            "no_split": ('SkillSetTo(player, skill, "mark_split_factor", 1.0)', "1.0"),
            "no_percent": ("ItemPower::MarkFactor(effect->GetAmount(), times)", "ItemPower::MarkFactor(0, times)"),
            "dead_marked": ("if (!id || !target->IsAlive())", "if (!id)"),
        }
        for name, (old, new) in mutants.items():
            with self.subTest(mutant=name):
                self.assertEqual(1, real.count(old), name + " does not apply once")
                self.assertTrue(firing_failures(real.replace(old, new)), name + " survived")


if __name__ == "__main__":
    unittest.main()
