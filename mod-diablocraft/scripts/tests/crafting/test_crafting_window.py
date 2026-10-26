"""diablocraft-488x: the Artisan and Jeweler window handlers (DCARTISAN, DCJEWELER), compiled from production source.

The harness includes the real dc_bridge.h, dc_request_gap.h and dc_crafting_window.h and drives each
prefix through the router into the real handler, with a fake Game standing in for the checked
functions in dc_crafting.cpp (the core cannot be compiled here). A good action succeeds; a bad
payload, an NPC out of range, combat, trading and an over-budget burst are each refused and never
reach the game; the reply carries the result and the changes. The wiring test reads dc_crafting.cpp
and the tunables sheet, and the window Lua of diablocraft-3oqx. Every test then re-runs on a source
mutation that removes the rule it checks and requires the run to fail: a test that cannot fail
proves nothing.
"""
import csv
import re
import sys
import unittest

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import crafting_source  # noqa: E402
import harness_env
from test_class_parity import SRC, mutate
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)
from test_window_bridge import PRELUDE

BRIDGE = (SRC / "common/dc_bridge.h").read_text(encoding="utf-8")
GAP = (SRC / "common/dc_request_gap.h").read_text(encoding="utf-8")
WINDOW = (SRC / "crafting/dc_crafting_window.h").read_text(encoding="utf-8")
CRAFTING = crafting_source.source()
TUNABLES = SRC.parent / "data/tunables/crafting.csv"
# diablocraft-3oqx: the window Lua half. Its own tests (scripts/tests/crafting/test_crafting.lua and
# scripts/tests/crafting/test_jeweler.lua) drive the bridge; what is checked here is the pair of facts that make
# the SEC_ADMINISTRATOR move safe for a player.
LUA = SRC.parent / "lua/aio"
ARTISAN_LUA = (LUA / "dc_crafting.lua").read_text(encoding="utf-8")
JEWELER_LUA = (LUA / "dc_jeweler.lua").read_text(encoding="utf-8")

RIG = r'''
using namespace DC::Crafting::Window;
using DC::Bridge::Outcome;
struct Guid { std::uint64_t id; std::uint64_t GetRawValue() const { return id; } };
struct Player { Guid guid; Guid GetGUID() const { return guid; } };

// The game the handlers drive. Each action records its call, then runs `effect`, which a test sets
// to change bags and funds (or to throw, as a real function does through Need()).
struct Fake {
    std::string gate;                        // non-empty: the NPC gate refuses with this text
    std::vector<std::string> calls, gates;
    int failed = 0;
    Bags bags;
    Funds funds{true, "1000", {{102000, "5"}, {102001, "9"}}};
    std::map<std::uint64_t, Rolled> rolled;
    std::function<void()> effect;
    void Gate(Npc n) { gates.push_back(std::to_string(int(n))); if (!gate.empty()) throw std::runtime_error(gate); }
    void Run(std::string call) { calls.push_back(call); if (effect) effect(); }
    void Salvage(std::uint32_t g) { Run("salvage " + std::to_string(g)); }
    void Bulk(std::uint32_t r) { Run("bulk " + std::to_string(r)); }
    void Craft(std::uint32_t id, std::uint32_t n) { Run("craft " + std::to_string(id) + " " + std::to_string(n)); }
    void Forge(std::uint32_t id, std::uint32_t n) { Run("forge " + std::to_string(id) + " " + std::to_string(n)); }
    std::pair<std::string, bool> RepairPrice(std::uint32_t scope, std::uint32_t g) { Run("repairquote " + std::to_string(scope) + " " + std::to_string(g)); return {"987",true}; }
    void RepairItems(std::uint32_t scope, std::uint32_t g) { Run("repairitems " + std::to_string(scope) + " " + std::to_string(g)); }
    // The two read-only Mystic calls: they change nothing, so they are not "calls"; reads says what was asked.
    EnchantState state;                      // what Place answers; a test fills it
    std::vector<EnchantAffix> previewed;     // what Preview answers
    std::vector<std::string> reads;
    std::string readError;                   // non-empty: the read refuses with this text
    EnchantState Place(std::uint32_t g) { reads.push_back("place " + std::to_string(g)); if (!readError.empty()) throw std::runtime_error(readError); return state; }
    std::vector<EnchantAffix> Preview(std::uint32_t g, std::uint32_t s) { reads.push_back("preview " + std::to_string(g) + " " + std::to_string(s)); if (!readError.empty()) throw std::runtime_error(readError); return previewed; }
    void Roll(std::uint32_t g, std::uint32_t s) { Run("roll " + std::to_string(g) + " " + std::to_string(s)); }
    void Pick(std::uint32_t g, std::uint32_t c) { Run("pick " + std::to_string(g) + " " + std::to_string(c)); }
    void Repair(Npc n) { Run("repair " + std::to_string(int(n))); }
    void Transmog() { Run("transmog"); }
    void Socket(std::uint32_t g, std::uint32_t s, std::uint32_t gem) { Run("socket " + std::to_string(g) + " " + std::to_string(s) + " " + std::to_string(gem)); }
    void Combine(std::uint32_t id, std::uint32_t n) { Run("combine " + std::to_string(id) + " " + std::to_string(n)); }
    void Jewelry(std::uint32_t id, std::uint32_t n) { Run("jewelry " + std::to_string(id) + " " + std::to_string(n)); }
    std::set<std::pair<std::uint32_t, std::uint32_t>> filled;   // (item guid, socket seq) holding a gem
    bool SocketFilled(std::uint32_t g, std::uint32_t s) { asked.push_back(std::to_string(g) + ":" + std::to_string(s)); return filled.count({g, s}) != 0; }
    std::vector<std::string> asked;
    Bags Carried() { return bags; }
    Funds Balance() { return funds; }
    std::optional<Rolled> Detail(std::uint64_t g, bool offers) {
        auto f = rolled.find(g);
        if (f == rolled.end()) return std::nullopt;
        Rolled r = f->second;
        if (!offers) r.offers.clear();
        return r;
    }
    void Failed() { ++failed; }
};

struct Rig {
    Fake game;
    Player player{{7}};
    std::vector<std::string> sent;
    DC::Bridge::Router<Player> router{[this](Player*, std::string const& prefix, std::string const& record) { sent.push_back(prefix + "\t" + record); }};
    Rig(double burst = 50, double rate = 50) {
        DC::Tunables::rows["crafting/artisan_burst"] = burst;
        DC::Tunables::rows["crafting/artisan_per_second"] = rate;
        DC::Tunables::rows["crafting/jeweler_burst"] = burst;
        DC::Tunables::rows["crafting/jeweler_per_second"] = rate;
        bool a = router.Add("DCARTISAN", {"crafting", "artisan_burst", "artisan_per_second"},
            [this](Player&, DC::Bridge::Request const& r, DC::Bridge::Wire<Player> const& w) { Artisan(game, r, w); });
        bool j = router.Add("DCJEWELER", {"crafting", "jeweler_burst", "jeweler_per_second"},
            [this](Player&, DC::Bridge::Request const& r, DC::Bridge::Wire<Player> const& w) { Jeweler(game, r, w); });
        assert(a && j);
    }
    Outcome send(std::string const& prefix, std::string const& payload, std::uint64_t now = 1000) {
        sent.clear();
        return router.Dispatch(&player, prefix + (payload.empty() ? "" : "\t" + payload), now);
    }
    Outcome artisan(std::string const& p, std::uint64_t now = 1000) { return send("DCARTISAN", p, now); }
    Outcome jeweler(std::string const& p, std::uint64_t now = 1000) { return send("DCJEWELER", p, now); }
    bool has(std::string const& record) const { for (auto const& s : sent) if (s == record) return true; return false; }
    bool starts(std::string const& head) const { for (auto const& s : sent) if (s.compare(0, head.size(), head) == 0) return true; return false; }
    std::string refusal() const { return sent.size() == 1 && sent[0].find("\tX|") != std::string::npos ? sent[0] : ""; }
};
'''

