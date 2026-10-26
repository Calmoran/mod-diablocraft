"""Security fixes, C++ lane (docs/security.md G5, G1, G7; brief claude-combat-security-fixes).

G5 reads every command registration in the Claude Combat lane. G1 and G7 compile
the production rule (the header, and RespecGate cut out of dc_paragon.cpp) and
check that the handlers still reach it. No game server or database is used.
Each test names the change that must make it fail.
"""
import re
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_class_parity import SRC, definition, mutate, run

# Read-only commands: they stay at GM level (brief G5: "list which"). Anything
# else registered SEC_GAMEMASTER in these files is a state change and fails.
READ_ONLY = {
    ("classes/barbarian/dc_barbarian.cpp", "abilities"), ("combat/dc_combat.cpp", "hit"),
    ("combat/dc_combat.cpp", "aps"), ("combat/dc_combat.cpp", "cooldowns"),
    ("combat/dc_combat.cpp", "fury"), ("common/dc_economy.cpp", "balance"),
    ("common/dc_tunables.cpp", "get"), ("hardcore/dc_hardcore.cpp", ""),
    ("items/dc_stash.cpp", ""), ("monsters/dc_monster_ai.cpp", "status"),
    ("rifts/dc_rift_scripts.cpp", "affixes"), ("rifts/dc_rift_scripts.cpp", "abilities"),
    ("rifts/dc_rift_scripts.cpp", "census"), ("rifts/dc_rift_scripts.cpp", "picks"), ("rifts/dc_rift_scripts.cpp", "show"),
    ("rifts/dc_shatter.cpp", "list"), ("stats/dc_stats.cpp", "stats"),
    ("rifts/dc_rift_touchup.cpp", "show"), ("rifts/dc_rift_touchup.cpp", "hide"),
}
# Every state-changing command Claude Combat owns, by (file, sub-command).
MOVED = [
    ("common/dc_economy.cpp", "set"), ("common/dc_economy.cpp", "credit"), ("common/dc_economy.cpp", "charge"),
    ("common/dc_tunables.cpp", "reload"), ("common/dc_tunables.cpp", "set"), ("common/dc_tunables.cpp", "default"),
    ("common/dc_account_economy.cpp", "failnext"),
    ("rifts/dc_rift_scripts.cpp", "open"), ("rifts/dc_rift_scripts.cpp", "close"), ("rifts/dc_rift_scripts.cpp", "affix"),
    ("rifts/dc_rift_scripts.cpp", "champion"), ("rifts/dc_rift_scripts.cpp", "rare"), ("rifts/dc_rift_scripts.cpp", "clear"),
    ("rifts/dc_rift_scripts.cpp", "perf"), ("rifts/dc_rift_scripts.cpp", "reload"), ("rifts/dc_rift_scripts.cpp", "set"),
    ("monsters/dc_monster_ai.cpp", "reload"),
    ("rifts/dc_shatter.cpp", ""), ("rifts/dc_shatter.cpp", "spell"), ("rifts/dc_shatter.cpp", "rubble"),
    ("rifts/dc_shatter.cpp", "portal"), ("rifts/dc_shatter.cpp", "timing"), ("rifts/dc_shatter.cpp", "dist"),
    ("rifts/dc_shatter.cpp", "clean"),
    ("items/dc_items.cpp", "roll"), ("items/dc_items.cpp", "item"), ("items/dc_stash.cpp", "tabs"),
    ("classes/dc_classes.cpp", "skill"), ("classes/dc_classes.cpp", "bar"), ("classes/dc_classes.cpp", "passive"),
    ("loot/dc_loot.cpp", "loot"), ("loot/dc_loot.cpp", "buffer"),
    ("loot/dc_ground_loot.cpp", "ground"), ("paragon/dc_paragon.cpp", "xp"),
    ("hardcore/dc_hardcore.cpp", "choose"), ("hardcore/dc_hardcore.cpp", "revive"),
    ("rifts/dc_rift_patrol.cpp", "start"), ("rifts/dc_rift_patrol.cpp", "stop"),
    ("rifts/dc_rift_touchup.cpp", "add"), ("rifts/dc_rift_touchup.cpp", "remove"), ("rifts/dc_rift_touchup.cpp", "move"),
    ("rifts/dc_rift_touchup.cpp", "tag"), ("rifts/dc_rift_touchup.cpp", "density"), ("rifts/dc_rift_touchup.cpp", "nospawn"),
]
LANE = sorted({f for f, _ in MOVED} | {f for f, _ in READ_ONLY})
ENTRY = re.compile(r'\{\s*"([^"]*)"\s*,\s*([A-Za-z_:]+)\s*,\s*(SEC_[A-Z]+)\s*,')


def registrations(text):
    return [(m.group(1), m.group(3)) for m in ENTRY.finditer(text)]


