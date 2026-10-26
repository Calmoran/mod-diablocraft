"""diablocraft-wpt7l.3: Kanai's Cube's made-by mark and the one-worn rule (plan docs/research/kanais-cube.md 6.4; decisions.md
2026-10-10: one item made this way may be worn, dropped Primals have no limit).

1. The equip check: dc_made_rule.h, and Leaving, Made and MadeEquipAllows cut out of src/items/dc_items_equip.cpp as they are,
   compiled against doubles of the core's Player and Item, with the limit read from the tunables sheet. A second made Primal
   is refused; one that replaces the made one in its slot, a ring swap, a two-hander over a made weapon, a dropped Primal and
   a made Ancient all pass; the refusal names the limit. Each case runs again on a mutation that breaks its rule.
2. The wiring, pinned as text: the veto keeps a saved set at login (only a new equip is checked), Unique Equipped shares
   Leaving, MarkMade sets the creator field and writes the name, `.dc made` is a GM command.
3. items_0008_made_by.sql on a disposable MySQL (test_account_economy_sql.isolated), applied twice on items_0001's table:
   the column is there, empty by default; without its guard the second apply fails.
"""
import csv
import re
import subprocess
import unittest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
from test_class_parity import SRC, definition, mutate
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)

ITEMS = items_source.source()
HEADER = (SRC / "items/dc_items.h").read_text(encoding="utf-8")
RULE = (SRC / "items/dc_made_rule.h").read_text(encoding="utf-8")
MODULE = SRC.parent
CHARACTERS = MODULE / "data/sql/db-characters/updates"


def limit():
    rows = csv.DictReader((MODULE / "data/tunables/crafting.csv").open(encoding="utf-8", newline=""))
    return next(r["value"] for r in rows if r["name"] == "made_primal_worn_limit")


DOUBLES = r'''
#include <cassert>
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>
using uint8 = std::uint8_t;
enum { INVENTORY_SLOT_BAG_0 = 255, EQUIPMENT_SLOT_START = 0, EQUIPMENT_SLOT_MAINHAND = 15, EQUIPMENT_SLOT_OFFHAND = 16,
       EQUIPMENT_SLOT_FINGER1 = 10, EQUIPMENT_SLOT_FINGER2 = 11, EQUIPMENT_SLOT_END = 19, INVENTORY_SLOT_ITEM_START = 23 };
enum { INVTYPE_FINGER = 11, INVTYPE_WEAPON = 13, INVTYPE_2HWEAPON = 17 };
enum { ITEM_FIELD_CREATOR = 10 };
struct Guid { std::uint64_t low = 0; std::uint64_t GetCounter() const { return low; } explicit operator bool() const { return low; } };
struct ItemTemplate { int InventoryType = INVTYPE_FINGER; };
struct Item {
    std::uint64_t guid = 0, creator = 0; ItemTemplate proto;
    Guid GetGUID() const { return {guid}; }
    Guid GetGuidValue(int) const { return {creator}; }
    ItemTemplate const* GetTemplate() const { return &proto; }
};
struct WorldSession {};
struct Player {
    std::map<int, Item*> worn; WorldSession session;
    Item* GetItemByPos(int bag, int slot) const { auto f = worn.find(slot); return bag == INVENTORY_SLOT_BAG_0 && f != worn.end() ? f->second : nullptr; }
    WorldSession* GetSession() { return &session; }
};
std::vector<std::string> said;
struct ChatHandler {
    explicit ChatHandler(WorldSession*) {}
    template<class... A> void PSendSysMessage(char const* text, A... args) { said.push_back(text); (void)sizeof...(args); }
};
namespace DC::Tunables { double limit = LIMIT; double Get(std::string const&, std::string const&) { return limit; } }
#include "RULE_HERE"
namespace DC::Items {
struct Instance { std::string qualityTier = "normal"; };
std::map<std::uint64_t, std::string> quality;   // the dc_item_instance rows: guid -> quality_tier
std::optional<Instance> Get(std::uint64_t guid) { auto f = quality.find(guid); if (f == quality.end()) return std::nullopt; return Instance{f->second}; }
'''