EXTRA_INCLUDES = "#include <functional>\n#include <optional>\n#include <set>\n#include <cstdio>\n"


def compile_window(body, window=WINDOW, bridge=BRIDGE):
    code = (EXTRA_INCLUDES + PRELUDE + GAP.replace('#ifndef DC_REQUEST_GAP_H', '#ifndef DC_REQUEST_GAP_H_T')
            + '\n' + bridge.replace('#include "dc_request_gap.h"', '').replace('#include "dc_tunables.h"', '')
            + '\n' + window.replace('#include "dc_bridge.h"', '') + RIG
            + "\nint main() {\n" + body + "\n    return 0;\n}\n")
    code = code.replace("#define DC_REQUEST_GAP_H\n", "#define DC_REQUEST_GAP_H_T\n")
    return run(code)


def both(test, body, old, new, source="window"):
    """Passes on production source, fails on the mutated one."""
    ok, out = compile_window(body)
    test.assertTrue(ok, out)
    if source == "window":
        ok, out = compile_window(body, window=mutate(WINDOW, old, new))
    else:
        ok, out = compile_window(body, bridge=mutate(BRIDGE, old, new))
    test.assertFalse(ok, "mutation survived: " + new)


class GoodActions(unittest.TestCase):
    def test_every_verb_reaches_the_game_with_its_parsed_fields(self):
        both(self, r'''
    Rig rig;
    struct Case { bool artisan; char const* payload; char const* call; };
    Case cases[] = {
        {true, "salvage\t41", "salvage 41"}, {true, "bulk\t2", "bulk 2"}, {true, "craft\t9\t3", "craft 9 3"},
        {true, "roll\t41\t5", "roll 41 5"}, {true, "pick\t41\t3", "pick 41 3"},
        {true, "repair\t0", "repair 0"}, {true, "repair\t1", "repair 1"},
        {true, "transmog", "transmog"},
        {false, "socket\t41\t2\t77", "socket 41 2 77"}, {false, "remove\t41\t2", "socket 41 2 0"},
        {false, "combine\t8", "combine 8 1"}, {false, "combine\t8\t5", "combine 8 5"},
        {false, "craft\t364041", "jewelry 364041 1"}, {false, "craft\t364042\t3", "jewelry 364042 3"},
    };
    for (auto const& c : cases) {
        rig.game.calls.clear();
        auto out = c.artisan ? rig.artisan(c.payload) : rig.jeweler(c.payload);
        assert(out == Outcome::Handled);
        assert(rig.game.calls.size() == 1 && rig.game.calls[0] == c.call);
        assert(rig.sent.size() >= 2 && rig.sent.back().find("\tE|") != std::string::npos);   // a result and an end
        assert(rig.sent.front().find("\tR|") != std::string::npos);
    }
''', "[&] { game.Combine(id, count); }", "[&] { game.Combine(id, 1); }")

    def test_craft_without_a_count_crafts_one_as_the_command_does(self):
        both(self, r'''
    Rig rig;
    assert(rig.artisan("craft\t9") == Outcome::Handled);
    assert(rig.game.calls.size() == 1 && rig.game.calls[0] == "craft 9 1");
''', "auto count = OptionalUint(request, 2, 1, Max, 1, bad);\n            Execute(game, wire, \"craft\", Npc::Blacksmith",
             "auto count = OptionalUint(request, 2, 1, Max, 0, bad);\n            Execute(game, wire, \"craft\", Npc::Blacksmith")

    def test_repair_without_a_number_is_the_blacksmith(self):
        both(self, r'''
    Rig rig;
    assert(rig.artisan("repair") == Outcome::Handled);
    assert(rig.game.calls[0] == "repair 0" && rig.game.gates[0] == "0");
''', "auto which = OptionalUint(request, 1, 0, 1, 0, bad);", "auto which = OptionalUint(request, 1, 0, 1, 1, bad);")