class G5CommandLevels(unittest.TestCase):
    def test_every_moved_command_is_registered_at_administrator(self):
        for file, name in MOVED:
            levels = {lvl for n, lvl in registrations((SRC / file).read_text()) if n == name}
            self.assertIn("SEC_ADMINISTRATOR", levels, f"{file} .{name or '(root)'} is not level 3")

    def test_no_state_change_is_left_at_gm_level(self):
        for file in LANE:
            for name, level in registrations((SRC / file).read_text()):
                if level == "SEC_GAMEMASTER":
                    self.assertIn((file, name), READ_ONLY, f"{file} .{name}: state change at GM level")

    def test_reverting_one_command_is_caught(self):
        text = (SRC / "common/dc_economy.cpp").read_text()
        reverted = mutate(text, '{"credit", CreditCommand, SEC_ADMINISTRATOR', '{"credit", CreditCommand, SEC_GAMEMASTER')
        left = [n for n, lvl in registrations(reverted) if lvl == "SEC_GAMEMASTER" and ("common/dc_economy.cpp", n) not in READ_ONLY]
        self.assertEqual(left, ["credit"])

    def test_player_bridge_commands_stay_player(self):
        # What the addon and Lua run through Player:RunCommand must not move.
        for file, name in [("items/dc_inventory.cpp", n) for n in ("equip", "unequip", "sheet", "slot")] + \
                [("paragon/dc_paragon.cpp", n) for n in ("allocate", "deallocate", "respec", "open", "sync", "")] + \
                [("items/dc_items.cpp", "socket"), ("items/dc_stash.cpp", "move"), ("items/dc_stash.cpp", "buytab"),
                 ("rifts/dc_rift_scripts.cpp", "status")]:
            levels = {lvl for n, lvl in registrations((SRC / file).read_text()) if n == name}
            self.assertIn("SEC_PLAYER", levels, f"{file} .{name or '(root)'}")


class G1SynchronousCommits(unittest.TestCase):
    def test_handlers_no_longer_commit_on_the_sync_connection(self):
        classes = (SRC / "classes/dc_classes.cpp").read_text()
        paragon = (SRC / "paragon/dc_paragon.cpp").read_text()
        for source, marker in [(classes, "bool SetSlot("), (classes, "bool InitializeStarterBar("),
                               (classes, "bool SetPassive("), (paragon, "void StorePoints(")]:
            body = definition(source, marker)
            self.assertNotIn("DirectCommitTransaction", body, marker)
            self.assertIn("AsyncCommitTransaction", body, marker)

    def test_a_failed_commit_is_reported_not_ignored(self):
        classes = (SRC / "classes/dc_classes.cpp").read_text()
        for marker in ("bool SetSlot(", "bool InitializeStarterBar(", "bool SetPassive("):
            self.assertRegex(definition(classes, marker), r"if \(!CharacterDatabase\.AsyncCommitTransaction\(.*\)\.m_future\.get\(\)\)")
        paragon = definition((SRC / "paragon/dc_paragon.cpp").read_text(), "void StorePoints(")
        self.assertIn("committed && ReadPoints", paragon)
        self.assertIn("Need(saved,", paragon)


