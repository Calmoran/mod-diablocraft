"""The source-text guards of immortal kings call set: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_immortal_kings_call_set.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
import barbarian_source
from test_item_power_immortal_kings_call_set import SRC  # noqa: E402


def hook_problems(powers, abilities, ancients, header):
    """What is wrong with the three places that read the rows, as text."""
    out = []
    if "void Spent(Player*, double fury);" not in header:
        out.append("Spent is not declared in dc_item_powers.h")
    body = powers[powers.index("    void Spent(Player* player, double fury)"):]
    body = body[:body.index("\n    }\n")]
    if 'Data().events.count("resource_spent")' not in body or "fury <= 0" not in body:
        out.append("Spent does not skip a build with no resource_spent row or nothing spent")
    if "ItemPower::SpentFires(Data().rows, CountsOf(guid), SituationOf(guid, std::move(seen)), fury, clocks[guid].spentCarry)" not in body:
        out.append("Spent does not drive SpentFires with the per-player carry")
    if "Seen(player)" not in body or body.index("Seen(player)") > body.index("std::lock_guard"):
        out.append("Spent reads the situation inside the lock")
    if "one.stat == \"cooldown_cut_named_seconds\"" not in body or "Abilities::ReduceSkillCooldown(player, name.c_str(), one.value * 1000.0);" not in body:
        out.append("Spent does not cut each named skill's cooldown in milliseconds")
    if body.index("Abilities::ReduceSkillCooldown") < body.index("\n        }\n"):
        out.append("the cut runs inside the lock")
    if "std::getline(names, name, ';')" not in body:
        out.append("Spent does not split the named skills")
    if "std::map<std::string, double> spentCarry;" not in powers:
        out.append("the clock has no spentCarry")
    spent = abilities[abilities.index("    void Spent(Player* p, double fury)"):]
    spent = spent[:spent.index("\n    }")]
    if "ItemPowers::Spent(p, fury);" not in spent or spent.index("ItemPowers::Spent(p, fury);") > spent.index("std::lock_guard"):
        out.append("Abilities::Spent does not report to ItemPowers::Spent before its own lock")
    summon = ancients[ancients.index("    void Summon(Player* p, uint32 id)"):]
    summon = summon[:summon.index("\n    }\n")]
    if 'SkillSetTo(p, "Call of the Ancients", "lasts_until_death", 0) > 0;' not in summon:
        out.append("Summon does not read lasts_until_death")
    elif summon.index("lasts_until_death") > summon.index("std::lock_guard"):
        out.append("Summon reads the flag inside its lock")
    if "untilDeath ? TEMPSUMMON_DEAD_DESPAWN : TEMPSUMMON_TIMED_DESPAWN" not in summon or "untilDeath ? 0u : uint32(" not in summon:
        out.append("Summon does not summon without a timer when the flag is on")
    return out


class Hooks(unittest.TestCase):
    def texts(self):
        return (item_powers_source.CPP_WITH_HEADER.read_text(encoding="utf-8"), barbarian_source.abilities((".cpp",)),
                (SRC / "classes/barbarian/dc_barbarian_call_of_the_ancients.cpp").read_text(encoding="utf-8"), (SRC / "combat/dc_item_powers.h").read_text(encoding="utf-8"))

    def test_the_readers_are_in_place(self):
        self.assertEqual([], hook_problems(*self.texts()))

    def test_the_other_summoners_keep_their_timer(self):
        text = (SRC / "classes/barbarian/dc_barbarian_call_of_the_ancients.cpp").read_text(encoding="utf-8")
        self.assertEqual(1, text.count("TEMPSUMMON_TIMED_DESPAWN"))
        self.assertEqual(1, text.count("TEMPSUMMON_DEAD_DESPAWN"))

    def test_the_mutants_are_found(self):
        powers, abilities, ancients, header = self.texts()
        mutants = {
            "spent_not_reported": (powers, abilities.replace("        ItemPowers::Spent(p, fury);\n", ""), ancients, header),
            "reported_after_the_lock": (powers, abilities.replace("        ItemPowers::Spent(p, fury);\n", "").replace("        auto& s = states[p->GetGUID().GetRawValue()];",
                                        "        auto& s = states[p->GetGUID().GetRawValue()];\n        ItemPowers::Spent(p, fury);", 1), ancients, header),
            "cut_in_seconds": (powers.replace("one.value * 1000.0", "one.value"), abilities, ancients, header),
            "cut_one_skill_only": (powers.replace("std::getline(names, name, ';')", "std::getline(names, name, '|')"), abilities, ancients, header),
            "other_stat_cuts": (powers.replace('one.stat == "cooldown_cut_named_seconds"', 'one.stat == "cooldown_cut_seconds"'), abilities, ancients, header),
            "no_carry": (powers.replace("fury, clocks[guid].spentCarry)", "fury, std::map<std::string, double>())"), abilities, ancients, header),
            "situation_in_the_lock": (powers.replace("        std::vector<ItemPower::Fired> fired;\n        ItemPower::Situation seen = Seen(player);\n        {\n            std::lock_guard<std::mutex> lock(mutex);\n            std::uint64_t const guid = player->GetGUID().GetRawValue();\n            if (!clocks.count(guid) && !counts.count(guid))\n                return;\n            fired = ItemPower::SpentFires",
                                     "        std::vector<ItemPower::Fired> fired;\n        {\n            std::lock_guard<std::mutex> lock(mutex);\n            std::uint64_t const guid = player->GetGUID().GetRawValue();\n            if (!clocks.count(guid) && !counts.count(guid))\n                return;\n            ItemPower::Situation seen = Seen(player);\n            fired = ItemPower::SpentFires"), abilities, ancients, header),
            "cut_in_the_lock": (powers.replace("            fired = ItemPower::SpentFires(Data().rows, CountsOf(guid), SituationOf(guid, std::move(seen)), fury, clocks[guid].spentCarry);\n        }\n",
                                "            fired = ItemPower::SpentFires(Data().rows, CountsOf(guid), SituationOf(guid, std::move(seen)), fury, clocks[guid].spentCarry);\n            for (ItemPower::Fired const& one : fired)\n                if (one.stat == \"cooldown_cut_named_seconds\")\n                    Abilities::ReduceSkillCooldown(player, one.skill.c_str(), one.value * 1000.0);\n        }\n"),
                                abilities, ancients, header),
            "no_spent_without_a_row": (powers.replace('!Data().events.count("resource_spent")', "false"), abilities, ancients, header),
            "flag_not_read": (powers, abilities, ancients.replace('"lasts_until_death", 0) > 0;', '"lasts_until_death", 0) > 1;'), header),
            "flag_read_in_the_lock": (powers, abilities, ancients.replace("        bool const untilDeath = Combat::ItemPowers::SkillSetTo(p, \"Call of the Ancients\", \"lasts_until_death\", 0) > 0;\n        std::lock_guard<std::recursive_mutex> guard(mutex);\n",
                                                                            "        std::lock_guard<std::recursive_mutex> guard(mutex);\n        bool const untilDeath = Combat::ItemPowers::SkillSetTo(p, \"Call of the Ancients\", \"lasts_until_death\", 0) > 0;\n", 1), header),
            "still_timed": (powers, abilities, ancients.replace("untilDeath ? TEMPSUMMON_DEAD_DESPAWN : TEMPSUMMON_TIMED_DESPAWN", "TEMPSUMMON_TIMED_DESPAWN"), header),
            "timer_kept_with_the_flag": (powers, abilities, ancients.replace("untilDeath ? 0u : uint32(", "uint32("), header),
            "spent_undeclared": (powers, abilities, ancients, header.replace("void Spent(Player*, double fury);", "")),
        }
        real = (powers, abilities, ancients, header)
        for name, texts in mutants.items():
            with self.subTest(mutant=name):
                self.assertNotEqual(real, texts, name + " did not apply")
                self.assertTrue(hook_problems(*texts), name + " survived")


if __name__ == "__main__":
    unittest.main()