class JewelerWindow(unittest.TestCase):
    """The Jeweler window brief (diablocraft-jeweler-window): sockets away from the Jeweler, no repair, combine count."""

    def test_an_empty_socket_needs_nobody_and_every_other_socket_request_needs_the_jeweler(self):
        both(self, r'''
    Rig rig;
    rig.game.filled.insert({41, 1});                                  // socket 1 holds a gem, socket 0 is empty
    assert(rig.jeweler("socket\t41\t0\t77") == Outcome::Handled);      // an empty socket: no NPC
    assert(rig.game.gates.size() == 1 && rig.game.gates[0] == std::to_string(int(Npc::Nobody)));
    rig.game.gates.clear();
    assert(rig.jeweler("socket\t41\t1\t77") == Outcome::Handled);      // over a filled socket: the Jeweler
    assert(rig.game.gates[0] == std::to_string(int(Npc::Jeweler)));
    rig.game.gates.clear();
    assert(rig.jeweler("remove\t41\t0") == Outcome::Handled);           // a removal is the Jeweler's even for an empty row
    assert(rig.jeweler("remove\t41\t1") == Outcome::Handled);
    assert(rig.jeweler("combine\t3") == Outcome::Handled);
    for (auto const& g : rig.game.gates) assert(g == std::to_string(int(Npc::Jeweler)));
    assert(rig.game.gates.size() == 3);
''', "return gemGiven && !socketFilled ? Npc::Nobody : Npc::Jeweler;", "return Npc::Jeweler;")

    def test_a_removal_is_never_gated_on_nobody(self):
        both(self, r'''
    Rig rig;
    rig.jeweler("remove\t41\t0");
    assert(rig.game.gates.size() == 1 && rig.game.gates[0] == std::to_string(int(Npc::Jeweler)));
''', "Execute(game, wire, \"remove\", Npc::Jeweler,", "Execute(game, wire, \"remove\", Npc::Nobody,")

    def test_a_socket_far_from_the_jeweler_is_still_refused_when_the_player_cannot_act(self):
        # Nobody is not "no gate": the player's own state (dead, in combat, trading) still stops it.
        both(self, r'''
    Rig rig;
    rig.game.gate = "Finish combat or trading before using an artisan.";
    assert(rig.jeweler("socket\t41\t0\t77") == Outcome::Refused && rig.game.calls.empty());
    assert(rig.game.gates.size() == 1 && rig.game.gates[0] == std::to_string(int(Npc::Nobody)));
''', "        Plain([&] { game.Gate(npc); });", "        if (npc != Npc::Nobody) Plain([&] { game.Gate(npc); });")

    def test_the_jeweler_no_longer_repairs(self):
        both(self, r'''
    Rig rig;
    for (auto p : {"repair", "repair\t0", "repair\t1"}) {
        assert(rig.jeweler(p) == Outcome::Refused);
        assert(rig.refusal() == "DCJEWELER\tX|Unknown Jeweler action." || rig.refusal() == std::string("DCJEWELER\tX|") + DC::Bridge::TextMalformed);
        assert(rig.game.calls.empty() && rig.game.gates.empty());
    }
    assert(rig.artisan("repair\t0") == Outcome::Handled && rig.game.calls[0] == "repair 0");   // the other artisans keep theirs
    assert(rig.artisan("repair\t1") == Outcome::Handled && rig.game.calls[1] == "repair 1");
''', "        else\n            throw Bridge::Refusal(\"Unknown Jeweler action.\");",
             "        else if (*verb == \"repair\")\n            Execute(game, wire, \"repair\", Npc::Jeweler, 0, false, [&] { game.Repair(Npc::Jeweler); });\n        else\n            throw Bridge::Refusal(\"Unknown Jeweler action.\");")

    def test_combine_takes_the_count_it_was_asked_for(self):
        both(self, r'''
    Rig rig;
    assert(rig.jeweler("combine\t8\t5") == Outcome::Handled && rig.game.calls.back() == "combine 8 5");
    assert(rig.jeweler("combine\t8") == Outcome::Handled && rig.game.calls.back() == "combine 8 1");   // the old request still works
    assert(rig.jeweler("combine\t8\t4294967295") == Outcome::Handled && rig.game.calls.back() == "combine 8 4294967295");
    assert(rig.jeweler("combine\t8\t0") == Outcome::Refused && rig.jeweler("combine\t8\t4294967296") == Outcome::Refused);
    assert(rig.game.calls.size() == 3);
''', "            auto count = OptionalUint(request, 2, 1, Max, 1, bad);\n            Execute(game, wire, \"combine\"",
             "            auto count = OptionalUint(request, 2, 1, 1, 1, bad);\n            Execute(game, wire, \"combine\"")

    def test_craft_jewelry_is_the_jewelers_own_and_reports_the_items_it_made(self):
        # Craft Jewelry (diablocraft-0vt07.15): `craft` on DCJEWELER reaches Jewelry(), never the Blacksmith's Craft/Forge,
        # behind the Jeweler's gate, and its result counts the items made (true), as the Blacksmith's craft does.
        both(self, r'''
    Rig rig;
    rig.game.effect = [&] { rig.game.bags[900] = {100466, 1, 255, 23}; };
    assert(rig.jeweler("craft\t364042\t1") == Outcome::Handled);
    assert(rig.game.calls.size() == 1 && rig.game.calls[0] == "jewelry 364042 1");
    assert(rig.game.gates.size() == 1 && rig.game.gates[0] == std::to_string(int(Npc::Jeweler)));
    assert(rig.sent.front() == "DCJEWELER\tR|craft|1" && rig.sent.back() == "DCJEWELER\tE|craft");
    assert(rig.jeweler("craft\t364041") == Outcome::Handled && rig.game.calls.back() == "jewelry 364041 1");   // count left out: one
    assert(rig.jeweler("craft\t364041\t4294967295") == Outcome::Handled && rig.game.calls.back() == "jewelry 364041 4294967295");
    assert(rig.jeweler("craft\t364041\t0") == Outcome::Refused && rig.jeweler("craft\t0") == Outcome::Refused);
    assert(rig.game.calls.size() == 3);
''', "Execute(game, wire, \"craft\", Npc::Jeweler, 0, true, [&] { game.Jewelry(id, count); });",
             "Execute(game, wire, \"craft\", Npc::Jeweler, 0, false, [&] { game.Jewelry(id, count); });")

    def test_craft_jewelry_count_left_out_is_one_and_the_gate_is_the_jewelers(self):
        both(self, r'''
    Rig rig;
    assert(rig.jeweler("craft\t364041") == Outcome::Handled && rig.game.calls.back() == "jewelry 364041 1");
''', "auto count = OptionalUint(request, 2, 1, Max, 1, bad);\n            Execute(game, wire, \"craft\", Npc::Jeweler",
             "auto count = OptionalUint(request, 2, 1, Max, 0, bad);\n            Execute(game, wire, \"craft\", Npc::Jeweler")
        both(self, r'''
    Rig rig;
    assert(rig.jeweler("craft\t364041\t2") == Outcome::Handled);
    assert(rig.game.gates.size() == 1 && rig.game.gates[0] == std::to_string(int(Npc::Jeweler)));
''', "Execute(game, wire, \"craft\", Npc::Jeweler,", "Execute(game, wire, \"craft\", Npc::Blacksmith,")

    def test_one_combine_request_is_one_request(self):
        # The window sends ONE request per click (flood limit): a count of 5 is a single dispatch and a
        # single reply, never five.
        both(self, r'''
    Rig rig;
    assert(rig.jeweler("combine\t8\t5") == Outcome::Handled);
    assert(rig.game.calls.size() == 1 && rig.game.gates.size() == 1);
    assert(rig.sent.size() == 2 && rig.sent.front() == "DCJEWELER\tR|combine|0" && rig.sent.back() == "DCJEWELER\tE|combine");
''', "wire.Record({\"E\", verb});", "wire.Record({\"E\", verb}); wire.Record({\"E\", verb});")