class G1RespecCooldown(unittest.TestCase):
    source = (SRC / "paragon/dc_paragon.cpp").read_text()

    def harness(self, gate_source, body):
        return r'''
#include <cassert>
#include <chrono>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <thread>
#include "dc_paragon_math.h"
namespace DC::Tunables { double cooldown = 200; double Get(std::string const&, std::string const&) { return cooldown; } }
namespace DC::Paragon {
struct Character { bool hasRespec = false; std::uint64_t lastRespecMs = 0; };
struct Probe {
''' + gate_source + r'''
};
}
using namespace DC::Paragon;
static bool Allowed(Character& c) { try { Probe::RespecGate(c); return true; } catch (std::runtime_error const&) { return false; } }
int main() {
''' + body + r'''
    return 0;
}
'''

    def gate(self):
        text = definition(self.source, "static std::uint64_t NowMs()") + "\n" + \
            definition(self.source, "static void RespecGate(")
        return text

    def test_second_respec_inside_the_cooldown_is_refused(self):
        body = r'''
    Character c;
    assert(Allowed(c));                 // first respec goes through
    assert(!Allowed(c));                // immediately again: refused
    assert(!Allowed(c));                // and still refused, a refused attempt does not extend the wait
    std::this_thread::sleep_for(std::chrono::milliseconds(260));
    assert(Allowed(c));                 // after the gap it works again
    assert(!Allowed(c));
    // A refused attempt must not extend the wait: refuse at ~150 ms of a 200 ms gap,
    // and the wait still ends 200 ms after the accepted attempt, not after the refusal.
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
    assert(!Allowed(c));                // refused, 150 ms in
    std::this_thread::sleep_for(std::chrono::milliseconds(90));
    assert(Allowed(c));                 // 240 ms after the accepted one, only 90 after the refusal
    DC::Tunables::cooldown = 0;
    assert(Allowed(c) && Allowed(c));   // a cooldown of 0 is no gap
'''
        ok, out = run(self.harness(self.gate(), body))
        self.assertTrue(ok, out)

    def test_negative_cooldown_is_no_gap(self):
        ok, out = run(self.harness(self.gate(), r'''
    DC::Tunables::cooldown = -1;
    Character c;
    assert(Allowed(c) && Allowed(c));   // a negative row is clamped to 0, not cast to a huge uint64
'''))
        self.assertTrue(ok, out)

    def test_removing_the_clamp_fails_the_test(self):
        broken = self.gate().replace("std::max(0.0, ", "(")
        self.assertNotEqual(broken, self.gate())
        ok, _ = run(self.harness(broken, r'''
    DC::Tunables::cooldown = -1;
    Character c;
    assert(Allowed(c) && Allowed(c));
'''))
        self.assertFalse(ok)

    def test_a_gate_that_stamps_refused_attempts_fails_the_test(self):
        broken = self.gate().replace(
            "Need(!RespecCooling(", "state.lastRespecMs = NowMs(); Need(!RespecCooling(")
        self.assertNotEqual(broken, self.gate())
        ok, _ = run(self.harness(broken, r'''
    Character c;
    assert(Allowed(c));
    std::this_thread::sleep_for(std::chrono::milliseconds(150));
    assert(!Allowed(c));
    std::this_thread::sleep_for(std::chrono::milliseconds(90));
    assert(Allowed(c));
'''))
        self.assertFalse(ok)

    def test_removing_the_gate_fails_the_test(self):
        broken = self.gate().replace("Need(!RespecCooling(", "Need(RespecCooling(")
        self.assertNotEqual(broken, self.gate())
        ok, _ = run(self.harness(broken, r'''
    Character c;
    assert(Allowed(c));
    assert(!Allowed(c));
'''))
        self.assertFalse(ok)

    def test_respec_command_goes_through_the_gate_before_the_commit(self):
        line = re.search(r"static bool Respec\(ChatHandler\* h\).*", self.source).group(0)
        self.assertLess(line.index("RespecGate(state)"), line.index("StorePoints("))
        self.assertIn("RespecCooling(", definition(self.source, "static void RespecGate("))

    def test_cooldown_is_a_tunable_row_not_a_literal(self):
        rows = (SRC.parent / "data/tunables/paragon.csv").read_text().splitlines()
        row = [r for r in rows if r.startswith("respec_cooldown_ms,")]
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0].split(",")[2], "1000")
        self.assertIn('"respec_cooldown_ms"', self.source)


class G7Identify(unittest.TestCase):
    rule = r'''
#include <cassert>
#include <cstring>
#include "../items/dc_identify_rule.h"
using DC::Identify::Refusal;
int main() {
    assert(!Refusal(true, false, false));                                   // alive, calm, free item: allowed
    assert(Refusal(true, true, false) && !std::strcmp(Refusal(true, true, false), "You cannot identify in combat."));
    assert(Refusal(true, false, true) && !std::strcmp(Refusal(true, false, true), "That item is in a trade."));
    assert(Refusal(false, false, false));                                   // dead
    return 0;
}
'''

    def test_rule_refuses_combat_trade_and_death(self):
        ok, out = run(self.rule)
        self.assertTrue(ok, out)

    def test_reverting_the_rule_fails(self):
        header = (SRC / "items/dc_identify_rule.h").read_text()
        broken = header.replace("inCombat ? ", "false ? ")
        self.assertNotEqual(header, broken)
        ok, _ = run(self.rule.replace('#include "../items/dc_identify_rule.h"', broken))
        self.assertFalse(ok)

    def test_every_door_uses_the_rule(self):
        identify = (SRC / "items/dc_identify.cpp").read_text()
        self.assertIn("Refusal(player->IsAlive(), player->IsInCombat(), shell->IsInTrade())",
                      definition(identify, "bool IdentifyOne("))
        command = definition((SRC / "items/dc_inventory.cpp").read_text(), "static bool HandleIdentify(")
        self.assertIn("Refusal(player->IsAlive(), player->IsInCombat(), item->IsInTrade())", command)

    def test_command_takes_the_usual_cast_time(self):
        command = definition((SRC / "items/dc_inventory.cpp").read_text(), "static bool HandleIdentify(")
        self.assertNotIn("IdentifyOne", command)      # no instant roll from the command
        self.assertIn("CastSpell(player, DC::Items::IdentifyItemSpell()", command)
        self.assertLess(command.index("Refusal("), command.index("CastSpell("))


if __name__ == "__main__":
    unittest.main()
