"""diablocraft-dm9vg.4: bounties W4, the Horadric Cache (brief bounties-first-set-2026-10-11 W4, docs/research/bounties.md
5.5, PM answers on the bead 2026-10-12).

1. The sheets and the generator: one cache a column with its act reagent, the act pools (only legendaries Torment has; an
   empty pool still renders and rolls nothing), the refusals, and the item rows client-patch/dbc/build_item.py reads.
2. The tunables: the Torment XVI rows are maxroll's, the tier scale and gem grade rows are 20 each, the lower tiers marked
   PLACEHOLDER, and Marquise is rank 6 in dc_gem_item.
3. The rules (src/bounties/dc_bounty_cache_rule.h, compiled as it is), fed the values parsed out of the generated
   tunables_0012.sql.
4. The delivery (Deliver cut out of dc_bounty_cache.cpp) against doubles: the bags with the tier row in the same
   transaction, else the stash with the same row, else lost with the line.
5. The stash insert (DeliverNew cut out of dc_stash.cpp) against doubles of the container and the transaction.
6. The debts (OweCache, TakeOwed, PayOwed cut out of dc_bounty_cache.cpp), and the column's completion owing every online
   member (Credit cut out of dc_bounties.cpp over test_bounties.py's in-memory board).

Every compiled test runs again on a source mutation that removes the rule it checks, and that run must fail. Not covered:
the open itself (Open: the core's item, roll and ledger calls; the rules it asks are part 3), the real database, and the
client; the test sheet's checks on dev cover those.
"""
import csv
import importlib.util
import re
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_bounties as G
from test_bounties import BOARD, DOUBLES, HELPERS, MIGRATION, PRELUDE, first_set_sql, SERVER, catalogue_cpp, owners_source
from test_class_parity import SRC, definition, mutate
from harness_env import run_cpp as run  # the cached compile and run (the contract test_class_parity.run had)

ROOT = G.MODULE.parent
D3 = G.MODULE / "data/d3"
CACHE_MIGRATION = G.MODULE / "data/sql/db-world/updates" / G.CACHES
TIER_MIGRATION = G.MODULE / "data/sql/db-characters/updates/bounties_0006_cache_tier.sql"
TUNABLES_SQL = G.MODULE / "data/sql/db-world/updates/tunables_0012.sql"
RIFTS_CSV = G.MODULE / "data/tunables/rifts.csv"
RULE = (SRC / "bounties/dc_bounty_cache_rule.h").read_text(encoding="utf-8")
CACHE = (SRC / "bounties/dc_bounty_cache.cpp").read_text(encoding="utf-8")
STASH = (SRC / "items/dc_stash.cpp").read_text(encoding="utf-8")
SHEETS = ("bounty_caches.csv", "bounty_cache_legendaries.csv", "account_economy.csv", "base_items.csv",
          "base_item_ids.csv", "set_caches.csv")
POOLS = {1: [100089], 2: [100570], 3: [100950], 4: [100089, 100570, 100950, 100951], 5: [100951]}  # decisions 4006a91d