class MysticWindow(unittest.TestCase):
    """diablocraft-xw2m: the Mystic's verbs and the records the window draws (docs/contracts/mystic-enchant-messages.md)."""

    OPEN = r'''
    Rig rig;
    auto& s = rig.game.state;
    s.guid = 41; s.entry = 30001; s.rarity = "legendary"; s.attempts = 2; s.bind = true;
    s.lines = {{0, "int", "primary", 0, 877, 0, 626, 750, 0, 0}, {5, "wpnarc", "primary", 1, 1252.5, 1471, 1177, 1439, 1410, 1788}};
    s.gold = "1800"; s.goldOk = true;
    s.materials = {{102002, "3", "12", "Arcane Dust", true}, {102003, "3", "0", "Veiled Crystal", false}};
'''

    def test_place_sends_the_item_its_lines_its_price_and_its_materials_in_that_order(self):
        both(self, self.OPEN + r'''
    assert(rig.artisan("place\t41") == Outcome::Handled);
    assert(rig.game.calls.empty() && rig.game.reads.size() == 1 && rig.game.reads[0] == "place 41");
    std::vector<std::string> want = {
        "DCARTISAN\tR|place|41",
        "DCARTISAN\tN|41|30001|legendary|0|2|1|0",
        "DCARTISAN\tL|41|0:int:primary:0:877:0:626:750:0:0|5:wpnarc:primary:1:1252.5:1471:1177:1439:1410:1788",
        "DCARTISAN\tP|41|1800|1",
        "DCARTISAN\tT|41|102002|3|12|1|Arcane Dust",
        "DCARTISAN\tT|41|102003|3|0|0|Veiled Crystal",
        "DCARTISAN\tE|place"};
    assert(rig.sent == want);
''', 'state.bind ? "1" : "0", state.pending ? "1" : "0"});', '"0", state.pending ? "1" : "0"});')

    def test_a_waiting_roll_sends_its_three_choices_numbered_from_one_and_nothing_else_about_the_item(self):
        both(self, self.OPEN + r'''
    s.pending = true; s.enchanted = true;
    s.choices = {{0, "int", "primary", 0, 877, 0, 626, 750, 0, 0}, {0, "cdr", "primary", 0, 9, 0, 6, 9, 0, 0},
                 {0, "wpnlit", "primary", 0, 1163, 1446, 1177, 1439, 1410, 1788}};
    assert(rig.artisan("place\t41") == Outcome::Handled);
    std::vector<std::string> want = {
        "DCARTISAN\tR|place|41",
        "DCARTISAN\tN|41|30001|legendary|1|2|1|1",
        "DCARTISAN\tC|41|1:int:primary:877:0:626:750:0:0|2:cdr:primary:9:0:6:9:0:0|3:wpnlit:primary:1163:1446:1177:1439:1410:1788",
        "DCARTISAN\tE|place"};
    assert(rig.sent == want);   // no L, P or T: nothing else can be done with the item until one is picked
''', "if (state.pending)\n        {\n            unsigned number = 0;", "if (false)\n        {\n            unsigned number = 0;")

    def test_the_first_choice_is_number_one(self):
        both(self, self.OPEN + r'''
    s.pending = true;
    s.choices = {{0, "int", "primary", 0, 877, 0, 626, 750, 0, 0}, {0, "cdr", "primary", 0, 9, 0, 6, 9, 0, 0}, {0, "ms", "primary", 0, 5, 0, 1, 12, 0, 0}};
    rig.artisan("place\t41");
    assert(rig.has("DCARTISAN\tC|41|1:int:primary:877:0:626:750:0:0|2:cdr:primary:9:0:6:9:0:0|3:ms:primary:5:0:1:12:0:0"));
''', "Packed(choice, Num(++number), false)", "Packed(choice, Num(number++), false)")

    def test_a_place_that_is_refused_shows_the_servers_own_words_and_sends_no_item(self):
        both(self, self.OPEN + r'''
    rig.game.readError = "The Mystic only enchants rare, legendary and set items.";
    assert(rig.artisan("place\t41") == Outcome::Refused);
    assert(rig.sent.size() == 1 && rig.sent[0] == "DCARTISAN\tX|The Mystic only enchants rare, legendary and set items.");
''', "        catch (std::exception const& error)\n        {\n            throw Bridge::Refusal(error.what());",
             "        catch (std::exception const& error)\n        {\n            throw;")

    def test_preview_sends_what_the_line_can_become_with_the_range_of_each(self):
        both(self, self.OPEN + r'''
    rig.game.previewed = {{5, "wpnarc", "primary", 0, 0, 0, 1177, 1439, 1410, 1788}, {5, "wpnlit", "primary", 0, 0, 0, 1177, 1439, 1410, 1788}};
    assert(rig.artisan("preview\t41\t5") == Outcome::Handled);
    std::vector<std::string> want = {
        "DCARTISAN\tR|preview|41",
        "DCARTISAN\tV|41|5|wpnarc:primary:1177:1439:1410:1788|wpnlit:primary:1177:1439:1410:1788",
        "DCARTISAN\tE|preview"};
    assert(rig.sent == want && rig.game.calls.empty() && rig.game.reads[0] == "preview 41 5");
''', 'parts.push_back(e.id + ":" + e.kind + ":" + Number(e.min) + ":" + Number(e.max) + ":" + Number(e.min2) +\n                            ":" + Number(e.max2));',
             'parts.push_back(e.id + ":" + e.kind + ":" + Number(e.min) + ":" + Number(e.max) + ":" + Number(e.min) +\n                            ":" + Number(e.max2));')

    def test_a_roll_reports_what_it_paid_and_then_the_waiting_choices(self):
        both(self, self.OPEN + r'''
    rig.game.effect = [&] { rig.game.funds.gold = "400"; rig.game.funds.materials[102001] = "6"; };
    s.pending = true; s.enchanted = true; s.attempts = 3; s.bind = false;
    s.choices = {{0, "int", "primary", 0, 877, 0, 626, 750, 0, 0}, {0, "cdr", "primary", 0, 9, 0, 6, 9, 0, 0}, {0, "ms", "primary", 0, 5, 0, 1, 12, 0, 0}};
    assert(rig.artisan("roll\t41\t0") == Outcome::Handled);
    assert(rig.game.calls.size() == 1 && rig.game.calls[0] == "roll 41 0" && rig.game.gates[0] == std::to_string(int(Npc::Mystic)));
    std::vector<std::string> want = {
        "DCARTISAN\tR|roll|0",
        "DCARTISAN\tB|400",
        "DCARTISAN\tM|102001:6",
        "DCARTISAN\tN|41|30001|legendary|1|3|0|1",
        "DCARTISAN\tC|41|1:int:primary:877:0:626:750:0:0|2:cdr:primary:9:0:6:9:0:0|3:ms:primary:5:0:1:12:0:0",
        "DCARTISAN\tE|roll"};
    assert(rig.sent == want);
''', "        tail();\n", "")

    def test_a_pick_reports_the_item_as_it_now_is(self):
        both(self, self.OPEN + r'''
    s.enchanted = true; s.bind = false;
    s.lines = {s.lines[1]};
    assert(rig.artisan("pick\t41\t2") == Outcome::Handled);
    assert(rig.game.calls.size() == 1 && rig.game.calls[0] == "pick 41 2");
    assert(rig.sent.front() == "DCARTISAN\tR|pick|0" && rig.sent.back() == "DCARTISAN\tE|pick");
    assert(rig.has("DCARTISAN\tN|41|30001|legendary|1|2|0|0") && rig.starts("DCARTISAN\tL|41|5:wpnarc"));
    assert(rig.has("DCARTISAN\tP|41|1800|1") && !rig.starts("DCARTISAN\tC|"));
''', "            Execute(game, wire, \"pick\", Npc::Mystic, 0, false, [&] { game.Pick(guid, choice); },\n                    [&] { SendEnchant(wire, game.Place(guid)); });",
             "            Execute(game, wire, \"pick\", Npc::Mystic, 0, false, [&] { game.Pick(guid, choice); });")

    def test_a_pick_is_one_of_the_three_choices(self):
        both(self, self.OPEN + r'''
    for (auto p : {"pick\t41\t0", "pick\t41\t4", "pick\t41\t-1", "pick\t41\tx", "pick\t41"}) {
        assert(rig.artisan(p) == Outcome::Refused && rig.game.calls.empty());
    }
    assert(rig.artisan("pick\t41\t0") == Outcome::Refused && rig.refusal() == "DCARTISAN\tX|That choice is not available.");
    for (auto p : {"pick\t41\t1", "pick\t41\t2", "pick\t41\t3"}) assert(rig.artisan(p) == Outcome::Handled);
    assert(rig.game.calls.size() == 3);
''', "RequiredUint(request, 2, 1, EnchantChoices,", "RequiredUint(request, 2, 0, EnchantChoices,")

    def test_the_old_verbs_are_gone(self):
        both(self, self.OPEN + r'''
    for (auto p : {"offer\t41\t0", "choose\t41\t0", "quote\t41"}) {
        assert(rig.artisan(p) == Outcome::Refused);
        assert(rig.refusal() == "DCARTISAN\tX|Unknown artisan action.");
        assert(rig.game.calls.empty() && rig.game.gates.empty());
    }
''', '        else if (*verb == "roll")', '        else if (*verb == "offer")\n            Execute(game, wire, "offer", Npc::Mystic, 0, false, [&] { game.Roll(0, 0); });\n        else if (*verb == "roll")')