CASES = r'''
using namespace DC::Items;
Item made{1, 77}, made2{2, 78}, dropped{3, 0}, ancient{4, 79}, plain{5, 0};
Item twoHander{6, 80, {INVTYPE_2HWEAPON}}, weapon{7, 81, {INVTYPE_WEAPON}};
quality = {{1, "primal"}, {2, "primal"}, {3, "primal"}, {4, "ancient"}, {5, "normal"}, {6, "primal"}, {7, "primal"}};
Player p; p.worn[EQUIPMENT_SLOT_FINGER1] = &made;
'''


def compile_made(body, items=ITEMS, rule=RULE, value=None):
    pieces = [definition(items, "std::vector<std::uint64_t> Leaving(Player* player, uint8 slot, Item* item)"),
              definition(items, "bool Made(Item* item)"),
              definition(items, "bool MadeEquipAllows(Player* player, uint8 slot, Item* item)")]
    code = (DOUBLES.replace("LIMIT", value or limit()).replace('#include "RULE_HERE"', rule)
            + "\n".join(pieces) + "\n}\nint main() {\n" + CASES + body + "\n    return 0;\n}\n")
    return run(code)


def both(test, body, old, new, where="items", value=None):
    ok, out = compile_made(body, value=value)
    test.assertTrue(ok, out)
    sources = {"items": ITEMS, "rule": RULE}
    ok, out = compile_made(body, value=value, **{where: mutate(sources[where], old, new)})
    test.assertFalse(ok, "mutation survived: " + new)


class EquipCheck(unittest.TestCase):
    def test_the_limit_is_one(self):
        self.assertEqual(limit(), "1")   # decisions.md 2026-10-10

    def test_a_second_made_primal_is_refused_and_says_the_limit(self):
        both(self, r'''
    assert(!MadeEquipAllows(&p, EQUIPMENT_SLOT_FINGER2, &made2));
    assert(said.size() == 1 && std::string(said[0]).find("Kanai's Cube") != std::string::npos);''',
             "if (w.made && std::find(leaving.begin(), leaving.end(), w.guid) == leaving.end())",
             "if (false)", where="rule")

    def test_the_slot_it_takes_and_a_ring_swap_leave(self):
        both(self, r'''
    assert(MadeEquipAllows(&p, EQUIPMENT_SLOT_FINGER1, &made2));   // replaces the made ring in its slot
    assert(MadeEquipAllows(&p, EQUIPMENT_SLOT_FINGER2, &made));    // the made ring moves to the other finger
    assert(said.empty());''',
             "    if (slot < EQUIPMENT_SLOT_END)\n        leave(slot);\n", "")
        both(self, r'''
    assert(MadeEquipAllows(&p, EQUIPMENT_SLOT_FINGER2, &made));''',
             "std::vector<std::uint64_t> leaving = {item->GetGUID().GetCounter()};", "std::vector<std::uint64_t> leaving;")

    def test_a_two_hander_takes_both_hands_off(self):
        both(self, r'''
    p.worn.clear(); p.worn[EQUIPMENT_SLOT_OFFHAND] = &weapon;
    assert(MadeEquipAllows(&p, EQUIPMENT_SLOT_MAINHAND, &twoHander));''',
             "        leave(EQUIPMENT_SLOT_OFFHAND);\n", "")

    def test_only_a_primal_with_a_maker_counts(self):
        both(self, r'''
    assert(MadeEquipAllows(&p, EQUIPMENT_SLOT_FINGER2, &dropped));   // a dropped Primal: no maker, no limit
    assert(MadeEquipAllows(&p, EQUIPMENT_SLOT_FINGER2, &ancient));   // made, but an Ancient
    assert(MadeEquipAllows(&p, EQUIPMENT_SLOT_FINGER2, &plain));''',
             'return hasMaker && qualityTier == "primal";', "return hasMaker;", where="rule")
        both(self, r'''
    assert(MadeEquipAllows(&p, EQUIPMENT_SLOT_FINGER2, &dropped));''',
             "    if (!item || !item->GetGuidValue(ITEM_FIELD_CREATOR))\n        return false;\n", "")

    def test_the_limit_is_read_from_the_tunable(self):
        both(self, r'''
    assert(MadeEquipAllows(&p, EQUIPMENT_SLOT_FINGER2, &made2));''',
             'double const limit = DC::Tunables::Get("crafting", "made_primal_worn_limit");', "double const limit = 1;",
             value="2")


