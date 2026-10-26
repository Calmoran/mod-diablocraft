"""diablocraft-g0t7i: Kanai's Cube interface (1), the server side of D3's three windows (docs/contracts/cube-messages.md).

1. The rules (dc_cube_rule.h, compiled as it is): a reagent cell's token, the recipe a grid holds (the one whose spend lines
   are exactly its reagents), a power's line at the top of its ranges, a long line in pieces, and a page of a list.
2. The handler (dc_cube_window.h, behind the real router, the recipes parsed out of world_0053): the list with the page text
   and the slots, Fill, the grid Transmute, a page of a slot's powers, one power's line and a slot's choice; each behind the
   gate, each refusal, and the ungated read-only `buffs` for the buff bar. Every test runs again on a source mutation that breaks its rule, and that run must fail.
3. The generator: cube_0001_pages.sql is the render of cube_slots.csv and cube_pages.csv and its mirror. Cross-source: the
   slots cover every pool legendary item and count what the plan counted (docs/research/kanais-cube.md 5.3). The refusals fire.
4. The glue (dc_crafting.cpp), pinned as text: the power list reads the data, never a class or a slot; every check before a
   choice is stored; the table columns are the migration's; a deleted character takes its slots.
5. Replay: both migrations, each twice, on a disposable MySQL.
"""
import csv
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_cube as G
from test_cube_items import RECIPES
from test_class_parity import mutate
from test_cube import CRAFTING, CUBE, RULE, UPDATES, compile_cube, read_csv

PAGES = UPDATES / G.PAGES
CHARACTERS = G.MODULE / "data/sql/db-characters/updates/cube_0001_powers.sql"
SQL = RECIPES.read_text(encoding="utf-8")


def grid(test, body, old=None, new=None, where="cube"):
    """The body runs on the real headers with world_0053's recipes, and fails again on the named header with `old` made `new`."""
    ok, out = compile_cube(body, sql=SQL)
    test.assertTrue(ok, out)
    if old is not None:
        sources = {"cube": CUBE, "rule": RULE}
        ok, out = compile_cube(body, sql=SQL, **{where: mutate(sources[where], old, new)})
        test.assertFalse(ok, "mutation survived: " + new)


class Rules(unittest.TestCase):
    def test_a_cell_is_entry_underscore_amount_in_range(self):
        body = r'''
    using namespace DC::Crafting::Cube;
    auto c = ParseCell("102003_100"); assert(c && c->entry == 102003 && c->amount == 100);
    assert(ParseCell("4294967295_4294967295") && ParseCell("1_1"));
    for (char const* bad : {"", "_", "5", "5_", "_5", "0_5", "5_0", "a_5", "5_b", "5__5", "1_2_3", "4294967296_1", "1_4294967296",
                            "12345678901_1", "1_12345678901", "-1_5", "5_-1", "1 _5", "+1_5"})
        assert(!ParseCell(bad));'''
        grid(self, body, "part[0] == 0 || part[1] == 0 ||", "part[1] == 0 ||", where="rule")
        grid(self, body, "part[0] > UINT32_MAX || part[1] > UINT32_MAX", "part[1] > UINT32_MAX", where="rule")
        grid(self, body, "if (text[i] < '0' || text[i] > '9')\n                return std::nullopt;", "", where="rule")

    def test_the_grid_holds_the_recipe_whose_reagents_it_has_exactly(self):
        body = r'''
    using namespace DC::Crafting::Cube;
    auto wrath = Match(generated, {{102003, 100}, {102000, 1}});
    assert(wrath && wrath->id == "iben_wrath");
    assert(Match(generated, {{102000, 1}, {102003, 100}}) == wrath);               // the cells' order is nothing
    assert(Match(generated, {{102003, 60}, {102000, 1}, {102003, 40}}) == wrath);  // two cells of one material add up
    assert(!Match(generated, {{102003, 100}}));                                    // a reagent missing
    assert(!Match(generated, {{102003, 99}, {102000, 1}}));                        // one short
    assert(!Match(generated, {{102003, 100}, {102000, 2}}));                       // one over
    assert(!Match(generated, {{102003, 100}, {102000, 1}, {102001, 1}}));          // a material no recipe asked for
    assert(!Match(generated, {}));
    for (auto const& recipe : generated) {                                         // every ledger recipe is found, and by itself
        if (recipe.rule == "augment") continue;                                    // it spends no material: test_cube_augment
        std::vector<Cell> cells;
        for (auto const& line : recipe.lines) if (line.kind == "spend") cells.push_back({line.entry, line.amount});
        assert(Match(generated, cells) == &recipe);
    }'''
        grid(self, body, "&& spend == held && take == gems)", "&& spend.size() == held.size() && take == gems)", where="rule")
        grid(self, body, "held[cell.entry] += cell.amount;", "held[cell.entry] = cell.amount;", where="rule")
        grid(self, body, 'if (line.kind == "spend")\n                    spend[line.entry]', 'if (line.kind != "")\n                    spend[line.entry]',
             where="rule")

    def test_a_power_line_reads_each_range_at_its_top(self):
        body = r'''
    using DC::Crafting::Cube::TopOfRanges;
    assert(TopOfRanges("After a massacre bonus, 4\xe2\x80\x93" "6 Skeletons are summoned for 10 seconds.") == "After a massacre bonus, 6 Skeletons are summoned for 10 seconds.");
    assert(TopOfRanges("Deals 300\xe2\x80\x93" "400% more damage.") == "Deals 400% more damage.");
    assert(TopOfRanges("Every 0.5\xe2\x80\x93" "1.5 seconds, 25\xe2\x80\x93" "30% less.") == "Every 1.5 seconds, 30% less.");
    assert(TopOfRanges("Lasts 10 seconds. A 3-4 hit combo.") == "Lasts 10 seconds. A 3-4 hit combo.");   // no range, no change
    assert(TopOfRanges("A trailing 5\xe2\x80\x93") == "A trailing 5\xe2\x80\x93" && TopOfRanges("\xe2\x80\x93" "5") == "\xe2\x80\x93" "5");
    assert(TopOfRanges("") == "");'''
        grid(self, body, "out += text.substr(from, to - from);", "out += text.substr(i, first - i);", where="rule")
        grid(self, body, "if (text.compare(first, dash.size(), dash) == 0 && digit(text[first + dash.size()]))",
             "if (text.compare(first, dash.size(), dash) == 0)", where="rule")

    def test_a_long_line_goes_in_pieces_that_join_back(self):
        body = r'''
    using DC::Crafting::Cube::Chunks;
    std::string text = "Fist of the Heavens now casts twice and deals 1000% more damage while the wearer stands in a cold place";
    auto pieces = Chunks(text, 20);
    std::string joined;
    for (auto const& p : pieces) { assert(!p.empty() && p.size() <= 20); joined += p; }
    assert(joined == text && pieces.size() > 4 && pieces.front() == "Fist of the Heavens ");
    for (std::size_t i = 0; i + 1 < pieces.size(); ++i) assert(pieces[i].back() == ' ');   // a piece ends after a space where it can
    assert(Chunks("short", 20) == std::vector<std::string>{"short"} && Chunks("", 20) == std::vector<std::string>{""});
    std::string word(31, 'x'); assert(Chunks(word, 10).size() == 4);                         // no space: a hard cut
    std::string accents; for (int i = 0; i < 15; ++i) accents += "\xc3\xa9";                 // 30 bytes of two-byte letters
    for (auto const& p : Chunks(accents, 7)) { assert(!p.empty() && p.size() % 2 == 0); assert((static_cast<unsigned char>(p[0]) & 0xC0) != 0x80); }'''
        grid(self, body, "std::size_t end = at + size < text.size() ? at + size : text.size();",
             "std::size_t end = at + size + 1 < text.size() ? at + size + 1 : text.size();", where="rule")
        grid(self, body, "while (end > at + 1 && (static_cast<unsigned char>(text[end]) & 0xC0) == 0x80)", "while (false)", where="rule")
        grid(self, body, "if (space != std::string::npos && space >= at)", "if (false)", where="rule")

    def test_a_page_is_the_clamped_slice_of_the_list(self):
        body = r'''
    using DC::Crafting::Cube::Page;
    auto a = Page(40, 18, 1); assert(a.page == 1 && a.pages == 3 && a.first == 0 && a.count == 18);
    auto c = Page(40, 18, 3); assert(c.page == 3 && c.first == 36 && c.count == 4);
    auto past = Page(40, 18, 9); assert(past.page == 3 && past.count == 4);
    auto zero = Page(40, 18, 0); assert(zero.page == 1 && zero.count == 18);
    auto empty = Page(0, 18, 1); assert(empty.page == 1 && empty.pages == 1 && empty.count == 0);
    auto exact = Page(18, 18, 1); assert(exact.pages == 1 && exact.count == 18);
    auto one = Page(19, 18, 2); assert(one.pages == 2 && one.first == 18 && one.count == 1);'''
        grid(self, body, "(total + perPage - 1) / perPage", "total / perPage", where="rule")
        grid(self, body, "out.page = want < 1 ? 1 : want > out.pages ? out.pages : want;", "out.page = want < 1 ? 1 : want;", where="rule")
        grid(self, body, "(total - out.first < perPage ? total - out.first : perPage)", "perPage", where="rule")