class Refusals(unittest.TestCase):
    def test_a_bad_payload_is_refused_and_never_reaches_the_game(self):
        both(self, r'''
    Rig rig;
    char const* artisan[] = {"", "nope", "salvage", "salvage\t0", "salvage\t-1", "salvage\t+5", "salvage\t 5", "salvage\t0x10",
        "salvage\t4294967296", "salvage\t99999999999", "salvage\t5\t6", "salvage\t", "bulk", "craft", "craft\t0", "craft\t5\t0",
        "craft\t5\tx", "craft\t5\t1\t1", "place", "place\t0", "place\t4\t1", "preview\t4", "preview\t4\t-1", "roll\t4",
        "roll\t4\t-1", "roll\t0\t1", "pick\t4", "pick\t4\t0", "pick\t4\t4", "pick\t4\t-1", "pick\t0\t1", "offer\t4\t1",
        "choose\t4\t1", "quote\t4", "repair\t2", "repair\tx",
        "repair\t0\t0", "transmog\t1", "SALVAGE\t1x", "sal-vage\t1"};
    for (auto p : artisan) {
        auto out = rig.artisan(p);
        assert(out == Outcome::Refused);
        assert(rig.refusal() != "");
        assert(rig.game.calls.empty() && rig.game.gates.empty());
    }
    char const* jeweler[] = {"socket\t4\t2", "socket\t4\t2\t0", "socket\t0\t2\t9", "socket\t4\t-2\t9", "socket\t4\t2\t9\t1", "remove\t4",
        "remove\t0\t1", "combine", "combine\t0", "combine\t1\t0", "combine\t1\tx", "combine\t1\t-2", "combine\t1\t2\t3",
        "combine\t1\t4294967296", "repair\t0", "forge\t1", "craft", "craft\t0", "craft\t364041\t0", "craft\t364041\tx",
        "craft\t364041\t1\t1", "craft\t364041\t4294967296"};
    for (auto p : jeweler) {
        auto out = rig.jeweler(p);
        assert(out == Outcome::Refused);
        assert(rig.game.calls.empty() && rig.game.gates.empty());
    }
    // a control byte and an over-long message die in the bridge's parser, before the handler
    assert(rig.artisan(std::string("salvage\t4") + '\x01') == Outcome::Refused && rig.game.calls.empty());
    assert(rig.artisan("salvage\t" + std::string(300, '1')) == Outcome::Refused && rig.game.calls.empty());
''', "        if (request.Count() > most || request.Count() < least)", "        if (false)")

    def test_a_number_field_is_bounded(self):
        both(self, r'''
    Rig rig;
    assert(rig.artisan("salvage\t0") == Outcome::Refused && rig.game.calls.empty());
    assert(rig.artisan("craft\t1\t4294967296") == Outcome::Refused && rig.game.calls.empty());
    assert(rig.artisan("salvage\t4294967295") == Outcome::Handled && rig.game.calls[0] == "salvage 4294967295");
''', "        auto value = request.Uint(index, low, high);\n        if (!value)\n            throw Bridge::Refusal(message);\n        return *value;\n    }\n    inline void Exactly",
             "        auto value = request.Uint(index, 0, 4294967295u);\n        if (!value)\n            throw Bridge::Refusal(message);\n        return *value;\n    }\n    inline void Exactly")

    def test_an_npc_that_is_out_of_range_dead_in_combat_or_trading_is_refused(self):
        both(self, r'''
    char const* reasons[] = {"Stand next to the artisan.", "A living player is required.",
                             "Finish combat or trading before using an artisan."};
    char const* artisan[] = {"salvage\t4", "bulk\t1", "craft\t3\t1", "place\t4", "preview\t4\t1", "roll\t4\t1", "pick\t4\t1", "repair\t0", "transmog"};
    char const* jeweler[] = {"socket\t4\t1\t9", "remove\t4\t1", "combine\t3", "combine\t3\t5", "craft\t364041", "craft\t364042\t2"};
    for (auto reason : reasons) {
        Rig rig;
        rig.game.gate = reason;
        rig.game.effect = [&] { assert(false && "the game acted past a refused gate"); };
        for (auto p : artisan) {
            assert(rig.artisan(p) == Outcome::Refused);
            assert(rig.sent.size() == 1 && rig.sent[0] == std::string("DCARTISAN\tX|") + reason);   // the command's own text
            assert(rig.game.calls.empty());
        }
        for (auto p : jeweler) {
            assert(rig.jeweler(p) == Outcome::Refused);
            assert(rig.sent[0] == std::string("DCJEWELER\tX|") + reason && rig.game.calls.empty());
        }
    }
''', "        Plain([&] { game.Gate(npc); });", "        (void)npc;")

    def test_the_gates_own_words_reach_the_window_not_a_generic_line(self):
        both(self, r'''
    Rig rig;
    rig.game.gate = "Stand next to the artisan.";
    assert(rig.jeweler("combine\t3") == Outcome::Refused);
    assert(rig.refusal() == "DCJEWELER\tX|Stand next to the artisan.");
''', "        catch (std::exception const& error)\n        {\n            throw Bridge::Refusal(error.what());",
             "        catch (std::exception const& error)\n        {\n            throw;")

    def test_the_read_only_verbs_are_gated_too(self):
        both(self, r'''
    Rig rig;
    rig.game.gate = "Stand next to the artisan.";
    assert(rig.artisan("place\t4") == Outcome::Refused && rig.game.calls.empty());
    assert(rig.artisan("preview\t4\t1") == Outcome::Refused && rig.game.calls.empty());
    assert(rig.artisan("transmog") == Outcome::Refused && rig.game.calls.empty());
    assert(rig.game.gates.size() == 3);
''', "            Plain([&] { game.Gate(Npc::Mystic); game.Transmog(); });", "            Plain([&] { game.Transmog(); });")

    def test_each_verb_is_gated_on_its_own_npc(self):
        both(self, r'''
    Rig rig;
    rig.artisan("salvage\t4"); rig.artisan("roll\t4\t0"); rig.jeweler("combine\t3"); rig.artisan("repair\t1");
    rig.jeweler("remove\t4\t1");
    assert(rig.game.gates.size() == 5);
    assert(rig.game.gates[0] == "0" && rig.game.gates[1] == "1" && rig.game.gates[2] == "2" && rig.game.gates[3] == "1");
    assert(rig.game.gates[4] == "2");
''', "            Execute(game, wire, \"roll\", Npc::Mystic,", "            Execute(game, wire, \"roll\", Npc::Blacksmith,")

    def test_an_over_budget_burst_is_dropped_without_a_reply(self):
        both(self, r'''
    Rig rig(3, 1);
    assert(rig.artisan("salvage\t4", 1000) == Outcome::Handled);
    assert(rig.artisan("salvage\t4", 1000) == Outcome::Handled);
    assert(rig.artisan("salvage\t4", 1000) == Outcome::Handled);
    rig.game.calls.clear();
    assert(rig.artisan("salvage\t4", 1000) == Outcome::Throttled);
    assert(rig.sent.empty() && rig.game.calls.empty());               // no reply, no action
    assert(rig.jeweler("combine\t3", 1000) == Outcome::Handled);      // the Jeweler has its own bucket
    assert(rig.artisan("salvage\t4", 2000) == Outcome::Handled);      // one token back after a second
''', "                return Outcome::Throttled;", "                {}", source="bridge")

    def test_a_route_with_no_tunable_rows_is_closed(self):
        ok, out = compile_window(r'''
    Rig rig(0, 0);
    assert(rig.artisan("salvage\t4") == Outcome::Throttled && rig.jeweler("combine\t3") == Outcome::Throttled);
    assert(rig.sent.empty() && rig.game.calls.empty());
''')
        self.assertTrue(ok, out)

    def test_a_game_error_reaches_the_window_as_its_own_text(self):
        both(self, r'''
    Rig rig;
    rig.game.effect = [&] { throw std::runtime_error("Not enough Death's Breath: you have 1 of 4."); };
    assert(rig.artisan("craft\t9\t2") == Outcome::Refused);
    assert(rig.refusal() == "DCARTISAN\tX|Not enough Death's Breath: you have 1 of 4.");
    assert(rig.game.failed == 1);                                     // the account operation was rolled back
''', "failure = error.what();", "failure = \"\";")

    def test_a_failed_action_rolls_the_account_operation_back(self):
        both(self, r'''
    Rig rig;
    rig.game.effect = [&] { throw std::runtime_error("Gold changed before combining."); };
    rig.jeweler("combine\t3");
    assert(rig.game.failed == 1);
    rig.game.effect = nullptr;
    rig.jeweler("combine\t3");
    assert(rig.game.failed == 1);                                     // a good action does not
''', "            game.Failed();\n", "")

    def test_a_failed_action_sends_no_result(self):
        both(self, r'''
    Rig rig;
    rig.game.effect = [&] { throw std::runtime_error("Make room for the returned gems and materials first."); };
    rig.artisan("salvage\t4");
    assert(!rig.starts("DCARTISAN\tR|") && !rig.starts("DCARTISAN\tE|") && rig.starts("DCARTISAN\tX|"));
''', "            throw Bridge::Refusal(failure);", "            return;")


