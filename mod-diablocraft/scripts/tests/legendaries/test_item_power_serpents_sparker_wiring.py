"""The source-text guards of serpents sparker: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_serpents_sparker.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_serpents_sparker import SRC  # noqa: E402


POWERS = item_powers_source.CPP


WIZARD = SRC / "classes/wizard/dc_wizard_hydra.cpp"


def hook_failures(wizard, powers):
    """What is wrong with the Hydra summon's cap (the source guards; [] when it is right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    start = wizard.find("void OnPlayerBeforeTempSummonInitStats(Player* player, TempSummon* summon, uint32&) override")
    need("the Wizard's player script has the summon hook", start >= 0)
    if start < 0:
        return wrong
    hook = wizard[start:wizard.index("\n            }\n", start)]
    need("the hook is registered", "PLAYERHOOK_ON_BEFORE_TEMP_SUMMON_INIT_STATS})" in wizard)
    need("only a Hydra's summon", "if (!summon || !IsHydraEntry(summon->GetEntry()))\n                    return;" in hook)
    ask = 'ItemPowers::ActiveCount(player, "Hydra", 1)'
    need("the cap asks the item powers with the core's one Hydra as its base", ask in hook)
    need("the dead and gone are not counted", "return !hydra || !hydra->IsAlive();" in hook)
    need("the oldest past the cap go", "std::size_t const gone = ItemPower::Dismissed(up.size(), cap);" in hook
         and "dismissed.assign(up.begin(), up.begin() + gone);" in hook and "up.erase(up.begin(), up.begin() + gone);" in hook)
    need("the new one is kept", "up.push_back(summon->GetGUID());" in hook)
    need("the dismissed are unsummoned, outside the lock", "hydra->ToTempSummon()->UnSummon();" in hook and "std::lock_guard" in hook
         and hook.index("hydra->ToTempSummon()->UnSummon();") > hook.index("\n                }\n", hook.index("std::lock_guard")))
    need("the survivor is taken off the totem slot so the core does not unsummon it", "player->m_SummonSlot[slot].Clear();" in hook)
    need("IsHydraEntry finds the Hydra records' summoned creature",
         "if (IsSkill(row.id, \"Hydra\"))" in wizard[wizard.index("bool IsHydraEntry(uint32 entry)"):]
         .split("\n        }\n")[0] and "info->Effects[EFFECT_0].MiscValue) == entry" in wizard)
    reader = powers[powers.index("double ActiveCount(Player const* player, std::string const& skill, double base)"):]
    reader = reader[:reader.index("\n    }\n")]
    need("the reader is the rule over the player's rows",
         "return ItemPower::ActiveCount(Data().rows, CountsOf(guid), skill, base, SituationOf(guid, std::move(seen)));" in reader)
    return wrong


class Hooks(unittest.TestCase):
    def test_the_summon_caps_the_hydras(self):
        self.assertEqual([], hook_failures(WIZARD.read_text(encoding="utf-8"), POWERS.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        wizard = WIZARD.read_text(encoding="utf-8")
        powers = POWERS.read_text(encoding="utf-8")
        mutants = {
            "not_registered": (WIZARD, "PLAYERHOOK_ON_BEFORE_TEMP_SUMMON_INIT_STATS})", "})"),
            "base_zero": (WIZARD, 'ItemPowers::ActiveCount(player, "Hydra", 1)', 'ItemPowers::ActiveCount(player, "Hydra", 0)'),
            "no_slot_clear": (WIZARD, "player->m_SummonSlot[slot].Clear();", "(void)slot;"),
            "new_one_not_kept": (WIZARD, "up.push_back(summon->GetGUID());", "(void)summon;"),
            "nothing_dismissed": (WIZARD, "hydra->ToTempSummon()->UnSummon();", "(void)hydra;"),
            "dead_counted": (WIZARD, "return !hydra || !hydra->IsAlive();", "return !hydra;"),
            "any_summon": (WIZARD, "if (!summon || !IsHydraEntry(summon->GetEntry()))", "if (!summon)"),
            "reader_wrong_rule": (POWERS, "return ItemPower::ActiveCount(Data().rows, CountsOf(guid), skill, base,",
                                  "return ItemPower::DurationSeconds(Data().rows, CountsOf(guid), skill, base,"),
        }
        for name, (where, old, new) in mutants.items():
            with self.subTest(mutant=name):
                text = wizard if where == WIZARD else powers
                self.assertEqual(1, text.count(old), name + " does not apply once")
                mutated = text.replace(old, new)
                self.assertTrue(hook_failures(mutated if where == WIZARD else wizard, mutated if where == POWERS else powers), name + " survived")


if __name__ == "__main__":
    unittest.main()