class Wiring(unittest.TestCase):
    def test_the_veto_checks_only_a_new_equip(self):
        self.assertIn("return !notLoading || (UniqueEquippedAllows(player, slot, item) && MadeEquipAllows(player, slot, item));",
                      ITEMS)
        self.assertIn("std::vector<std::uint64_t> const leaving = Leaving(player, slot, item);",
                      definition(ITEMS, "bool UniqueEquippedAllows(Player* player, uint8 slot, Item* item)"))

    def test_the_mark_sets_the_creator_field_and_the_name(self):
        mark = definition(ITEMS, "void MarkMade(Player* owner, Item* item, Player* maker, CharacterDatabaseTransaction const& transaction)")
        self.assertIn("item->SetGuidValue(ITEM_FIELD_CREATOR, maker->GetGUID());", mark)
        self.assertIn("item->SetState(ITEM_CHANGED, owner);", mark)
        self.assertIn("CharacterDatabase.EscapeString(name);", mark)
        self.assertIn("UPDATE dc_item_instance SET made_by='{}' WHERE item_guid={}", mark)
        self.assertIn("void MarkMade(Player* owner, Item* item, Player* maker, CharacterDatabaseTransaction const& transaction);", HEADER)

    def test_made_is_a_gm_command_that_saves_the_mark(self):
        self.assertIn('{"made", HandleMade, SEC_ADMINISTRATOR, Console::No},', ITEMS)
        handler = definition(ITEMS, "static bool HandleMade(ChatHandler* handler, uint32 guid)")
        self.assertLess(handler.index("MarkMade(player, item, player, transaction);"),
                        handler.index("player->SaveInventoryAndGoldToDB(transaction);"))
        self.assertIn("CharacterDatabase.CommitTransaction(transaction);", handler)
        self.assertNotIn("DirectCommitTransaction", handler)


class Migration(unittest.TestCase):
    def test_the_column_is_added_once_and_a_second_apply_changes_nothing(self):
        from test_account_economy_sql import MYSQL, isolated
        table = (CHARACTERS / "items_0001_item_instance.sql").read_text(encoding="utf-8")
        made = (CHARACTERS / "items_0008_made_by.sql").read_text(encoding="utf-8")
        unguarded = "ALTER TABLE dc_item_instance ADD COLUMN `made_by` VARCHAR(12) NOT NULL DEFAULT '' AFTER `quality_tier`;"

        def body(port):
            command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
                       "--batch", "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

            def mysql(text, database):
                done = subprocess.run(command + [f"--database={database}"], input=text, text=True, capture_output=True)
                return done.returncode, done.stdout.strip()

            for name, sql in (("made_real", made), ("made_unguarded", unguarded)):
                subprocess.run(command, input=f"CREATE DATABASE {name};", text=True, check=True)
                self.assertEqual(mysql(table, name)[0], 0)
                codes = [mysql(sql, name)[0] for _ in range(2)]
                if name == "made_real":
                    self.assertEqual(codes, [0, 0])
                    self.assertEqual(mysql("INSERT INTO dc_item_instance (item_guid, base_item) VALUES (1, 100087);", name)[0], 0)
                    self.assertEqual(mysql("SELECT CONCAT('[', made_by, ']') FROM dc_item_instance", name)[1], "[]")
                    self.assertEqual(mysql("SELECT COLUMN_COMMENT FROM information_schema.columns WHERE table_schema=DATABASE() "
                                           "AND table_name='dc_item_instance' AND column_name='made_by'", name)[1],
                                     "the maker's character name when the item was made (Kanai's Cube); empty otherwise")
                else:
                    self.assertEqual(codes[0], 0)
                    self.assertNotEqual(codes[1], 0, "an unguarded add fails on the second apply: the guard is what keeps it safe")

        isolated(body)


if __name__ == "__main__":
    unittest.main()