class Reply(unittest.TestCase):
    def test_a_craft_reports_the_new_items_the_gold_and_the_materials(self):
        both(self, r'''
    Rig rig;
    rig.game.rolled[500] = Rolled{"rare", false, 0, {{0, "str", "primary", 120.5, false, -1, 0}, {1, "sockets", "socket", 1, false, -1, 0}}, {}};
    rig.game.effect = [&] {
        rig.game.bags[500] = {30001, 1, 255, 23};
        rig.game.bags[501] = {102001, 4, 255, 24};                    // a plain stack
        rig.game.funds.gold = "900";
        rig.game.funds.materials[102000] = "3";
    };
    assert(rig.artisan("craft\t9\t2") == Outcome::Handled);
    assert(rig.sent.front() == "DCARTISAN\tR|craft|2");               // two items added
    assert(rig.has("DCARTISAN\tB|900"));
    assert(rig.has("DCARTISAN\tM|102000:3"));                         // only the changed material
    assert(rig.has("DCARTISAN\tA|500|30001|255|23|rare|0|0"));
    assert(rig.has("DCARTISAN\tF|500|0:str:120.5:primary:0:-1:0|1:sockets:1:socket:0:-1:0"));
    assert(rig.has("DCARTISAN\tI|501:102001:4:255:24"));
    assert(rig.sent.back() == "DCARTISAN\tE|craft");
    assert(!rig.starts("DCARTISAN\tD|"));
''', "wire.Record({\"R\", verb, Num(craft ? added : removed)});", "wire.Record({\"R\", verb, Num(craft ? removed : added)});")

    def test_a_salvage_reports_the_removed_items(self):
        both(self, r'''
    Rig rig;
    rig.game.bags[10] = {30001, 1, 255, 23}; rig.game.bags[11] = {30002, 1, 255, 24}; rig.game.bags[12] = {102001, 2, 255, 25};
    rig.game.effect = [&] { rig.game.bags.erase(10); rig.game.bags.erase(11); rig.game.bags[12].count = 5; };
    assert(rig.artisan("bulk\t1") == Outcome::Handled);
    assert(rig.sent.front() == "DCARTISAN\tR|bulk|2");
    assert(rig.has("DCARTISAN\tD|10|11"));
    assert(rig.has("DCARTISAN\tI|12:102001:5:255:25"));               // a changed count is a changed stack
''', "            if (!after.count(guid))\n                removed.push_back(Num(guid));", "            if (false)\n                removed.push_back(Num(guid));")

    def test_a_socket_sends_the_item_it_rewrote_even_though_nothing_moved(self):
        both(self, r'''
    Rig rig;
    rig.game.bags[41] = {30001, 1, 255, 5};
    rig.game.rolled[41] = Rolled{"legendary", false, 0, {{2, "sockets", "socket", 1, false, -1, 0}, {3, "ruby", "gem", 0, false, 2, 400}}, {}};
    assert(rig.jeweler("socket\t41\t2\t77") == Outcome::Handled);
    assert(rig.has("DCJEWELER\tA|41|30001|255|5|legendary|0|0"));
    assert(rig.has("DCJEWELER\tF|41|2:sockets:1:socket:0:-1:0|3:ruby:0:gem:0:2:400"));
''', "|| guid == touched)", ")")

    def test_a_touched_item_sends_its_open_offers_and_no_other_item_does(self):
        both(self, r'''
    Rig rig;
    rig.game.bags[41] = {30001, 1, 255, 5}; rig.game.bags[42] = {30002, 1, 255, 6};
    rig.game.rolled[41] = Rolled{"rare", true, 1, {{0, "str", "primary", 9, true, -1, 0}}, {{1, "vit", 8}, {2, "str", 11}}};
    rig.game.rolled[42] = rig.game.rolled[41];
    rig.game.effect = [&] { rig.game.bags[42].slot = 7; };            // another item moved: it is sent, without offers
    assert(rig.jeweler("socket\t41\t0\t77") == Outcome::Handled);
    assert(rig.has("DCJEWELER\tO|41|1:vit:8|2:str:11"));
    assert(!rig.starts("DCJEWELER\tO|42"));
    assert(rig.has("DCJEWELER\tA|42|30002|255|7|rare|1|1"));
''', "if (auto rolled = game.Detail(guid, guid == touched))", "if (auto rolled = game.Detail(guid, true))")

    def test_a_gold_change_is_sent_and_an_unchanged_ledger_is_not(self):
        both(self, r'''
    Rig rig;
    rig.game.effect = [&] { rig.game.funds.gold = "990"; };
    rig.jeweler("combine\t3");
    assert(rig.has("DCJEWELER\tB|990"));
    rig.game.effect = nullptr;
    rig.jeweler("combine\t3");
    assert(!rig.starts("DCJEWELER\tB|") && !rig.starts("DCJEWELER\tM|"));
''', "            if (fundsBefore.gold != fundsAfter.gold)", "            if (false)")

    def test_a_material_change_is_sent_only_when_it_changed(self):
        both(self, r'''
    Rig rig;
    rig.game.effect = [&] { rig.game.funds.materials[102001] = "8"; };
    rig.jeweler("combine\t3");
    assert(rig.has("DCJEWELER\tM|102001:8") && !rig.has("DCJEWELER\tM|102000:5|102001:8"));
''', "if (was == fundsBefore.materials.end() || was->second != amount)", "if (true)")

    def test_a_ledger_that_could_not_be_read_reports_no_funds(self):
        ok, out = compile_window(r'''
    Rig rig;
    rig.game.funds.valid = false;
    rig.game.effect = [&] { rig.game.funds.gold = "1"; };
    assert(rig.jeweler("combine\t3") == Outcome::Handled);
    assert(!rig.starts("DCJEWELER\tB|"));
''')
        self.assertTrue(ok, out)

    def test_a_craft_that_stopped_halfway_still_reports_what_it_made_then_refuses(self):
        both(self, r'''
    Rig rig;
    rig.game.rolled[500] = Rolled{"magic", false, 0, {}, {}};
    rig.game.effect = [&] {
        rig.game.bags[500] = {30001, 1, 255, 23};
        rig.game.funds.gold = "950";
        throw std::runtime_error("Crafting stopped before completing the requested count.");
    };
    assert(rig.artisan("craft\t9\t3") == Outcome::Refused);
    assert(rig.has("DCARTISAN\tB|950") && rig.has("DCARTISAN\tA|500|30001|255|23|magic|0|0"));
    assert(rig.sent.back() == "DCARTISAN\tX|Crafting stopped before completing the requested count.");
    assert(!rig.starts("DCARTISAN\tR|"));
''', "            Report(game, wire, before, fundsBefore, 0);\n            throw", "            throw")

    def test_a_long_list_is_split_into_records_that_fit_the_wire(self):
        both(self, r'''
    Rig rig;
    for (std::uint64_t g = 4000000000ull; g < 4000000000ull + 60; ++g) rig.game.bags[g] = {30001, 1, 255, 23};
    rig.game.effect = [&] { rig.game.bags.clear(); };
    assert(rig.artisan("bulk\t1") == Outcome::Handled);
    int guids = 0, records = 0;
    for (auto const& s : rig.sent) {
        assert(s.size() <= DC::Bridge::MaxMessage);                   // prefix, tab and record
        if (s.compare(0, 12, "DCARTISAN\tD|") == 0) { ++records; for (char c : s) guids += c == '|'; }
    }
    assert(records > 1 && guids == 60);                                // every guid arrived, one '|' before each
''', "constexpr std::size_t PackBudget = 200;", "constexpr std::size_t PackBudget = 2000;")

    def test_a_read_only_verb_reports_no_changes(self):
        ok, out = compile_window(r'''
    Rig rig;
    rig.game.state.guid = 41;
    assert(rig.artisan("place\t41") == Outcome::Handled);
    assert(!rig.starts("DCARTISAN\tB|") && !rig.starts("DCARTISAN\tM|") && !rig.starts("DCARTISAN\tA|") && !rig.starts("DCARTISAN\tI|"));
    assert(rig.artisan("preview\t41\t2") == Outcome::Handled);
    assert(rig.sent.size() == 2 && rig.sent[0] == "DCARTISAN\tR|preview|41" && rig.sent[1] == "DCARTISAN\tE|preview");
    assert(rig.artisan("transmog") == Outcome::Handled);
    assert(rig.sent.size() == 2 && rig.sent[0] == "DCARTISAN\tR|transmog|0");
''')
        self.assertTrue(ok, out)