class Handler(unittest.TestCase):
    def test_the_list_carries_each_recipes_page_and_the_slots(self):
        body = r'''
    auto own = [&](std::string const& id) -> decltype(generated[0]) { for (auto& r : generated) if (r.id == id) return r; assert(false); return generated[0]; };
    own("iben_pleasure").subtitle = "Convert Reusable Parts"; own("iben_pleasure").item = "Normal, Magic or Rare Item";
    own("iben_wrath").subtitle = "Convert Veiled Crystal"; own("iben_wrath").item = "Normal, Magic or Rare Item"; own("iben_wrath").note = "A note.";
    own("iben_wrath").quote = "A quote."; own("iben_wrath").quoteSource = "a source";
    Rig rig; rig.game.slots = {{1, "Weapon", 0, ""}, {2, "Armor", 100007, "Cain's Destiny"}, {3, "Jewelry", 0, ""}};
    rig.cube("list");
    assert(rig.sent.front() == "DCCUBE\tR|list|9" && rig.sent.back() == "DCCUBE\tE|list");
    int c0 = rig.at("C|iben_pleasure|convert|Pleasure of Iben Fahd");
    assert(rig.at("P|iben_pleasure|Convert Reusable Parts|Normal, Magic or Rare Item|") == c0 + 1);      // the page follows its recipe
    assert(rig.at("T|iben_pleasure|102001|100|150|1") == c0 + 2);
    assert(!rig.has("Q|iben_pleasure||"));                                                                // no quote, no Q
    int w = rig.at("C|iben_wrath|convert|Wrath of Iben Fahd");
    assert(rig.at("P|iben_wrath|Convert Veiled Crystal|Normal, Magic or Rare Item|A note.") == w + 1);
    assert(rig.at("Q|iben_wrath|A quote.|a source") == w + 2);
    assert(rig.game.gates == std::vector<std::string>{CUBE});
    std::size_t n = rig.sent.size();                                                                       // the slots close the list
    assert(rig.sent[n - 4] == "DCCUBE\tS|1|Weapon|0|" && rig.sent[n - 3] == "DCCUBE\tS|2|Armor|100007|Cain's Destiny"
           && rig.sent[n - 2] == "DCCUBE\tS|3|Jewelry|0|");
    assert(rig.at("C|iben_regret|convert|Regret of Iben Fahd") < rig.at("S|1|Weapon|0|"));'''
        grid(self, body, "        if (!recipe.quote.empty())", "        if (recipe.quote.empty())")
        grid(self, body, "        if (!recipe.subtitle.empty())", "        if (recipe.subtitle.empty())")
        grid(self, body, "        for (auto const& slot : slots)\n            SendSlot(wire, slot);\n", "")

    def test_fill_puts_a_recipes_reagents_in_the_grid_and_takes_nothing(self):
        body = r'''
    Rig rig; rig.game.funds.materials = {{102003, "100"}, {102000, "1"}};                // exactly enough is enough
    rig.cube("fill\tiben_wrath");
    assert(rig.sent.size() == 3 && rig.sent[0] == "DCCUBE\tR|fill|2" && rig.sent[2] == "DCCUBE\tE|fill");
    assert(rig.sent[1] == "DCCUBE\tG|iben_wrath|102003:100|102000:1");
    assert(rig.game.calls.empty() && rig.game.failed == 0 && rig.game.gates == std::vector<std::string>{CUBE});
    rig.game.funds.materials = {{102004, "50"}, {102008, "5"}, {102009, "5"}, {102010, "5"}, {102011, "5"}, {102012, "5"}, {102000, "9"}};
    rig.cube("fill\tlaw_of_kulle");
    assert(rig.sent[0] == "DCCUBE\tR|fill|6" && rig.sent.size() == 3);
    assert(rig.sent[1] == "DCCUBE\tG|law_of_kulle|102004:50|102008:5|102009:5|102010:5|102011:5|102012:5");
    rig.game.funds.materials[102012] = "4"; rig.cube("fill\tlaw_of_kulle");                  // one short fills nothing
    assert(rig.refusal() == "Not enough materials for that recipe.");
    rig.game.funds = Funds{}; rig.cube("fill\tiben_wrath");                                   // a ledger that cannot be read holds nothing
    assert(rig.refusal() == "Not enough materials for that recipe.");
    rig.cube("fill\tnot_a_recipe"); assert(rig.refusal() == "Choose a recipe.");'''
        grid(self, body, "< line.amount)\n                    throw Bridge::Refusal(\"Not enough materials for that recipe.\");",
             "<= line.amount)\n                    throw Bridge::Refusal(\"Not enough materials for that recipe.\");")
        grid(self, body, "        if (!recipe)\n            throw Bridge::Refusal(\"Choose a recipe.\");\n        Funds funds",
             "        if (!recipe)\n            return;\n        Funds funds")
        grid(self, body, 'cells.push_back(Num(line.entry) + ":" + Num(line.amount));', 'cells.push_back(Num(line.entry) + ":1");')

    def test_a_transmute_runs_the_recipe_the_grid_holds(self):
        body = r'''
    Rig rig;
    rig.cube("transmute\t42\t102000_1\t102003_60\t102003_40");                    // any order, a material in two cells
    assert(rig.game.calls == std::vector<std::string>{"iben_wrath 42"} && rig.sent.front() == "DCCUBE\tR|transmute|0");
    rig.game.calls.clear();
    rig.cube("transmute\t42\t102004_50\t102008_5\t102009_5\t102010_5\t102011_5\t102012_5");
    assert(rig.game.calls == std::vector<std::string>{"law_of_kulle 42"});
    rig.game.calls.clear(); rig.game.failed = 0;
    rig.cube("transmute\t42\t102003_100");                                       // a reagent missing: no recipe
    assert(rig.refusal() == "The Cube cannot use what is in the grid." && rig.game.calls.empty() && rig.game.failed == 1);
    rig.cube("transmute\t42\t102003_100\t102000_1\t102001_1");                   // one more than any recipe asks
    assert(rig.refusal() == "The Cube cannot use what is in the grid." && rig.game.calls.empty());
    rig.cube("transmute\t42\t102003_99\t102000_1");
    assert(rig.refusal() == "The Cube cannot use what is in the grid." && rig.game.calls.empty());
    rig.cube("transmute\t0\t102003_100\t102000_1");                              // reagents and no item
    assert(rig.refusal() == "Put an item in the Cube." && rig.game.calls.empty());'''
        grid(self, body, "                    game.Transmute(chosen, guid, gems);", "                    game.Transmute(recipes.front().id, guid, gems);")
        grid(self, body, "                    if (guid == 0)\n                        throw std::runtime_error(\"Put an item in the Cube.\");\n", "")
        grid(self, body, "                    if (!recipe)\n                        throw std::runtime_error(\"The Cube cannot use what is in the grid.\");\n",
             "                    if (!recipe)\n                        throw std::runtime_error(\"The Cube cannot use what is in the grid.\");\n"
             "                    if (recipe->lines.empty()) return;\n                    recipe = &recipes.front();\n")

    def test_a_page_of_powers_with_what_is_extracted(self):
        body = r'''
    Rig rig; rig.game.slots = {{1, "Weapon", 0, ""}, {2, "Armor", 0, ""}, {3, "Jewelry", 0, ""}};
    for (unsigned i = 0; i < 40; ++i) rig.game.powers.push_back({100000 + i, i == 5 ? "Ring: of A:B" : "P" + std::to_string(i), i % 3 == 0, i % 2 == 0});
    auto split = [](std::string s) { std::vector<std::string> out; std::size_t at = 0, bar;
        while ((bar = s.find('|', at)) != std::string::npos) { out.push_back(s.substr(at, bar - at)); at = bar + 1; }
        out.push_back(s.substr(at)); return out; };
    auto entries = [&] { std::vector<std::string> out; for (auto const& s : rig.sent) { assert(s.size() <= 255);
        auto f = split(s.substr(7)); if (f[0] == "W") { assert(f[1] == "3" || f[1] == "1"); out.insert(out.end(), f.begin() + 2, f.end()); } } return out; };
    rig.cube("powers\t1\t1");
    assert(rig.sent.front() == "DCCUBE\tR|powers|18" && rig.sent.back() == "DCCUBE\tE|powers" && rig.at("L|1|1|3|40") == 1);
    auto first = entries(); assert(first.size() == 18);
    assert(first[0] == "100000:1:P0" && first[1] == "100001:0:P1" && first[3] == "100003:2:P3");   // extracted and fits 1, not 0, extracted but not usable 2
    assert(first[5] == "100005:0:Ring  of A B" && first[17] == "100017:0:P17");                      // a ':' in a name never splits the packing
    assert(rig.sent.size() > 4);                                                                       // the 18 split over records
    rig.cube("powers\t1\t3"); assert(rig.at("L|1|3|3|40") == 1 && rig.sent.front() == "DCCUBE\tR|powers|4");
    auto last = entries(); assert(last.size() == 4 && last[0] == "100036:1:P36" && last[3] == "100039:2:P39");
    rig.cube("powers\t3\t99"); assert(rig.at("L|3|3|3|40") == 1);                                      // past the end is the last page, the third slot exists
    rig.game.powers.clear(); rig.cube("powers\t2\t1");
    assert(rig.sent.size() == 3 && rig.at("L|2|1|1|0") == 1 && rig.sent.front() == "DCCUBE\tR|powers|0");
    int read = rig.game.powersRead;
    rig.cube("powers\t4\t1"); assert(rig.refusal() == "There is no such slot." && rig.game.powersRead == read);'''
        grid(self, body, "Cube::Page(powers.size(), CubePowersPerPage, want)", "Cube::Page(powers.size(), CubePowersPerPage + 1, want)")
        grid(self, body, '(powers[i].fits ? "1" : "2")', '(powers[i].fits ? "2" : "1")')
        grid(self, body, "known = slot <= game.Slots().size();", "known = slot < game.Slots().size();")
        grid(self, body, "                if (c == ':')\n                    c = ' ';", "                if (c == ';')\n                    c = ' ';")

    def test_a_powers_line_goes_in_pieces_with_each_range_at_its_top(self):
        body = r'''
    std::string line = "Fist of the Heavens now casts twice and deals 900\xe2\x80\x93" "1000% more damage. It also does a great many other things, one after another, for a long time, so that the line passes the piece size.";
    Rig rig; rig.game.texts[100001] = {"Darklight", line};
    rig.cube("power\t100001");
    std::string joined; int pieces = 0;
    for (auto const& s : rig.sent) { assert(s.size() <= 255);
        if (s.rfind("DCCUBE\tU|100001|Darklight|", 0) == 0) { ++pieces; std::string rest = s.substr(26);
            assert(rest.rfind(std::to_string(pieces) + "|", 0) == 0); joined += rest.substr(std::to_string(pieces).size() + 1); } }
    assert(pieces == 2 && rig.sent.front() == "DCCUBE\tR|power|2" && rig.sent.back() == "DCCUBE\tE|power");
    assert(joined == "Fist of the Heavens now casts twice and deals 1000% more damage. It also does a great many other things, one after another, for a long time, so that the line passes the piece size.");
    rig.cube("power\t100002"); assert(rig.refusal() == "That is not a Cube power.");'''
        grid(self, body, "Cube::Chunks(Cube::TopOfRanges(found->text), CubeTextPiece)", "Cube::Chunks(found->text, CubeTextPiece)")
        grid(self, body, 'wire.Record({"U", Num(entry), power.name, Num(i + 1), pieces[i]});',
             'wire.Record({"U", Num(entry), power.name, Num(i + 1), pieces[0]});')
        grid(self, body, '        if (!found)\n            throw Bridge::Refusal("That is not a Cube power.");', "        if (!found)\n            return;")

    def test_choosing_a_power_fills_the_slot_and_zero_empties_it(self):
        body = r'''
    Rig rig; rig.game.slots = {{1, "Weapon", 0, ""}, {2, "Armor", 0, ""}, {3, "Jewelry", 0, ""}};
    rig.cube("choose\t2\t100005");
    assert(rig.game.chose == std::vector<std::string>{"2 100005"} && rig.game.gates == std::vector<std::string>{CUBE});
    assert(rig.sent.size() == 3 && rig.sent[0] == "DCCUBE\tR|choose|1" && rig.sent[1] == "DCCUBE\tS|2|Armor|100005|Power 100005" && rig.sent[2] == "DCCUBE\tE|choose");
    rig.cube("choose\t2\t0");
    assert(rig.sent.size() == 3 && rig.sent[0] == "DCCUBE\tR|choose|0" && rig.sent[1] == "DCCUBE\tS|2|Armor|0|");
    rig.game.chooseFails = "You have not extracted that power."; rig.game.slots[0].entry = 7;
    rig.cube("choose\t1\t100009"); assert(rig.refusal() == "You have not extracted that power." && rig.game.slots[0].entry == 7);'''
        grid(self, body, 'wire.Record({"R", "choose", entry ? "1" : "0"});', 'wire.Record({"R", "choose", "1"});')
        grid(self, body, "                if (s.slot == slot)\n                    SendSlot(wire, s);", "                SendSlot(wire, s);")

    def test_the_buff_bar_asks_buffs_with_no_gate_and_gets_each_held_power(self):
        body = r'''
    std::string line = "Fist of the Heavens now casts twice and deals 900\xe2\x80\x93" "1000% more damage. It also does a great many other things, one after another, for a long time, so that the line passes the piece size.";
    Rig rig; rig.game.slots = {{1, "Weapon", 100001, "Darklight"}, {2, "Armor", 0, ""}, {3, "Jewelry", 100003, "Ring of Royal Grandeur"}};
    rig.game.texts[100001] = {"Darklight", line}; rig.game.texts[100003] = {"Ring of Royal Grandeur", "Needs fewer pieces."};
    rig.game.gate = "You cannot do that while dead.";                                // dead, in combat or far from the Cube
    rig.cube("buffs");
    assert(rig.game.gates.empty() && rig.game.calls.empty() && rig.game.recipesRead == 0 && rig.game.powersRead == 0);
    assert(rig.sent.front() == "DCCUBE\tR|buffs|2" && rig.sent.back() == "DCCUBE\tE|buffs");           // an empty slot is not counted
    assert(rig.at("S|1|Weapon|100001|Darklight") == 1);
    assert(rig.sent.size() == 7 && rig.at("S|3|Jewelry|100003|Ring of Royal Grandeur") == 4);             // R, S1, U, U, S3, U, E: slot order
    assert(!rig.has("S|2|Armor|0|"));
    std::string joined; int pieces = 0;
    for (auto const& s : rig.sent) { assert(s.size() <= 255);
        if (s.rfind("DCCUBE\tU|100001|Darklight|", 0) == 0) { ++pieces; std::string rest = s.substr(26);
            assert(rest.rfind(std::to_string(pieces) + "|", 0) == 0); joined += rest.substr(std::to_string(pieces).size() + 1); } }
    assert(pieces == 2 && joined == "Fist of the Heavens now casts twice and deals 1000% more damage. It also does a great many other things, one after another, for a long time, so that the line passes the piece size.");
    assert(rig.has("U|100003|Ring of Royal Grandeur|1|Needs fewer pieces."));
    rig.game.slots = {{1, "Weapon", 0, ""}, {2, "Armor", 0, ""}, {3, "Jewelry", 0, ""}};                 // nothing held: R|buffs|0, no S
    rig.cube("buffs"); assert(rig.sent.size() == 2 && rig.sent[0] == "DCCUBE\tR|buffs|0" && rig.sent[1] == "DCCUBE\tE|buffs");
    rig.game.slots = {{1, "Weapon", 100009, "Gone"}};                                                      // an entry with no Cube text counts as empty
    rig.cube("buffs"); assert(rig.sent.size() == 2 && rig.sent[0] == "DCCUBE\tR|buffs|0");
    rig.cube("buffs\t1"); assert(rig.refusal() == "That request was not understood.");'''
        grid(self, body, "            SendPieces(wire, slot.entry, text, Cube::Chunks(Cube::TopOfRanges(text.text), CubeTextPiece));",
             "            SendPieces(wire, slot.entry, text, Cube::Chunks(text.text, CubeTextPiece));")
        grid(self, body, "                    if (auto text = game.PowerText(slot.entry)) // entry 0 (an empty slot) is no Cube power\n                        held.push_back({slot, *text});",
             "                    held.push_back({slot, CubePowerText{slot.name, \"\"}});")
        grid(self, body, "        wire.Record({\"R\", \"buffs\", Num(held.size())});", "        wire.Record({\"R\", \"buffs\", Num(3)});")
        grid(self, body, "            Exactly(request, 1, 1);\n            SendBuffs", "            SendBuffs")
        grid(self, body, "                for (auto const& slot : game.Slots())", "                game.Gate(Npc::Cube);\n                for (auto const& slot : game.Slots())")

    def test_every_new_verb_checks_the_gate_first(self):
        for verb, old in (("fill\tiben_wrath", "game.Gate(Npc::Cube);\n                recipes = game.Recipes();\n            });\n        auto const* recipe"),
                          ("powers\t1\t1", "game.Gate(Npc::Cube);\n                known = slot"),
                          ("power\t100001", "game.Gate(Npc::Cube);\n                found = game.PowerText(entry);"),
                          ("choose\t1\t100001", "game.Gate(Npc::Cube);\n                    game.Choose(slot, entry);")):
            body = (r'''
    Rig rig; rig.game.slots = {{1, "Weapon", 0, ""}}; rig.game.texts[100001] = {"Darklight", "text"};
    rig.game.gate = "Stand next to Kanai's Cube."; rig.cube("''' + verb + r'''");
    assert(rig.refusal() == "Stand next to Kanai's Cube." && rig.game.powersRead == 0 && rig.game.chose.empty() && rig.game.calls.empty());''')
            grid(self, body, old, old.replace("game.Gate(Npc::Cube);", "(void)0;", 1))