def build_item():
    spec = importlib.util.spec_from_file_location("build_item", ROOT / "client-patch/dbc/build_item.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- 1. the sheets and the generator ------------------------------------------------------------------------------------

class Generator(unittest.TestCase):
    def test_committed_migration_is_the_render(self):
        self.assertEqual(CACHE_MIGRATION.read_text(encoding="utf-8"), G.render_caches())
        self.assertEqual((G.MODULE / "data/generated" / G.CACHES).read_text(encoding="utf-8"), G.render_caches())

    def test_one_cache_a_column_with_its_act_reagent_and_pool(self):
        found = G.caches()
        self.assertEqual([c[0] for c in found], [1, 2, 3, 4, 5])
        self.assertEqual([c[1] for c in found], [101141, 101142, 101143, 101144, 101145])
        self.assertEqual([c[3] for c in found], [102008, 102009, 102010, 102011, 102012])  # W3's act reagents, act order
        self.assertEqual([c[4] for c in found], ["Khanduran Rune", "Caldeum Nightshade", "Arreat War Tapestry",
                                                 "Corrupted Angel Flesh", "Westmarch Holy Water"])
        self.assertEqual({c[0]: [i for i, _ in c[5]] for c in found}, POOLS)

    def test_every_pool_item_is_a_legendary_torment_has(self):
        # Cross-source: the pool rows against base_item_ids.csv and base_items.csv, read here without the generator.
        ids = {int(r["item_entry"]): r["d3_id"] for r in csv.DictReader((D3 / "base_item_ids.csv").open(encoding="utf-8"))}
        bases = {r["d3_id"]: r for r in csv.DictReader((D3 / "base_items.csv").open(encoding="utf-8"))}
        for row in csv.DictReader((D3 / "bounty_cache_legendaries.csv").open(encoding="utf-8")):
            base = bases[ids[int(row["item_entry"])]]
            self.assertEqual((base["rarity"], base["d3_name"]), ("legendary", row["d3_name"]))

    def sheets(self, edit):
        """The generator on a copy of the sheets with `edit(folder)` applied."""
        with tempfile.TemporaryDirectory() as folder:
            for name in SHEETS:
                shutil.copy(D3 / name, folder)
            edit(Path(folder))
            self.assertTrue(str(Path(folder) / "bounty_caches.csv").startswith(tempfile.gettempdir()))
            return G.render_caches(folder)

    @staticmethod
    def replace(folder, name, old, new):
        path = folder / name
        text = path.read_text(encoding="utf-8")
        assert text.count(old) >= 1, old
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_an_empty_pool_renders_and_rolls_nothing(self):
        def drop_column_one(folder):
            path = folder / "bounty_cache_legendaries.csv"
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            path.write_text("".join(line for line in lines if not line.startswith("1,")), encoding="utf-8")
        sql = self.sheets(drop_column_one)
        self.assertNotIn("(1, 100089)", sql)
        self.assertIn("'Horadric Cache (Act I)', 15590, 2, 4, 1, 0, 0, 0, 0, 1, 0, 1, 0, 1, 'Earned by completing a column of "
                      "bounties. Opens into gold, Blood Shards, Khanduran Rune, gems, Death''s Breath and rare items.')", sql)

    def test_refusals(self):
        broken = {
            "a generic base in a pool": ("bounty_cache_legendaries.csv", "1,100089,Ring of Royal Grandeur", "1,100000,Ring of Royal Grandeur"),
            "an item Torment does not have": ("bounty_cache_legendaries.csv", "1,100089,", "1,99999,"),
            "the wrong name for the item": ("bounty_cache_legendaries.csv", "1,100089,Ring of Royal Grandeur", "1,100089,Avarice Band"),
            "a pool for a column with no cache": ("bounty_cache_legendaries.csv", "5,100951,", "6,100951,"),
            "a reagent that is no material": ("bounty_caches.csv", ",102008,", ",102006,"),
            "a set cache's entry": ("bounty_caches.csv", "1,101141,", "1,101114,"),
            "a base item's entry": ("bounty_caches.csv", "1,101141,", "1,100089,"),
            "a column twice": ("bounty_caches.csv", "2,101142,", "1,101142,"),
            "a column off the board": ("bounty_caches.csv", "5,101145,", "6,101145,"),
        }
        for why, (name, old, new) in broken.items():
            with self.subTest(why):
                with self.assertRaises(ValueError):
                    self.sheets(lambda folder: self.replace(folder, name, old, new))

    def test_the_item_rows_are_what_build_item_reads_and_item_dbc_has_them(self):
        tool = build_item()
        self.assertIn(G.CACHES, tool.APPEND_SQL)
        rows = tool.sql_item_rows(CACHE_MIGRATION)
        self.assertEqual(sorted(rows), [101141, 101142, 101143, 101144, 101145])
        for record in rows.values():
            self.assertEqual((record[0], record[1], record[4]), (15, 0, 15590))  # miscellaneous junk, the junkbox display
        data = (ROOT / "client-patch/dbc/Item.dbc").read_bytes()
        _, count, _, size, _ = struct.unpack_from("<4sIIII", data)
        present = {struct.unpack_from("<I", data, 20 + i * size)[0]: struct.unpack_from("<IIIiiIII", data, 20 + i * size)[1:]
                   for i in range(count)}
        for entry, record in rows.items():
            self.assertEqual(present.get(entry), record, f"Item.dbc row {entry}")

    def test_the_tier_table_is_keyed_by_item_guid(self):
        sql = TIER_MIGRATION.read_text(encoding="utf-8")
        self.assertIn("CREATE TABLE IF NOT EXISTS `dc_bounties_cache_item`", sql)
        self.assertIn("PRIMARY KEY (`item_guid`)", sql)


# --- 2. the tunables ----------------------------------------------------------------------------------------------------

def tunables():
    """{name: (d3_value, value, notes)} of the bounty_cache_* rows of rifts.csv."""
    with RIFTS_CSV.open(encoding="utf-8") as stream:
        return {r["name"]: (r["d3_value"], r["value"], r["notes"]) for r in csv.DictReader(stream)
                if r["name"].startswith("bounty_cache_")}


def generated():
    """{name: the value the server reads} of the bounty_cache_* rows of the generated migration (tuned, else D3's)."""
    out = {}
    for name, d3, tuned in re.findall(r"\('rifts', '(bounty_cache_\w+)', (NULL|-?[\d.]+), (NULL|-?[\d.]+),",
                                      TUNABLES_SQL.read_text(encoding="utf-8")):
        out[name] = float(tuned if tuned != "NULL" else d3)
    return out


class Tunables(unittest.TestCase):
    def test_the_notes_scale_by_the_earned_tier(self):
        # diablocraft-52737: the amounts scale by the tier the cache was earned on (dc_bounties_cache_item), not the opener's
        amounts = [n for n in tunables() if not n.startswith(("bounty_cache_scale_pct_", "bounty_cache_gem_rank_"))]
        self.assertEqual(len(amounts), 9)
        for name in amounts:
            notes = tunables()[name][2]
            self.assertIn("the tier the cache was earned on", notes, name)
            self.assertNotIn("opener's tier", notes, name)

    def test_the_top_is_maxroll(self):
        rows = tunables()
        for name, d3 in (("gold", "1640000"), ("blood_shards", "135"), ("reagent", "22"), ("gems_min", "1"), ("gems_max", "4"),
                         ("deaths_breath", "6"), ("rares_min", "1"), ("rares_max", "2"), ("legendaries", "2")):
            self.assertEqual(rows["bounty_cache_" + name][:2], (d3, ""), name)
            self.assertIn("maxroll", rows["bounty_cache_" + name][2])

    def test_twenty_tiers_each_lower_one_a_placeholder(self):
        rows = tunables()
        for tier in range(1, 21):
            scale, grade = rows[f"bounty_cache_scale_pct_tier_{tier:02d}"], rows[f"bounty_cache_gem_rank_tier_{tier:02d}"]
            if tier == 20:
                self.assertEqual((scale[:2], grade[:2]), (("100", ""), ("6", "")))
            else:
                self.assertEqual((scale[:2], grade[:2]), (("", "100"), ("", "6")))
                self.assertIn("PLACEHOLDER", scale[2])
                self.assertIn("PLACEHOLDER", grade[2])
        self.assertEqual(len(rows), 9 + 40)

    def test_the_generated_migration_carries_every_row(self):
        self.assertEqual(set(generated()), set(tunables()))

    def test_marquise_is_rank_six_in_each_of_the_five_colours(self):
        sql = (G.MODULE / "data/sql/db-world/updates/crafting_0007_crafting_tunables.sql").read_text(encoding="utf-8")
        marquise = re.findall(r"\((\d+),'[^']+','Marquise',(\d+),", sql)
        self.assertEqual(len(marquise), 5)  # Amethyst, Diamond, Emerald, Ruby, Topaz
        self.assertEqual({rank for _, rank in marquise}, {"6"})


# --- 3. the rules, fed the generated values -----------------------------------------------------------------------------

RULE_MAIN = r'''
#include <cassert>
#include <vector>
using namespace DC::Bounties::Cache;
struct Seq { std::uint32_t n = 0; std::uint32_t operator()(std::uint32_t lo, std::uint32_t hi) { return lo + (n++ % (hi - lo + 1)); } };
int main() {
    Top top{GEN_gold, GEN_blood_shards, GEN_reagent, GEN_deaths_breath, GEN_gems_min, GEN_gems_max, GEN_rares_min, GEN_rares_max, GEN_legendaries};
    double const t16 = GEN_scale_pct_tier_20, normal = GEN_scale_pct_tier_01;
'''


def compile_rule(body, rule=RULE):
    values = generated()
    main = RULE_MAIN
    for name, value in sorted(values.items(), key=lambda item: -len(item[0])):
        main = main.replace("GEN_" + name[len("bounty_cache_"):], repr(value))
    return run(rule + main + body + "\n    return 0;\n}\n")


def rule_both(test, body, old, new):
    ok, out = compile_rule(body)
    test.assertTrue(ok, out)
    ok, out = compile_rule(body, mutate(RULE, old, new))
    test.assertFalse(ok, "mutation survived: " + new)


class Rules(unittest.TestCase):
    def test_torment_xvi_pays_maxroll(self):
        rule_both(self, '''
    Amounts a = Scale(top, t16);
    assert(a.gold == 1640000 && a.shards == 135 && a.reagent == 22 && a.deathsBreath == 6);
    assert(a.gemsMin == 1 && a.gemsMax == 4 && a.raresMin == 1 && a.raresMax == 2 && a.legendaries == 2);
    Amounts same = Scale(top, normal); assert(same.gold == a.gold);              // the placeholder: every tier at the top''',
                  "double const value = top * pct / 100.0;", "double const value = top * pct / 10.0;")

    def test_a_scale_rounds_to_the_nearest_whole(self):
        rule_both(self, '''
    Amounts h = Scale(top, 50);
    assert(h.gold == 820000 && h.shards == 68 && h.reagent == 11 && h.gemsMax == 2 && h.raresMax == 1);''',
                  "std::llround(std::min(value, 1e15))", "std::floor(std::min(value, 1e15))")

    def test_nothing_for_a_bad_cell_and_counts_are_capped(self):
        rule_both(self, '''
    assert(Scaled(-5, 100) == 0 && Scaled(0.0 / 0.0, 100) == 0 && Scaled(5, -1) == 0);
    assert(Count(1e9, 100) == 1000);''',
                  "if (!std::isfinite(value) || value <= 0)", "if (!std::isfinite(value))")

    def test_min_and_max_set_the_wrong_way_round_are_swapped(self):
        rule_both(self, '''
    Top back = top; back.gemsMin = 4; back.gemsMax = 1;
    Amounts a = Scale(back, 100); assert(a.gemsMin == 1 && a.gemsMax == 4);''',
                  "a.gemsMin = Count(std::min(top.gemsMin, top.gemsMax), pct);", "a.gemsMin = Count(top.gemsMin, pct);")

    def test_an_empty_pool_rolls_no_legendary(self):
        rule_both(self, '''
    Seq rng; Amounts a = Scale(top, t16);
    Counts c = Roll(a, false, std::ref(rng)); assert(c.gems >= 1 && c.gems <= 4 && c.rares >= 1 && c.rares <= 2 && c.legendaries == 2);
    assert(Roll(a, true, std::ref(rng)).legendaries == 0);''',
                  "poolEmpty ? 0u : a.legendaries", "a.legendaries")

    def test_the_refusals_in_order_before_anything_moves(self):
        rule_both(self, '''
    Facts f; f.alive = true; f.ledger = f.earned = f.rows = true; f.items = 8; f.freeSlots = 7;
    assert(Judge(f) == Verdict::Open);                               // the cache's own slot is the eighth
    Facts g = f; g.freeSlots = 6; assert(Judge(g) == Verdict::BagsShort);
    assert(Refusal(Verdict::BagsShort, "Horadric Cache (Tanaris)", 8, 6) == "Horadric Cache (Tanaris) needs 7 free bag slots; you have 6.");
    Facts h = f; h.earned = false; assert(Judge(h) == Verdict::NoRecord);
    Facts r = f; r.rows = false; assert(Judge(r) == Verdict::NoRows);
    Facts l = f; l.ledger = false; l.earned = false; assert(Judge(l) == Verdict::NoLedger);
    Facts d = f; d.alive = false; d.inCombat = true; assert(Judge(d) == Verdict::Dead);
    Facts c = f; c.inCombat = true; c.inTrade = true; assert(Judge(c) == Verdict::InCombat);
    assert(Refusal(Verdict::NoRecord, "X", 0, 0) == "X cannot be opened. Report it.");
    assert(SlotsNeeded(0) == 0);''',
                  "return items > 0 ? items - 1 : 0;", "return items;")

    def test_a_cache_with_no_record_is_refused(self):
        rule_both(self, 'Facts f; f.alive = f.ledger = f.rows = true; assert(Judge(f) == Verdict::NoRecord);',
                  "        if (!f.earned)\n", "        if (false)\n")

    def test_the_tier_rows_run_01_to_20(self):
        rule_both(self, '''
    assert(TierRow("bounty_cache_scale_pct", 5) == "bounty_cache_scale_pct_tier_05");
    assert(TierRow("bounty_cache_gem_rank", 20) == "bounty_cache_gem_rank_tier_20");
    assert(TierRow("bounty_cache_scale_pct", 0).empty() && TierRow("bounty_cache_scale_pct", 21).empty());''',
                  "if (tier < 1 || tier > Tiers)", "if (tier < 1)")

    def test_the_lines(self):
        rule_both(self, '''
    assert(StashLine("Horadric Cache (Azshara)") == "Your bags were full: Horadric Cache (Azshara) went to your Stash.");
    assert(LostLine("Horadric Cache (Azshara)") == "Your bags and Stash were full: Horadric Cache (Azshara) was lost.");''',
                  '" went to your Stash."', '" went somewhere."')


# --- 4. the delivery, cut out of dc_bounty_cache.cpp --------------------------------------------------------------------

DELIVER_DOUBLES = r'''
#include <cassert>
#include <functional>
#include <memory>
#include <string>
#include <tuple>
#include <vector>
#define LOG_INFO(...) ((void)0)
using uint32 = std::uint32_t;
struct Trans { std::vector<std::string> rows; void Append(char const* sql) { rows.push_back(sql); } };
// fmt's "{}" in order, which is all the record uses.
namespace Acore { inline void Fill(std::string&) {}
    template<class T, class... A> void Fill(std::string& f, T v, A... rest) { f.replace(f.find("{}"), 2, std::to_string(v)); Fill(f, rest...); }
    template<class... A> std::string StringFormat(char const* f, A... a) { std::string out = f; Fill(out, a...); return out; } }
using CharacterDatabaseTransaction = std::shared_ptr<Trans>;
struct Guid { unsigned long long low; unsigned long long GetCounter() const { return low; } };
struct Item { unsigned long long guid; Guid GetGUID() const { return {guid}; } };
using ItemPosCountVec = std::vector<int>;
enum { NULL_BAG = 255, NULL_SLOT = 255, EQUIP_ERR_OK = 0, EQUIP_ERR_INV_FULL = 50 };
struct Session { bool aborted = false; void AbortEconomy() { aborted = true; } };
struct Player {
    Session session; bool bagsRoom = true; std::vector<Item*> stored, announced; std::vector<std::string> said; int saves = 0;
    Session* GetSession() { return &session; } std::string GetName() const { return "Calmoran"; }
    int CanStoreNewItem(int, int, ItemPosCountVec&, uint32, uint32) const { return bagsRoom ? EQUIP_ERR_OK : EQUIP_ERR_INV_FULL; }
    Item* StoreNewItem(ItemPosCountVec const&, uint32, bool) { stored.push_back(new Item{900 + stored.size()}); return stored.back(); }
    void SaveInventoryAndGoldToDB(CharacterDatabaseTransaction const&) { ++saves; }
    void SendNewItem(Item* item, uint32, bool, bool, bool) { announced.push_back(item); }
};
struct ChatHandler { Player* p; explicit ChatHandler(Session* s) : p(nullptr) { (void)s; } void SendSysMessage(std::string const& t); };
Player* chatTo = nullptr; void ChatHandler::SendSysMessage(std::string const& t) { chatTo->said.push_back(t); }
CharacterDatabaseTransaction lastTrans; int fails = 0; bool commits = true;
namespace PlayerEconomy { struct Scope { explicit Scope(Player*) {} }; CharacterDatabaseTransaction BeginTransaction() { return lastTrans = std::make_shared<Trans>(); } void Fail() { ++fails; } }
namespace DC::AccountEconomy { bool Commit(Player*, CharacterDatabaseTransaction const&) { return commits; } }
// The stash: room or full; a delivery hands the caller's rows its own transaction and a new item.
bool stashRoom = true; CharacterDatabaseTransaction stashTrans; uint32 stashEntry = 0;
namespace DC::Stash { bool DeliverNew(Player*, uint32 entry, std::function<std::string(uint32)> const& also) {
    if (!stashRoom) return false; stashEntry = entry; stashTrans = std::make_shared<Trans>(); if (also) stashTrans->Append(also(77).c_str()); return true; } }
namespace DC::Bounties {
'''


def deliver_source(cache=CACHE):
    return (RULE + DELIVER_DOUBLES + definition(cache, "struct CacheRow") + ";\n" + definition(cache, "struct Staged") + ";\n"
            + definition(cache, "bool Deliver(") + "\n}\n")


DELIVER_MAIN = r'''
using namespace DC::Bounties;
int main() {
    CacheRow tanaris; tanaris.column = 2; tanaris.entry = 101142; tanaris.name = "Horadric Cache (Tanaris)";
    Player p; chatTo = &p;
'''


def compile_deliver(body, cache=CACHE):
    return run(deliver_source(cache) + DELIVER_MAIN + body + "\n    return 0;\n}\n")


def deliver_both(test, body, old, new):
    ok, out = compile_deliver(body)
    test.assertTrue(ok, out)
    ok, out = compile_deliver(body, mutate(CACHE, old, new))
    test.assertFalse(ok, "mutation survived: " + new)


class Delivery(unittest.TestCase):
    def test_at_logout_the_stash_only_so_no_bag_commit_can_fail(self):
        # diablocraft-52737: the logout's save flag is fixed before its hook, so the bags are never tried there
        deliver_both(self, '''
    commits = false;                                                   // a bag commit would fail and abort the economy
    assert(Deliver(&p, tanaris, 5, false));
    assert(p.stored.empty() && !p.session.aborted && fails == 0 && p.said.empty() && stashEntry == 101142
           && (stashTrans->rows == std::vector<std::string>{"INSERT INTO dc_bounties_cache_item (item_guid,col,tier) VALUES (77,2,5)"}));''',
                     "if (bags && player->CanStoreNewItem(", "if (player->CanStoreNewItem(")

    def test_at_logout_a_full_stash_is_not_lost(self):
        deliver_both(self, '''
    stashRoom = false;
    assert(!Deliver(&p, tanaris, 5, false) && p.said.empty() && p.stored.empty());''',
                     "            if (!bags)\n                return false;\n", "")

    def test_the_logout_hook_pays_into_the_stash_only(self):
        hook = definition(CACHE, "void OnPlayerBeforeLogout(")
        self.assertIn("PayOwed(player, true);", hook)
        self.assertIn("PayOwed(player);", definition(CACHE, "void OnPlayerUpdate("))

    def test_the_bags_first_with_the_tier_in_the_same_transaction(self):
        deliver_both(self, '''
    assert(Deliver(&p, tanaris, 7));
    assert(p.stored.size() == 1 && p.announced == p.stored && p.saves == 1 && p.said.empty() && !p.session.aborted);
    assert((lastTrans->rows == std::vector<std::string>{"INSERT INTO dc_bounties_cache_item (item_guid,col,tier) VALUES (900,2,7)"}) && !stashTrans);''',
                     "itemGuid, cache.column, tier);", "itemGuid, cache.column, 0u);")

    def test_full_bags_go_to_the_stash_with_the_same_row_and_a_line(self):
        deliver_both(self, '''
    p.bagsRoom = false;
    assert(Deliver(&p, tanaris, 12));
    assert(p.stored.empty() && stashEntry == 101142
           && (stashTrans->rows == std::vector<std::string>{"INSERT INTO dc_bounties_cache_item (item_guid,col,tier) VALUES (77,2,12)"}));
    assert(p.said == std::vector<std::string>{"Your bags were full: Horadric Cache (Tanaris) went to your Stash."});''',
                     "if (DC::Stash::DeliverNew(player, cache.entry, record))", "if (DC::Stash::DeliverNew(player, cache.entry, nullptr))")

    def test_both_full_is_lost_with_the_line(self):
        deliver_both(self, '''
    p.bagsRoom = false; stashRoom = false;
    assert(!Deliver(&p, tanaris, 3));
    assert(p.said == std::vector<std::string>{"Your bags and Stash were full: Horadric Cache (Tanaris) was lost."});''',
                     "            chat.SendSysMessage(Cache::LostLine(cache.name));\n", "")

    def test_a_failed_commit_reloads_the_session(self):
        deliver_both(self, '''
    commits = false;
    assert(!Deliver(&p, tanaris, 3) && p.session.aborted && fails == 1 && p.announced.empty());
    commits = true; Player q; chatTo = &q;
    assert(Deliver(&q, tanaris, 3) && !q.session.aborted);''',
                     "                guard.committed = true;\n                player->SendNewItem(item, 1, true, false, false);",
                     "                player->SendNewItem(item, 1, true, false, false);")


# --- 5. the stash insert, cut out of dc_stash.cpp -----------------------------------------------------------------------

STASH_DOUBLES = r'''
#include <cassert>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>
#define LOG_ERROR(...) ((void)0)
#define LOG_INFO(...) ((void)0)
using uint8 = std::uint8_t; using uint32 = std::uint32_t;
struct Trans { std::vector<std::string> ops; template<class... A> void Append(char const* sql, A...) { ops.push_back(sql); } };
using CharacterDatabaseTransaction = std::shared_ptr<Trans>;
struct Guid { uint32 low; uint32 GetCounter() const { return low; } };
int created = 0, deleted = 0, purged = 0; bool commits = true; std::vector<std::string> committed;
struct Item {
    uint32 entry; bool inWorld = false; Guid GetGUID() const { return {500}; } void AddToWorld() { inWorld = true; }
    static Item* CreateItem(uint32 entry, uint32, void const*) { ++created; return new Item{entry}; }
    ~Item() { ++deleted; }
};
struct Session { uint32 GetAccountId() const { return 9; } };
struct Player { Session s; Session* GetSession() { return &s; } Guid GetGUID() const { return {42}; } std::string GetName() const { return "Calmoran"; } };
struct ObjectMgr { void const* GetItemTemplate(uint32 entry) { return entry == 101141 ? this : nullptr; } } objectMgr, *sObjectMgr = &objectMgr;
namespace Hardcore { enum class Mode { Unchosen, Normal, Hardcore }; Mode mode = Mode::Normal; bool locked = false, pending = false;
    Mode ModeOf(Player const*) { return mode; } bool IsLocked(uint32) { return locked; } bool DeathPending(Player const*) { return pending; } }
namespace DC::Stash {
    constexpr std::uint8_t SlotsPerTab = 70;
    std::uint8_t LaunchTabs() { return 1; }
'''

STASH_TAIL = r'''
    std::map<Key, Container> containers;
    std::mutex lockOne; std::shared_ptr<std::mutex> OperationLock(Key const&) { return std::shared_ptr<std::mutex>(&lockOne, [](std::mutex*) {}); }
    Container& Get(Key const& key) { return containers[key]; }
    void Park(CharacterDatabaseTransaction const& t, Item*) { t->Append("park"); }
    void ClearSlot(CharacterDatabaseTransaction const& t, Key const&, std::uint16_t position) { t->Append(("clear " + std::to_string(position)).c_str()); }
    void FillSlot(CharacterDatabaseTransaction const& t, Key const&, std::uint16_t position, Item*) { t->Append(("fill " + std::to_string(position)).c_str()); }
    bool Commit(Key const&, Container& container, CharacterDatabaseTransaction& t) { ++container.revision; if (commits) committed = t->ops; return commits; }
    void Purge(Key const& key) { ++purged; containers.erase(key); }
'''


def stash_source(stash=STASH):
    # The ClearSlot/FillSlot doubles append a std::string's c_str(): copy it into ops before it dies.
    doubles = STASH_DOUBLES.replace("ops.push_back(sql);", "ops.push_back(std::string(sql));")
    return (doubles + definition(stash, "struct Key") + ";\n" + definition(stash, "struct Container") + ";\n"
            + STASH_TAIL + definition(stash, "std::uint16_t FirstFreeStashSlot(") + "\n"
            + definition(stash, "bool DeliverNew(") + "\n}\n")


STASH_MAIN = r'''
using namespace DC::Stash;
struct CharacterDatabaseClass { CharacterDatabaseTransaction BeginTransaction() { return std::make_shared<Trans>(); } } CharacterDatabase;
int main() {
    Player p; Key const mine{9, false};
    auto row = [](uint32 guid) { return "tier row " + std::to_string(guid); };
'''


def compile_stash(body, stash=STASH):
    # CharacterDatabase is used inside DeliverNew, so it is declared before the cut.
    source = stash_source(stash).replace("namespace DC::Stash {\n    constexpr",
                                         "struct CharacterDatabaseClass { CharacterDatabaseTransaction BeginTransaction() { return std::make_shared<Trans>(); } } CharacterDatabase;\nnamespace DC::Stash {\n    constexpr", 1)
    main = STASH_MAIN.replace("struct CharacterDatabaseClass { CharacterDatabaseTransaction BeginTransaction() { return std::make_shared<Trans>(); } } CharacterDatabase;\n", "")
    return run(source + main + body + "\n    return 0;\n}\n")


def stash_both(test, body, old, new):
    ok, out = compile_stash(body)
    test.assertTrue(ok, out)
    ok, out = compile_stash(body, mutate(STASH, old, new))
    test.assertFalse(ok, "mutation survived: " + new)


class StashInsert(unittest.TestCase):
    def test_the_first_free_slot_in_one_durable_write_through_the_container(self):
        stash_both(self, '''
    Item first{1}; containers[mine].items[0] = &first;
    assert(DeliverNew(&p, 101141, row));
    Container& c = containers[mine];
    assert(c.items.size() == 2 && c.items[1]->entry == 101141 && c.items[1]->inWorld && c.revision == 1);
    assert((committed == std::vector<std::string>{"park", "clear 1", "fill 1", "tier row 500"}));
    assert(DeliverNew(&p, 101141, nullptr) && committed.size() == 3);                 // no statement of the caller's: none written''',
                   "            transaction->Append(statement.c_str());\n", "            ;\n")

    def test_no_mode_a_fallen_hardcore_or_an_unknown_item_writes_nothing(self):
        stash_both(self, '''
    Hardcore::mode = Hardcore::Mode::Unchosen; assert(!DeliverNew(&p, 101141, row));
    Hardcore::mode = Hardcore::Mode::Normal; Hardcore::locked = true; assert(!DeliverNew(&p, 101141, row));
    Hardcore::locked = false; Hardcore::pending = true; assert(!DeliverNew(&p, 101141, row));
    Hardcore::pending = false; assert(!DeliverNew(&p, 999, row));
    assert(created == 0 && committed.empty());''',
                   "Hardcore::IsLocked(player->GetGUID().GetCounter()) ||", "")

    def test_a_full_stash_creates_no_item(self):
        stash_both(self, '''
    Item filler{1}; for (std::uint16_t s = 0; s < SlotsPerTab; ++s) containers[mine].items[s] = &filler;
    assert(!DeliverNew(&p, 101141, row) && created == 0 && committed.empty());''',
                   "        catch (std::runtime_error const&)\n        {\n            return false;\n        }",
                   "        catch (std::runtime_error const&)\n        {\n        }")

    def test_a_failed_commit_frees_the_item_and_drops_the_cache(self):
        stash_both(self, '''
    commits = false;
    assert(!DeliverNew(&p, 101141, row) && created == 1 && deleted == 1 && purged == 1 && !containers.count(mine));''',
                   "            delete item;\n            Purge(key);\n", "            delete item;\n")

    def test_the_hardcore_mode_has_its_own_stash(self):
        stash_both(self, '''
    Hardcore::mode = Hardcore::Mode::Hardcore;
    assert(DeliverNew(&p, 101141, row) && containers.count(Key{9, true}) && !containers.count(mine));''',
                   "mode == Hardcore::Mode::Hardcore};\n        std::lock_guard", "false};\n        std::lock_guard")


# --- 6. the debts, and the completion that makes them -------------------------------------------------------------------

OWED_DOUBLES = r'''
#include <atomic>
#include <cassert>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>
#define LOG_ERROR(...) ((void)0)
struct ObjectGuid { unsigned low; bool operator==(ObjectGuid o) const { return low == o.low; } };
template <> struct std::hash<ObjectGuid> { std::size_t operator()(ObjectGuid g) const { return g.low; } };
struct Player { ObjectGuid guid; unsigned tier; ObjectGuid GetGUID() const { return guid; } };
namespace DC::Difficulty { unsigned CurrentTier(Player const* p) { return p->tier; } }
namespace DC::Bounties {
    struct CacheRow { unsigned column = 0; };
    bool ByColumn(unsigned column, CacheRow& out) { out.column = column; return column >= 1 && column <= 5; }
    struct Paid { unsigned guid, column, tier; }; std::vector<Paid> paid;
    bool delivers = true; std::vector<bool> bagsAsked;   // false: the stash could not take it (at logout)
    bool Deliver(Player* p, CacheRow const& c, unsigned tier, bool bags) {
        bagsAsked.push_back(bags); if (!delivers) return false; paid.push_back({p->guid.low, c.column, tier}); return true; }
'''


def owed_source(cache=CACHE):
    return (OWED_DOUBLES + definition(cache, "struct Owed") + ";\n"
            + "std::mutex owedMutex; std::unordered_map<ObjectGuid, std::vector<Owed>> owed; std::atomic<unsigned> owedCount{0};\n"
            + definition(cache, "std::vector<Owed> TakeOwed(") + "\n" + definition(cache, "void PayOwed(") + "\n"
            + definition(cache, "void OweCache(") + "\n}\n")


def compile_owed(body, cache=CACHE):
    return run(owed_source(cache) + "using namespace DC::Bounties;\nint main() {\n" + body + "\n    return 0;\n}\n")


def owed_both(test, body, old, new):
    ok, out = compile_owed(body)
    test.assertTrue(ok, out)
    ok, out = compile_owed(body, mutate(CACHE, old, new))
    test.assertFalse(ok, "mutation survived: " + new)


class Room(unittest.TestCase):
    """diablocraft-wuvw: the open counts only room its items can go into (DC::Items::FreeSlotsFor, whose rule
    test_set_caches.py compiles and drives with the core's ItemCanGoIntoBag), never every free slot of every bag."""

    @staticmethod
    def problems(source):
        body = definition(source, "void Open(")
        live = "\n".join(l.split("//")[0] for l in body.splitlines())
        out = []
        if "facts.freeSlots = DC::Items::FreeSlotsFor(player, templates);" not in live or "GetFreeInventorySpace" in live:
            out.append("the free slots are not FreeSlotsFor's")
        if not re.search(r"for \(auto const\* list : \{&rares, &legendaries, &gems\}\)\s+for \(std::uint32_t entry : \*list\)\s+"
                         r"templates\.push_back\(sObjectMgr->GetItemTemplate\(entry\)\);", live):
            out.append("not every item the cache holds is asked about")
        if live.index("facts.freeSlots =") > live.index("DestroyWithRows("):
            out.append("the room is counted after the cache is destroyed")
        return out

    def test_the_room_is_what_the_items_can_go_into(self):
        self.assertEqual(self.problems(CACHE), [])
        for old, new in (("facts.freeSlots = DC::Items::FreeSlotsFor(player, templates);", "facts.freeSlots = player->GetFreeInventorySpace();"),
                         ("{&rares, &legendaries, &gems}", "{&rares, &legendaries}")):
            self.assertNotEqual(self.problems(mutate(CACHE, old, new)), [], new)


class Debts(unittest.TestCase):
    def test_at_logout_the_stash_only_and_an_unpaid_cache_stays_owed(self):
        # diablocraft-52737: logout pays into the stash only; what it cannot take is paid on the next login's update
        body = '''
    Player a{{1}, 7}; OweCache(&a, 2);
    delivers = false; PayOwed(&a, true);
    assert(paid.empty() && owedCount == 1 && bagsAsked == std::vector<bool>{false});
    delivers = true; a.tier = 1; PayOwed(&a);
    assert(paid.size() == 1 && paid[0].tier == 7 && owedCount == 0 && (bagsAsked == std::vector<bool>{false, true}));'''
        owed_both(self, body, "                    owed[player->GetGUID()].push_back(debt);\n", "")
        owed_both(self, body, "Deliver(player, cache, debt.tier, !atLogout)", "Deliver(player, cache, debt.tier, true)")

    def test_each_member_is_paid_once_at_the_tier_they_had(self):
        owed_both(self, '''
    Player a{{1}, 7}, b{{2}, 7};
    OweCache(&a, 2); OweCache(&b, 2); a.tier = 1;                       // a tier change after the completion pays nothing less
    assert(owedCount == 2);
    PayOwed(&a); PayOwed(&a);
    assert(paid.size() == 1 && paid[0].guid == 1 && paid[0].column == 2 && paid[0].tier == 7 && owedCount == 1);
    PayOwed(&b); assert(paid.size() == 2 && paid[1].guid == 2 && owedCount == 0);''',
                  "std::vector<Owed> out = std::move(found->second);\n            owed.erase(found);",
                  "std::vector<Owed> out = found->second;")  # the debt kept: paid again on the next update

    def test_the_debt_keeps_the_owing_moments_tier(self):
        owed_both(self, '''
    Player a{{1}, 9}; OweCache(&a, 1); a.tier = 3; PayOwed(&a); assert(paid.at(0).tier == 9);''',
                  "unsigned const tier = DC::Difficulty::CurrentTier(member);", "unsigned const tier = 0;")


CREDIT_DOUBLES = r'''
std::vector<std::pair<unsigned, unsigned>> owedTo;   // (owner id the member stands for, column)
std::vector<Player*> online;
std::vector<Player*> Online(Owner) { return online; }
void ShowAll(Owner, std::string const& = "") {}
void OweCache(Player* member, unsigned column) { owedTo.emplace_back(member->owner.id, column); }
'''


def credit_source(server=SERVER):
    return owners_source(server) + CREDIT_DOUBLES + "template<class Step>\n" + definition(server, "bool Credit(") + "\n"


def compile_credit(body, server=SERVER):
    sql = first_set_sql()
    code = (PRELUDE + "#include <mutex>\nstd::mutex boardMutex;\n" + DOUBLES + BOARD + catalogue_cpp(sql) + HELPERS
            + credit_source(server) + "int main() {\n" + body + "\n    return 0;\n}\n")
    return run(code)


class Completion(unittest.TestCase):
    def test_a_finished_column_owes_every_online_member_and_a_step_owes_nobody(self):
        body = '''
    Player leader{Owner{1, 70}}, other{Owner{1, 70}};
    Board& b = LoadLocked(Owner{1, 70}); assert(b.empty());
    boards[Owner{1, 70}] = Draw(catalog, targets, Rules{2, 3, 6}, std::ref(seq));
    online = {&leader, &other};
    std::uint32_t const first = At(boards[Owner{1, 70}], 1, 2)->bounty;   // diablocraft-hyoic.1: act 1 has two zones
    assert(Credit(&leader, first, [&](Board& board) { return Complete(board, first); }) && owedTo.empty());   // half the act: no cache
    Cell const* kill = At(boards[Owner{1, 70}], 1, 1);
    assert(Credit(&leader, kill->bounty, [&](Board& board) { return AddProgress(board, kill->bounty, 1); }) && owedTo.empty());
    std::uint32_t const id = kill->bounty;
    assert(Credit(&leader, id, [&](Board& board) { return Complete(board, id); }));
    assert(owedTo.size() == 2 && owedTo[0].second == 1 && owedTo[1].second == 1);
    assert(!Credit(&leader, id, [&](Board& board) { return Complete(board, id); }) && owedTo.size() == 2);   // done once'''
        ok, out = compile_credit(body)
        self.assertTrue(ok, out)
        ok, out = compile_credit(body, mutate(SERVER, "            if (change.columnDone)\n", "            if (change.completed && false)\n"))
        self.assertFalse(ok, "mutation survived: the completion owes nothing")


if __name__ == "__main__":
    unittest.main()
