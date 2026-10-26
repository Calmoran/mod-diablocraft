"""diablocraft-rn57: items are account bound, so a trade window carries gold only.

The route is the core's own server-side hook: TradeHandler.cpp asks every
PlayerScript's OnPlayerCanSetTradeItem before an item enters a trade slot, so a
modified client that sends the packet is refused by the server, not by the UI.
This compiles the module's real TradeBlock class (pulled out of dc_inventory.cpp)
against small doubles and requires:

  * every trade slot, and a missing player, gets the refusal and `false`;
  * the player is told why, with the rule's own line;
  * the run fails when the hook is changed to let an item through;
  * gold is untouched: the class has no money code and the module hooks no
    other trade step (ruling q-0930-11: "Gold can still be traded"), and the core
    still moves money independently of the item hook.

    python mod-diablocraft/scripts/tests/items/test_trade_block.py
"""
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
from test_class_parity import MODULE, ROOT, SRC, definition, mutate
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)

INVENTORY = SRC / "items/dc_inventory.cpp"
HEADER = SRC / "items/dc_trade_rule.h"
CORE_TRADE = ROOT / ("azeroth" + "core-wotlk") / "src/server/game/Handlers/TradeHandler.cpp"

DOUBLES = r'''
#include <cassert>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include "../items/dc_trade_rule.h"
typedef uint8_t uint8;
enum PlayerHook { PLAYERHOOK_CAN_SET_TRADE_ITEM };
struct Item { };
struct WorldSession { };
struct Player { WorldSession session; WorldSession* GetSession() { return &session; } };
static std::vector<std::string> told;
struct ChatHandler {
    explicit ChatHandler(WorldSession*) { }
    void SendSysMessage(char const* text) { told.push_back(text); }
};
struct PlayerScript {
    PlayerScript(char const*, std::vector<PlayerHook>) { }
    virtual ~PlayerScript() = default;
    virtual bool OnPlayerCanSetTradeItem(Player*, Item*, uint8) { return true; }
};
namespace DC::Inventory {
%(block)s;
}
int main() {
    DC::Inventory::TradeBlock block;
    Player player;
    Item item;
    for (uint8 slot = 0; slot < 7; ++slot) {          // six traded slots and the non-traded one
        assert(!block.OnPlayerCanSetTradeItem(&player, &item, slot));
    }
    assert(told.size() == 7);
    for (auto const& line : told) assert(line == DC::Trade::ItemRefusal());
    assert(!block.OnPlayerCanSetTradeItem(nullptr, &item, 0));   // no player: still refused
    assert(std::strstr(DC::Trade::ItemRefusal(), "Gold"));
    return 0;
}
'''


def block_source():
    return definition(INVENTORY.read_text(), "class TradeBlock final : public PlayerScript")


def harness(block):
    return DOUBLES % {"block": block}


class TradeBlock(unittest.TestCase):
    def test_every_slot_refuses_an_item_and_says_why(self):
        ok, out = run(harness(block_source()))
        self.assertTrue(ok, out)

    def test_letting_an_item_through_fails_the_test(self):
        block = block_source()
        ok, _ = run(harness(mutate(block, "return false;", "return true;")))
        self.assertFalse(ok)

    def test_skipping_the_notice_fails_the_test(self):
        block = block_source()
        ok, _ = run(harness(mutate(block, "SendSysMessage(DC::Trade::ItemRefusal())",
                                   "SendSysMessage(\"\")")))
        self.assertFalse(ok)

    def test_the_script_is_registered(self):
        source = INVENTORY.read_text()
        self.assertIn('PlayerScript("dc_trade_block", {PLAYERHOOK_CAN_SET_TRADE_ITEM})', source)
        self.assertIn("new TradeBlock();", definition(source, "void RegisterScripts()"))

    def test_the_core_asks_the_hook_before_an_item_takes_a_slot(self):
        core = CORE_TRADE.read_text()
        handler = definition(core, "void WorldSession::HandleSetTradeItemOpcode(")
        self.assertIn("sScriptMgr->OnPlayerCanSetTradeItem(_player, item, tradeSlot)", handler)
        self.assertLess(handler.index("OnPlayerCanSetTradeItem"), handler.index("my_trade->SetItem("))

    def test_gold_is_not_touched(self):
        # Ruling q-0930-11: the window keeps working for gold. The refusal has no
        # money code, and no other trade step is hooked by the module.
        block = block_source()
        for word in ("Money", "money", "Gold", "gold", "Trade(", "CloseTrade"):
            self.assertNotIn(word, block.replace("DC::Trade::ItemRefusal", ""))
        for path in sorted(SRC.rglob("*.cpp")):
            text = path.read_text(encoding="utf-8", errors="replace")
            self.assertNotIn("PLAYERHOOK_CAN_INIT_TRADE", text, path.name)
            self.assertNotIn("OnPlayerCanInitTrade", text, path.name)
            if path != INVENTORY:
                self.assertNotIn("PLAYERHOOK_CAN_SET_TRADE_ITEM", text, path.name)
        # The core moves money with its own trade data, whatever the item hook says.
        accept = definition(CORE_TRADE.read_text(), "void WorldSession::HandleAcceptTradeOpcode(")
        self.assertIn("GetMoney()", accept)

    def test_the_header_is_one_line_the_player_reads(self):
        text = HEADER.read_text()
        self.assertIn("account bound", text)
        self.assertIn("Gold only", text)


if __name__ == "__main__":
    unittest.main()