def wiring_problems(cpp, sheet):
    """What must hold in dc_crafting.cpp and the tunables sheet for the windows to reach the same functions."""
    problems = []
    for prefix, category, burst, rate in (("DCARTISAN", "crafting", "artisan_burst", "artisan_per_second"),
                                          ("DCJEWELER", "crafting", "jeweler_burst", "jeweler_per_second")):
        if not re.search(r'Routes\(\)\.Add\(\s*"%s",\s*\{"%s", "%s", "%s"\}' % (prefix, category, burst, rate), cpp):
            problems.append("route " + prefix)
    for window, game in (("Window::Artisan(game, request, wire)", "DCARTISAN"), ("Window::Jeweler(game, request, wire)", "DCJEWELER")):
        if window not in cpp:
            problems.append("handler " + window)
    # Each Game method calls the checked function the command calls.
    for method, call in (("Salvage(uint32 guid)", "DC::Crafting::Salvage(player_, guid, 0)"),
                         ("Bulk(uint32 rarity)", "DC::Crafting::Salvage(player_, 0, rarity)"),
                         ("Craft(uint32 id, uint32 count)", "DC::Crafting::Craft(player_, id, count)"),
                         ("Place(uint32 guid)", "MysticState(player_, guid)"),
                         ("Preview(uint32 guid, uint32 seq)", "MysticPreview(player_, guid, seq)"),
                         ("Roll(uint32 guid, uint32 seq)", "DC::Crafting::Roll(player_, guid, seq)"),
                         ("Pick(uint32 guid, uint32 choice)", "DC::Crafting::Pick(player_, guid, choice)"),
                         ("Socket(uint32 guid, uint32 seq, uint32 gem)", "DC::Crafting::Socket(player_, guid, seq, gem)"),
                         ("Combine(uint32 id, uint32 count)", "DC::Crafting::Combine(player_, id, count)"),
                         ("Gate(Window::Npc npc)", "Artisan(player_, Entry(npc))"),
                         ("Gate(Window::Npc npc)", "Reachable(player_)"),
                         ("Repair(Window::Npc npc)", "DC::Crafting::Repair(player_, Artisan(player_, Entry(npc)))")):
        body = re.search(re.escape(method) + r"\s*\{(.*?)\n            \}", cpp, re.S)
        if not body or call not in body.group(1):
            problems.append("game method " + method)
    # DCARTISAN, DCJEWELER and (diablocraft-wpt7l.4) DCCUBE each run in one account operation.
    if cpp.count("PlayerEconomy::Scope operation(&player);\n                WindowGame game(&player);") != 3:
        problems.append("account operation scope")
    # diablocraft-jeweler-window: the three server rules of the new Jeweler window, in the one file the
    # compiled harness cannot run. (1) Socket() asks Window::SocketGate, the rule the handler is tested
    # on, and only an answer of Nobody skips the Jeweler. (2) The Jeweler no longer repairs: the command
    # verb is gone. (3) Combine() checks the whole count before it takes anything.
    socket = re.search(r"void Socket\(Player\* player, uint32 guid, uint32 seq, uint32 gemGuid\)\n        \{(.*?)\n        \}\n", cpp, re.S)
    if not socket or "if (Window::SocketGate(gemGuid != 0, child != instance.affixes.end()) == Window::Npc::Nobody)\n                Reachable(player);\n            else\n                Artisan(player, Jeweler);" not in socket.group(1):
        problems.append("Socket() gate")
    elif 'Need(child == instance.affixes.end(), "Remove the existing gem first.");' in socket.group(1):
        problems.append("Socket() still refuses a swap")
    # The repair-packet hook refuses the Jeweler by name before the flag lookup, and does not list it as an
    # artisan that repairs (the stock handler would otherwise be left to decide).
    hook = re.search(r"if \(packet\.GetOpcode\(\) != CMSG_REPAIR_ITEM.*?return false;\n            \}\n", cpp, re.S)
    if not hook or "target->GetEntry() == Jeweler" not in hook.group(0) or '"The Jeweler does not repair."' not in hook.group(0):
        problems.append("repair hook refuses the Jeweler")
    elif "npc->GetEntry() != Jeweler" in hook.group(0) or hook.group(0).index("== Jeweler") > hook.group(0).index("GetNPCIfCanInteractWith"):
        problems.append("repair hook lists the Jeweler or checks it too late")
    action = re.search(r"static bool JewelerAction\(.*?\n            \}\n", cpp, re.S)
    if not action or '"repair"' in action.group(0) or 'Combine(player, first, second.value_or(1));' not in action.group(0):
        problems.append("JewelerAction repair or combine count")
    combine = re.search(r"void Combine\(Player\* player, uint32 output, uint32 count\)\n        \{(.*?)\n        \}\n", cpp, re.S)
    if not combine or "void Combine(Player* player, uint32 output, uint32 count = 1);" not in cpp:
        problems.append("Combine() signature")
    else:
        text = combine.group(1)
        order = [text.find(mark) for mark in ("Need(count > 0,", "Need(price <= UINT64_MAX / count,", "CheckMaterials(player, materials);",
                                              "Need(Economy::CanAfford(player, price), \"Not enough account gold.\");", "CheckRoom(player, {{output, count}});",
                                              "Economy::Charge(player, price)", "SpendMaterials(player, materials);", "Grant(player, {{output, count}});")]
        if -1 in order or order != sorted(order):
            problems.append("Combine() checks the whole count before it takes anything")
        if "uint64(each) * count" not in text or "uint64(breath) * count" not in text:
            problems.append("Combine() materials are not multiplied by the count")
    if "Gold Bars" in cpp:
        problems.append("a refusal names Gold Bars, a retired denomination")
    # diablocraft-3oqx: the Lua half moved the windows onto the bridge, so the old verbs are
    # GM-only test sheets (the designer, q-0930-12) and a player-level `.dc artisan` can no longer act.
    if not re.search(r'\{"artisan", Handle, SEC_ADMINISTRATOR', cpp) or not re.search(r'\{"jeweler", JewelerAction, SEC_ADMINISTRATOR', cpp):
        problems.append("old verbs not GM-only")
    # The designer set the four rows (q-0930-49, diablocraft-window-tunables-set, cad7d66d); a missing or
    # blank value still closes that route for every player (contract, Budget), and none of them is
    # a D3 number to source.
    rows = {r["name"]: r for r in csv.DictReader(sheet.splitlines())}
    for name in ("artisan_burst", "artisan_per_second", "jeweler_burst", "jeweler_per_second"):
        if name not in rows or rows[name]["d3_value"] != "" or rows[name]["value"].strip() == "" \
                or not rows[name]["value"].strip().lstrip("-").replace(".", "", 1).isdigit() or not rows[name]["notes"]:
            problems.append("tunable row " + name)
    return problems