class Generator(unittest.TestCase):
    def test_the_migration_is_the_render_and_its_mirror(self):
        sql = G.render_pages()
        self.assertEqual(PAGES.read_text(encoding="utf-8"), sql)
        self.assertEqual((G.MODULE / "data/generated" / G.PAGES).read_text(encoding="utf-8"), sql)

    def test_the_slots_take_every_pool_legendary_and_count_what_the_plan_counted(self):
        slots = G.slots()
        self.assertEqual({n: label for n, (label, _) in slots.items()}, {1: "Weapon", 2: "Armor", 3: "Jewelry"})
        owner = {item: n for n, (_, items) in slots.items() for item in items}
        pool = [r for r in read_csv(G.DATA / "base_items.csv") if r["rarity"] == "legendary" and r["pool_version"] == "yes"]
        counts, torment = {1: 0, 2: 0, 3: 0}, []
        for row in pool:
            self.assertIn(row["slot"], owner, row["d3_name"])        # no legendary is left without a slot
            if row["source_file"] == "torment_shaman":
                torment.append((row["d3_name"], owner[row["slot"]]))   # Torment's own, beyond D3's 500
                continue
            counts[owner[row["slot"]]] += 1
        self.assertEqual(counts, {1: 259, 2: 178, 3: 63})            # kanais-cube.md 5.3: 114+88+57, the eight armor slots, finger and neck
        self.assertEqual(sum(counts.values()), 500)
        self.assertEqual(torment, [("Earthcaller's Gavel", 1)])      # the Shaman's start legendary, a Ritual Mace (xnrvn.3)

    def test_every_recipe_has_a_page_that_fits_the_wire(self):
        pages = G.pages()
        self.assertEqual(set(pages), {r[0] for r in G.recipes()})
        for rid, (subtitle, item, note, quote, source) in pages.items():
            self.assertLessEqual(len("|".join(("P", rid, subtitle, item, note)).encode()), G.MAX_PAGE_RECORD, rid)
            self.assertLessEqual(len("|".join(("Q", rid, quote, source)).encode()), G.MAX_PAGE_RECORD, rid)
        # rzusn: a convert page names the material it spends (cube_rules.csv spend row -> account_economy.csv name) and that it
        # makes the item's material; D3 draws no output, so the words are the only place the player learns it.
        names = {r["item_entry"]: r["name"] for r in read_csv(G.DATA / "account_economy.csv")}
        for rid in ("iben_pleasure", "iben_regret", "iben_wrath"):
            spend = [r["item_entry"] for r in read_csv(G.DATA / "cube_rules.csv") if r["recipe_id"] == rid and r["kind"] == "spend" and r["item_entry"] != "102000"]
            self.assertEqual(len(spend), 1, rid)
            self.assertEqual(pages[rid][0], f"Convert {names[spend[0]]} to Item's Material", rid)
        # The designer's captures: the three quoted pages say what they said, and Nilfur's red line is the rule's own.
        self.assertEqual(pages["skill_of_nilfur"][:3], ("Convert Set Item", "Set Item", "Resulting item cannot be Ancient."))
        self.assertTrue(pages["law_of_kulle"][3].startswith("For weeks the fires burned") and pages["law_of_kulle"][1] == "Legendary or Set Item")
        self.assertEqual(pages["hope_of_cain"][0], "Upgrade Rare Item")
        # Cross-source: Nilfur's line is true: the recipe rolls the new piece at normal quality (never Ancient or Primal).
        self.assertIn('quality = "normal"; // D3: the new piece never rolls Ancient or Primal', CRAFTING)

    def broken(self, sheet, edit, render):
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(folder.startswith(tempfile.gettempdir()))
            for name in ("cube_rules.csv", "cube_object.csv", "cube_pages.csv", "cube_slots.csv", "account_economy.csv", "world_objects.csv", "gems.csv",
                         "base_items.csv"):
                shutil.copy(G.DATA / name, folder)
            path = Path(folder) / sheet
            rows = read_csv(path)
            edit(rows)
            with path.open("w", newline="", encoding="utf-8") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            with self.assertRaises(G.CubeError) as caught:
                render(folder)
            return str(caught.exception)

    def test_refusals(self):
        slots, pages, rules = "cube_slots.csv", "cube_pages.csv", "cube_rules.csv"
        self.assertIn("no gap", self.broken(slots, lambda r: [x.update(slot="4") for x in r if x["slot"] == "3"], G.render_pages))
        self.assertIn("label", self.broken(slots, lambda r: [x.update(label="Armor:") for x in r if x["slot"] == "2"], G.render_pages))
        self.assertIn("label", self.broken(slots, lambda r: [x.update(label="A" * 17) for x in r if x["slot"] == "2"], G.render_pages))
        self.assertIn("repeats its label", self.broken(slots, lambda r: r[1].update(label="Arms"), G.render_pages))
        self.assertIn("not an item slot", self.broken(slots, lambda r: r[0].update(item_slot="elbow"), G.render_pages))
        self.assertIn("two Cube slots", self.broken(slots, lambda r: r[1].update(item_slot="onehand"), G.render_pages))
        self.assertIn("not a recipe", self.broken(pages, lambda r: r[0].update(recipe_id="iben_none"), G.render_pages))
        self.assertIn("two rows", self.broken(pages, lambda r: r.append(dict(r[0])), G.render_pages))
        self.assertIn("no page for", self.broken(pages, lambda r: r.pop(), G.render_pages))
        self.assertIn("'|' or tab", self.broken(pages, lambda r: r[0].update(subtitle="a|b"), G.render_pages))
        self.assertIn("a subtitle and an item line", self.broken(pages, lambda r: r[0].update(item=""), G.render_pages))
        self.assertIn("go together", self.broken(pages, lambda r: r[3].update(quote_source=""), G.render_pages))
        self.assertIn("over 240 bytes", self.broken(pages, lambda r: r[3].update(quote="x" * 300), G.render_pages))
        self.assertIn("at most 8 reagents", self.broken(rules, lambda r: r.extend(
            dict(r[0], recipe_id="big_one", sort="99", rule="reforge", name="Big", line=str(n), kind="spend", rarity="",
                 item_entry=str(entry), amount="1") for n, entry in enumerate((102000, 102001, 102002, 102003, 102004, 102008, 102009, 102010, 102011), 1)),
            G.recipes))
        self.assertIn("could not tell them apart", self.broken(rules, lambda r: r.extend(
            [dict(x, recipe_id="twin", sort="98", name="Twin") for x in r if x["recipe_id"] == "iben_wrath"]),
            G.recipes))


