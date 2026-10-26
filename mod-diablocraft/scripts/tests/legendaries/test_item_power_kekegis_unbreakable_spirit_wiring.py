"""The source-text guards of kekegis unbreakable spirit: what the server .cpp files must call, in what order and how often.

They read the .cpp files and compile nothing; the compiled rules and their mutants are in test_item_power_kekegis_unbreakable_spirit.py, which a .cpp edit then does not re-run.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import item_powers_source  # noqa: E402
from test_item_power_kekegis_unbreakable_spirit import MODULE  # noqa: E402


POWERS = item_powers_source.CPP


TEMPEST = MODULE / "src/classes/monk/dc_monk_tempest_rush.cpp"


def body_of(text, head):
    """The function that starts at the line `head` (its whole first line), up to its closing brace at the same indent."""
    start = text.index(head + "\n")
    indent = head[:len(head) - len(head.lstrip())]
    return text[start:text.index("\n" + indent + "}\n", start)]


def reader_failures(powers, tempest):
    """What is wrong with the window's code (the source guards; [] when it is right)."""
    wrong = []

    def need(why, ok):
        if not ok:
            wrong.append(why)

    fire = body_of(powers, "        void Fire(Player* player, char const* event, std::string const& skill, double scale, Unit* target, unsigned enemies,")
    need("Fire opens the window with the fired row's number",
         'else if (one.stat == "cost_free_seconds")\n                    OpenCostFree(player, one.value);' in fire)
    opened = body_of(powers, "        void OpenCostFree(Player* player, double seconds)")
    add = "Stats::AddContribution(guid, {Source::Temporary, Stat::ResourceCostReduction, CostFreeId, 100.0, Bucket::Flat});"
    need("the window is a Temporary 100% Resource Cost Reduction", add in opened)
    need("the gear cost aura is rebuilt from it", add in opened and "Passives::RefreshModifiers(player);" in opened[opened.index(add):])
    need("the end is the rule's, kept under the lock",
         "end = until = ItemPower::CostFreeEnd(until, now, seconds);" in opened and "opened = !ItemPower::CostFreeAt(until, now);" in opened
         and opened.index("std::lock_guard<std::mutex> lock(mutex);") < opened.index("end = until"))
    need("the contribution goes on only when no window was open", "if (opened)" in opened and add in opened and opened.index("if (opened)") < opened.index(add))
    need("the end is on the player's own event queue",
         "player->m_Events.AddEventAtOffset([player, end] { CloseCostFree(player, end); }, Milliseconds(end - now));" in opened)
    closed = body_of(powers, "        void CloseCostFree(Player* player, std::uint32_t end)")
    remove = "Stats::RemoveContribution(guid, Source::Temporary, Stat::ResourceCostReduction, CostFreeId);"
    need("only the window's own end closes it", "if (at == costFree.end() || at->second != end)\n                    return;" in closed)
    need("the close takes the 100% off and rebuilds the aura", remove in closed and "Passives::RefreshModifiers(player);" in closed[closed.index(remove):]
         if remove in closed else False)
    reader = body_of(powers, "    bool CostFree(Player const* player)")
    need("CostFree is the rule on the player's end", "return at != costFree.end() && ItemPower::CostFreeAt(at->second, getMSTime());" in reader)
    need("the readers take no Seen", "Seen(" not in reader and "Seen(" not in opened and "Seen(" not in closed)
    need("a logout forgets the window", "costFree.erase(player->GetGUID().GetRawValue());" in body_of(powers, "            void OnPlayerLogout(Player* player) override"))
    tick = body_of(tempest, "        void Tick(Player* player, std::uint64_t generation)")
    need("a Tempest Rush tick inside the window is not paid", "if (!covered && !ItemPowers::CostFree(player))" in tick
         and tick.index("if (!covered && !ItemPowers::CostFree(player))") < tick.index("Resources::SpendUnits(player, Resources::Spirit, units);"))
    return wrong


class Hooks(unittest.TestCase):
    def test_the_window_reaches_every_cost(self):
        self.assertEqual([], reader_failures(POWERS.read_text(encoding="utf-8"), TEMPEST.read_text(encoding="utf-8")))

    def test_the_source_guards_fail_their_mutants(self):
        powers = POWERS.read_text(encoding="utf-8")
        tempest = TEMPEST.read_text(encoding="utf-8")
        mutants = {
            "never_opened": (POWERS, "OpenCostFree(player, one.value);", "(void)one;"),
            "a_partial_cut": (POWERS, "CostFreeId, 100.0, Bucket::Flat}", "CostFreeId, 50.0, Bucket::Flat}"),
            "aura_not_rebuilt": (POWERS, "                Stats::AddContribution(guid, {Source::Temporary, Stat::ResourceCostReduction, CostFreeId, 100.0, Bucket::Flat});\n"
                                         "                Passives::RefreshModifiers(player);\n",
                                 "                Stats::AddContribution(guid, {Source::Temporary, Stat::ResourceCostReduction, CostFreeId, 100.0, Bucket::Flat});\n"),
            "never_closed": (POWERS, "player->m_Events.AddEventAtOffset([player, end] { CloseCostFree(player, end); }, Milliseconds(end - now));", "(void)end;"),
            "any_end_closes": (POWERS, "if (at == costFree.end() || at->second != end)", "if (at == costFree.end())"),
            "close_keeps_the_cut": (POWERS, "            Stats::RemoveContribution(guid, Source::Temporary, Stat::ResourceCostReduction, CostFreeId);\n", ""),
            "reader_always_free": (POWERS, "return at != costFree.end() && ItemPower::CostFreeAt(at->second, getMSTime());", "return at != costFree.end();"),
            "logout_keeps_it": (POWERS, "                costFree.erase(player->GetGUID().GetRawValue());\n", ""),
            "tick_paid": (TEMPEST, "if (!covered && !ItemPowers::CostFree(player))", "if (!covered)"),
        }
        for name, (where, old, new) in mutants.items():
            with self.subTest(mutant=name):
                text = powers if where == POWERS else tempest
                self.assertEqual(1, text.count(old), name + " does not apply once")
                mutated = text.replace(old, new)
                self.assertTrue(reader_failures(mutated if where == POWERS else powers, mutated if where == TEMPEST else tempest), name + " survived")


if __name__ == "__main__":
    unittest.main()