def lua_problems(artisan, jeweler):
    """What makes the SEC_ADMINISTRATOR move safe for a player: no window types the verb any more."""
    problems = []
    for name, text in (("dc_crafting.lua", artisan), ("dc_jeweler.lua", jeweler)):
        if ":RunCommand(" in text:
            problems.append(name + " still types a command")
    if 'SendAddonMessage("DCARTISAN"' not in artisan:
        problems.append("dc_crafting.lua does not send DCARTISAN")
    if 'SendAddonMessage("DCJEWELER"' not in jeweler:
        problems.append("dc_jeweler.lua does not send DCJEWELER")
    return problems


class WindowLua(unittest.TestCase):
    def test_no_window_types_the_gm_only_verb_any_more(self):
        # The two halves ship in one commit (brief task 2), so the moment the verbs are
        # SEC_ADMINISTRATOR a window that still typed one would refuse the player outright.
        self.assertEqual(lua_problems(ARTISAN_LUA, JEWELER_LUA), [])

    def test_the_check_notices_a_window_that_still_types_the_command(self):
        typed = ARTISAN_LUA + '\nplayer:RunCommand("dc artisan craft 1 1")\n'
        self.assertEqual(lua_problems(typed, JEWELER_LUA), ["dc_crafting.lua still types a command"])
        self.assertNotEqual(lua_problems(ARTISAN_LUA.replace("DCARTISAN", "DCARTISANS"), JEWELER_LUA), [])


class Wiring(unittest.TestCase):
    def test_production_is_wired_to_the_same_functions_with_live_routes(self):
        sheet = TUNABLES.read_text(encoding="utf-8")
        self.assertEqual(wiring_problems(CRAFTING, sheet), [])

    def test_the_check_notices_each_kind_of_break(self):
        sheet = TUNABLES.read_text(encoding="utf-8")
        for old, new in (('"DCJEWELER", {"crafting", "jeweler_burst"', '"DCJEWELER", {"crafting", "jeweler_bursts"'),
                         ("DC::Crafting::Craft(player_, id, count);", "player_->GetName();"),
                         ("DC::Crafting::Repair(player_, Artisan(player_, Entry(npc)));", "DC::Crafting::Repair(player_, nullptr);"),
                         ("Window::Artisan(game, request, wire);", ""),
                         ("PlayerEconomy::Scope operation(&player);\n                WindowGame game(&player);\n                Window::Jeweler",
                          "WindowGame game(&player);\n                Window::Jeweler"),
                         ('{"jeweler", JewelerAction, SEC_ADMINISTRATOR', '{"jeweler", JewelerAction, SEC_PLAYER'),
                         ("target->GetEntry() == Jeweler", "target->GetEntry() == Mystic"),
                         ("npc->GetEntry() != Blacksmith && npc->GetEntry() != Mystic)", "npc->GetEntry() != Blacksmith && npc->GetEntry() != Mystic && npc->GetEntry() != Jeweler)"),
                         ("if (Window::SocketGate(gemGuid != 0, child != instance.affixes.end()) == Window::Npc::Nobody)", "if (false)"),
                         ("Artisan(player, Jeweler);\n            Need(!CharacterDatabase.Query(\"SELECT 1 FROM dc_enchant_offer", "Reachable(player);\n            Need(!CharacterDatabase.Query(\"SELECT 1 FROM dc_enchant_offer"),
                         ('                    else\n                        throw std::runtime_error("Unknown Jeweler action.");',
                          '                    else if (action == "repair")\n                        Repair(player, Artisan(player, Jeweler));\n                    else\n                        throw std::runtime_error("Unknown Jeweler action.");'),
                         ("            Need(price <= UINT64_MAX / count, \"The combine total exceeds supported currency capacity.\");\n", ""),
                         ("            Need(Economy::CanAfford(player, price), \"Not enough account gold.\");\n            CheckRoom(player, {{output, count}});", "            CheckRoom(player, {{output, count}});"),
                         ("\"Not enough account gold.\");\n            CheckRoom(player, {{output, count}});", "\"Not enough gold and Gold Bars.\");\n            CheckRoom(player, {{output, count}});"),
                         ("Amounts materials = {{input, uint64(each) * count}};", "Amounts materials = {{input, uint64(each)}};"),
                         ("                if (npc == Window::Npc::Nobody)\n                    Reachable(player_);\n                else if",
                          "                if")):
            self.assertNotEqual(wiring_problems(mutate(CRAFTING, old, new), sheet), [], old)
        self.assertNotEqual(wiring_problems(CRAFTING, sheet.replace("jeweler_burst,,10,", "jeweler_burst,,,")), [])
        self.assertNotEqual(wiring_problems(CRAFTING, sheet.replace("artisan_per_second,,5,", "artisan_per_second,gone,5,")), [])


class HarnessRunsUnderTheCoreLimit(unittest.TestCase):
    """This file is a registered runner (test_harness_core_limit.RUNNERS): every harness it compiles is started by
    test_class_parity.run through harness_env.run, and harness_env.run refuses a test file that is not listed."""

    def test_a_child_started_by_the_helper_has_the_one_byte_core_limit(self):
        program = "import resource; print(*resource.getrlimit(resource.RLIMIT_CORE))"
        ran = harness_env.run([sys.executable, "-c", program], capture_output=True, text=True)
        self.assertEqual(ran.stdout.split(), ["1", "1"])


if __name__ == "__main__":
    unittest.main()