class Wiring(unittest.TestCase):
    BODY = CRAFTING[CRAFTING.index("        constexpr char const* CubePowerItems ="):CRAFTING.index("        // Skill of Nilfur (set_convert) and Hope of Cain")]

    def test_the_power_list_reads_the_data_and_names_no_class_or_slot(self):
        self.assertIn("JOIN dc_cube_slot_item s ON s.item_slot=b.slot", self.BODY)
        self.assertIn("b.rarity='legendary' AND ", self.BODY)
        self.assertIn("b.pool_version='yes' AND EXISTS(SELECT 1 FROM dc_legendary_power p WHERE p.owner=b.d3_id AND p.pieces=0)", self.BODY)
        self.assertIn("RollClass::Eligible(", self.BODY)
        for word in ("onehand", "twohand", "offhand", "'finger'", "'neck'", "'head'", "barbarian", "wizard", "crusader", "monk"):
            self.assertNotIn(word, self.BODY)
        self.assertIn("dc_cube_slot_item", (PAGES).read_text(encoding="utf-8"))

    def test_a_choice_checks_everything_before_it_is_stored(self):
        body = self.BODY[self.BODY.index("        void ChooseCubePower("):]
        order = ['"There is no such slot."', "That power does not go in this slot.", "Your class cannot use that power.",
                 "Kanai's Cube needs the account ledger.", "You have not extracted that power.", "REPLACE INTO dc_cube_slot"]
        at = [body.index(step) for step in order]
        self.assertEqual(at, sorted(at))
        self.assertEqual(body.count("REPLACE INTO"), 1)

    def test_the_queries_use_the_migrations_columns(self):
        sql = CHARACTERS.read_text(encoding="utf-8")
        columns = {name: set(re.findall(r"^\s+`(\w+)`", block, re.M)) for name, block in
                   re.findall(r"CREATE TABLE IF NOT EXISTS `(\w+)` \((.*?)\) ENGINE", sql, re.S)}
        self.assertEqual(columns, {"dc_cube_power": {"account_id", "mode", "power_id"}, "dc_cube_slot": {"guid", "slot", "power_id"}})
        for query in re.findall(r'"((?:SELECT|DELETE|REPLACE|INSERT)[^"]*\bdc_cube_(?:power|slot)\b[^"]*)"', CRAFTING):
            table = "dc_cube_power" if "dc_cube_power" in query else "dc_cube_slot"
            used = set(re.findall(r"\b(account_id|mode|power_id|guid|slot)\b", query))
            self.assertLessEqual(used, columns[table], query)

    def test_a_deleted_character_takes_its_slots_but_not_the_accounts_powers(self):
        self.assertIn('PlayerScript("dc_cube_characters", {PLAYERHOOK_ON_DELETE_FROM_DB, PLAYERHOOK_ON_LOGIN})', CRAFTING)
        self.assertIn('trans->Append("DELETE FROM dc_cube_slot WHERE guid={}", guid);', CRAFTING)
        self.assertNotIn("DELETE FROM dc_cube_power", CRAFTING)
        self.assertIn("new CubeCharacters();", CRAFTING)

    def test_the_buff_bar_reads_slots_and_text_without_the_cubes_gate(self):
        for name in ("std::vector<Window::CubeSlot> CubeSlots(", "std::optional<Window::CubePowerText> CubePowerText("):
            start = self.BODY.index(name)
            body = self.BODY[start:self.BODY.index("\n        }\n", start)]
            for gate in ("CubeInReach", "Reachable", "Gate("):
                self.assertNotIn(gate, body)

    def test_the_game_hands_the_window_the_four_new_calls(self):
        for call in ("return CubeSlots(player_);", "return CubePowers(player_, slot);", "return CubePowerText(entry);",
                     "ChooseCubePower(player_, slot, entry);"):
            self.assertIn(call, CRAFTING)
        self.assertIn("SELECT recipe_id,subtitle,item,note,quote,quote_source FROM dc_cube_page", CRAFTING)


class Replay(unittest.TestCase):
    """Both migrations applied for real, twice each, on a disposable MySQL (test_account_economy_sql.isolated), then probed: the
    keys refuse a duplicate and the mode column refuses a word that is no mode. Each mutant must change an outcome."""

    def test_the_migrations_apply_twice_and_hold_what_the_sheets_say(self):
        from test_account_economy_sql import MYSQL, isolated
        world = PAGES.read_text(encoding="utf-8")
        characters = CHARACTERS.read_text(encoding="utf-8")
        world_probes = ["INSERT INTO dc_cube_slot_item VALUES (1,'Weapon','onehand')",
                        "INSERT INTO dc_cube_page VALUES ('law_of_kulle','a','b','','','')",
                        "INSERT INTO dc_cube_page VALUES ('another','a','b','','','')"]
        character_probes = ["INSERT INTO dc_cube_power VALUES (1,'normal','a')", "INSERT INTO dc_cube_power VALUES (1,'normal','a')",
                            "INSERT INTO dc_cube_power VALUES (1,'normal','b')", "INSERT INTO dc_cube_power VALUES (1,'hardcore','a')",
                            "INSERT INTO dc_cube_power VALUES (1,'bogus','a')", "INSERT INTO dc_cube_slot VALUES (5,1,'a')",
                            "INSERT INTO dc_cube_slot VALUES (5,1,'b')", "INSERT INTO dc_cube_slot VALUES (5,2,'b')"]

        def body(port):
            command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
                       "--batch", "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

            def mysql(text, database=None):
                done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                                      capture_output=True, encoding="utf-8")
                return done.returncode, done.stdout.rstrip("\n")

            def outcome(sql, tag, counts, probes):
                name = f"cube_grid_{tag}"
                mysql(f"CREATE DATABASE {name} CHARACTER SET utf8mb4;")
                codes = [mysql(sql, name)[0] for _ in range(2)]
                if codes != [0, 0]:
                    return codes
                return codes, [mysql(f"SELECT COUNT(*) FROM {t}", name)[1] for t in counts], [int(bool(mysql(p, name)[0])) for p in probes]

            pages = str(len(G.pages()))
            real_world = outcome(world, "world", ("dc_cube_slot_item", "dc_cube_page"), world_probes)
            self.assertEqual(real_world, ([0, 0], ["13", pages], [1, 1, 0]))
            real_characters = outcome(characters, "chars", ("dc_cube_power", "dc_cube_slot"), character_probes)
            self.assertEqual(real_characters, ([0, 0], ["0", "0"], [0, 1, 0, 0, 1, 0, 1, 0]))
            mutants = ((world, "DROP TABLE IF EXISTS `dc_cube_page`;\n", "", ("dc_cube_slot_item", "dc_cube_page"), world_probes, real_world),
                       (world, "(2,'Armor','head'),\n", "", ("dc_cube_slot_item", "dc_cube_page"), world_probes, real_world),
                       (world, "PRIMARY KEY (`item_slot`)", "KEY (`item_slot`)", ("dc_cube_slot_item", "dc_cube_page"), world_probes, real_world),
                       (characters, "CREATE TABLE IF NOT EXISTS `dc_cube_power`", "CREATE TABLE `dc_cube_power`", ("dc_cube_power", "dc_cube_slot"),
                        character_probes, real_characters),
                       (characters, "PRIMARY KEY (`account_id`, `mode`, `power_id`)", "PRIMARY KEY (`account_id`, `mode`)",
                        ("dc_cube_power", "dc_cube_slot"), character_probes, real_characters),
                       (characters, "`mode`       ENUM('normal','hardcore')", "`mode`       VARCHAR(16)", ("dc_cube_power", "dc_cube_slot"),
                        character_probes, real_characters))
            for number, (sql, old, new, counts, probes, real) in enumerate(mutants):
                self.assertEqual(sql.count(old), 1, old)
                self.assertNotEqual(outcome(sql.replace(old, new), f"m{number}", counts, probes), real, "mutant survived: " + new)

        isolated(body)


    def test_the_power_queries_run_on_the_real_tables_and_list_what_is_built(self):
        """dc_crafting.cpp's own SQL (cut out of the source) run against dc_base_item, dc_legendary_power and dc_item_tooltip as the
        migrations make them, and dc_cube_slot_item as this bead makes it: each slot lists exactly the pool legendaries of its item
        slots that have a built power row (the sheets' own join, computed here in Python), and a choice's lookup finds a power
        in its slot only."""
        from test_account_economy_sql import MYSQL, isolated
        updates = UPDATES
        tooltip = (updates / "crafting_0001_artisans.sql").read_text(encoding="utf-8")
        start = tooltip.index("DROP TABLE IF EXISTS `dc_item_tooltip`")
        last = tooltip.rindex("INSERT INTO `dc_item_tooltip`")
        tooltip = tooltip[start:tooltip.index(";\n", last) + 2]
        # the newest full legendary_powers table holds every built row (each legendary bead renumbers it); no number is pinned here
        newest_powers = sorted(updates.glob("legendary_powers_*_table.sql"))[-1]
        files = [(updates / "0002_dc_base_item.sql").read_text(encoding="utf-8"), tooltip,
                 newest_powers.read_text(encoding="utf-8"), PAGES.read_text(encoding="utf-8"),
                 (updates / G.EXCLUDED).read_text(encoding="utf-8")]
        items = "constexpr char const* CubePowerItems ="
        piece = re.findall(r'"((?:[^"\\]|\\.)*)"', CRAFTING[CRAFTING.index(items):CRAFTING.index(";", CRAFTING.index(items))])
        from_clause = "".join(piece)
        queries = re.findall(r'std::string\("(SELECT b[^"]*)"\)\s*\+\s*CubePowerItems\s*\+\s*"([^"]*)"', CRAFTING)
        self.assertEqual(len(queries), 3)
        (listing, order), (text_of, text_tail), (choose, choose_tail) = [(head + from_clause, tail) for head, tail in queries]

        slots = G.slots()
        owner = {item: n for n, (_, kinds) in slots.items() for item in kinds}
        built = {r["owner"] for r in read_csv(G.MODULE / "data/legendary_powers.csv") if not r["pieces"]}
        base = read_csv(G.DATA / "base_items.csv")
        refused = {r["d3_id"] for r in read_csv(G.DATA / "cube_excluded.csv")}
        self.assertIn("Unique_Amulet_102_x1", built & refused)  # Ancestors' Grace is built and D3's cube: false keeps it out
        expect = {n: sorted(r["d3_name"] for r in base if r["d3_id"] in built - refused and r["rarity"] == "legendary"
                            and r["pool_version"] == "yes" and owner[r["slot"]] == n) for n in slots}
        self.assertTrue(all(expect.values()), expect)       # every slot lists something; the lists themselves are checked against the database below, not pinned to a count the next legendary moves

        def body(port):
            command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
                       "--batch", "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

            def mysql(text, database=None):
                done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                                      capture_output=True, encoding="utf-8")
                return done.returncode, done.stdout.rstrip("\n")

            def ask(tag, head, tail, *values, prefix=None):
                name = f"cube_grid_q{tag}"
                if tag not in made:
                    mysql(f"CREATE DATABASE {name} CHARACTER SET utf8mb4;")
                    for sql in files:
                        self.assertEqual(mysql(sql, name)[0], 0)
                    made.add(tag)
                sql = (head + tail).replace("{}", "%s")
                for value in values:
                    sql = sql.replace("%s", str(value), 1)
                return mysql(sql, name)

            made = set()
            for n in slots:
                code, out = ask("real", listing, order, n)
                self.assertEqual(code, 0)
                self.assertEqual(sorted(row.split("\t")[2] for row in out.splitlines()), expect[n], n)
            def entry_of(name):
                return int(mysql("SELECT entry FROM dc_base_item WHERE d3_name='" + name.replace("'", "''") + "' AND pool_version='yes'", "cube_grid_qreal")[1])
            sun = entry_of("Sun Keeper")
            code, out = ask("real", text_of, text_tail, sun)
            self.assertEqual((code, out.split("\t")[0]), (0, "Sun Keeper"))
            self.assertEqual(ask("real", choose, choose_tail, 1, sun)[1].split("\t")[0], "Unique_Mace_1H_011_x1")   # its own slot
            self.assertEqual(ask("real", choose, choose_tail, 2, sun)[1], "")                                     # not the armor slot
            self.assertEqual(ask("real", choose, choose_tail, 1, entry_of("Leoric's Signet"))[1], "")                # a legendary with no power row
            grace = entry_of("Ancestors' Grace")                                                                  # built, and D3's cube: false
            self.assertEqual(ask("real", choose, choose_tail, 3, grace)[1], "")                                   # not choosable in its own slot
            self.assertEqual(ask("real", text_of, text_tail, grace)[1], "")                                       # no power text, so the Archive's list check fails too
            for number, (old, new) in enumerate((("s.item_slot=b.slot", "1=1"), ("p.owner=b.d3_id", "1=1"),
                                                 ("NOT EXISTS(SELECT 1 FROM dc_cube_excluded x WHERE x.d3_id=b.d3_id)", "1=1"))):
                self.assertEqual(from_clause.count(old), 1, old)
                bad = from_clause.replace(old, new)
                slot = 3 if "excluded" in old else 1
                code, out = mysql((queries[0][0] + bad + order).replace("{}", str(slot)), "cube_grid_qreal")
                self.assertNotEqual(sorted(row.split("\t")[2] for row in out.splitlines()) if code == 0 else None, expect[slot],
                                    "mutant survived: " + new)

        isolated(body)


if __name__ == "__main__":
    unittest.main()
