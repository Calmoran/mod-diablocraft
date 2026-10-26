"""diablocraft-bzr0 - the set caches (kadala.md section 6.6, Part 8): rows, rule header, hook wiring, replay.

What this proves, and what it does not:

  * The data. `set_caches_0007.sql` (0001, applied, is the 27 before the Monk; 0002, applied on dev, the 33 before the Necromancer; 0004, applied on dev, the 39 before the Crusader; 0005, applied on dev, the 45 before the Demon Hunter; 0006, applied on dev, the 51 before the Witch Doctor) is parsed and compared with a second computation: the set pieces the APPLIED slot
    vendor migration lists (the newest slot_vendors_NNNN.sql's npc_vendor rows), grouped by the set each belongs to in
    base_items.csv. One cache per set that has a listed piece and for no other; each cache's pieces are exactly
    that set's listed pieces; its name is the set's, its description names every piece within 255 characters, its
    price and sell price are 0 and its flags are the has-loot flag; the vendor lists the caches A to Z, free, with a
    level condition equal to the highest level among the set's pieces (a cache never gives a piece the slot vendor
    would hide). The cache rows are also read by client-patch/dbc/build_item.py's own migration reader (Part 9).
    No cache or vendor entry is used anywhere else, and nothing names Kadala, a Blood Shard or a price.
  * The decisions. The production header `src/items/dc_set_cache_rule.h` is compiled into a harness with the slot
    vendors' roll rule and the identify rule (G7) and driven with the sheets' values: the roll class of every piece
    for every playable opener, every refusal in its order, the free-slot arithmetic of every cache at the edge, the
    chat line, and agreement with G7. Each rule has a mutant of the header that must turn the harness red.
  * The hook's WIRING (`dc_set_cache.cpp`) is read with comments removed: it answers every cache and no other item,
    refusals included, destroys the cache before it stages, stages every piece in the one transaction, commits once,
    publishes after the commit. It is NOT executed: that needs a Player, which is the GM script in
    docs/test-diablocraft-bzr0.md.
  * `set_caches_0007.sql` is replayed twice on a disposable MySQL with stub core tables and read back.
"""
import csv
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_set_caches as gen
import generate_sql
import generate_slot_vendors as slot_gen
import harness_env
import test_slot_vendors as slot_test
from test_account_economy_sql import MYSQL, ROOT, isolated
from test_slot_vendors import check, code, cpp_str, mutate, rows, squash

MODULE = ROOT / "mod-diablocraft"
D3 = MODULE / "data/d3"
SRC = MODULE / "src"
HEADER = SRC / "items/dc_set_cache_rule.h"
HOOK = SRC / "items/dc_set_cache.cpp"
ITEMS = SRC / "items/dc_items.cpp"
SLOT_HEADER = SRC / "items/dc_slot_vendor_rule.h"
IDENTIFY_HEADER = SRC / "items/dc_identify_rule.h"
ROLL_CLASS = SRC / "items/dc_roll_class.h"
UPDATES = MODULE / "data/sql/db-world/updates"
MIGRATION = UPDATES / gen.NAME
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/set_caches_test"
SHEETS = ("slot_vendors.csv", "base_items.csv", "base_item_ids.csv", "set_classes.csv", "class_map.csv",
          "set_caches.csv", "set_cache_vendor.csv", "bounty_cache_legendaries.csv")


# ---- the data --------------------------------------------------------------------------------------------------------

ITEM_ROW = re.compile(r"^  \((\d+), (\d+), (\d+), '((?:[^']|'')*)', (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), "
                      r"(\d+), (\d+), (-?\d+), (\d+), (\d+), '((?:[^']|'')*)'\)[,;]$", re.M)


def unquote(text):
    return text.replace("''", "'")


def parsed_items(text):
    """{entry: dict} of the item_template rows, by column name."""
    names = ("entry", "class", "subclass", "name", "displayid", "Quality", "Flags", "BuyCount", "BuyPrice", "SellPrice",
             "InventoryType", "maxcount", "stackable", "BagFamily", "Material", "bonding", "ItemLevel", "description")
    out = {}
    for found in ITEM_ROW.findall(text):
        row = dict(zip(names, found))
        out[int(row["entry"])] = {**row, "name": unquote(row["name"]), "description": unquote(row["description"])}
    return out


def parsed_caches(text):
    return {int(e): unquote(n) for e, n in re.findall(r"^\((101\d\d\d), '((?:[^']|'')*)'\)[,;]$", text, re.M)}


def parsed_pieces(text):
    out = {}
    for cache, item in re.findall(r"^\((101\d\d\d), (\d+)\)[,;]$", text, re.M):
        out.setdefault(int(cache), []).append(int(item))
    return out


def parsed_vendor_rows(text):
    found = re.findall(r"^\((910113), (\d+), (\d+), 0, 0, (\d+), 0\)[,;]$", text, re.M)
    assert all(cost == "0" for _, _, _, cost in found), "a cache row carries an ExtendedCost"
    assert [int(p) for _, p, _, _ in found] == list(range(len(found))), "cache vendor positions run 0.."
    return [int(i) for _, _, i, _ in found]


def parsed_conditions(text):
    return {(int(g), int(e)): int(lv) for g, e, lv in re.findall(
        r"^\(23, (\d+), (\d+), 0, 0, 27, 0, (\d+), 3, 0, 0, 0, 0, '', '[^']*'\)[,;]$", text, re.M)}


def second_computation():
    """{set name: [item entry]} from the APPLIED slot vendor migration, not from the generator's own wear rule."""
    listed = {i for items in slot_test.parsed_lists(slot_test.MIGRATION.read_text(encoding="utf-8")).values() for i in items}
    ids = {r["d3_id"]: int(r["item_entry"]) for r in rows(D3 / "base_item_ids.csv")}
    out = {}
    for r in rows(D3 / "base_items.csv"):
        if r["rarity"] == "set" and ids[r["d3_id"]] in listed:
            out.setdefault(r["set_name"], []).append(ids[r["d3_id"]])
    return out


def test_data():
    text = MIGRATION.read_text(encoding="utf-8")
    check(text == (MODULE / "data/generated" / gen.NAME).read_text(encoding="utf-8"), "the generated mirror and the migration are one file")
    check(text == gen.render(), "the migration is what the generator renders from the sheets")
    want = second_computation()
    sheet = {int(r["entry"]): r["set_name"] for r in rows(D3 / "set_caches.csv")}
    names = slot_test.item_names()
    by_id = {r["d3_id"]: r for r in rows(D3 / "base_items.csv")}
    bases = {int(r["item_entry"]): by_id[r["d3_id"]] for r in rows(D3 / "base_item_ids.csv")}

    caches, pieces, items = parsed_caches(text), parsed_pieces(text), parsed_items(text)
    check(caches == sheet, "dc_set_cache is the sheet")
    check(sorted(caches.values()) == sorted(want), "a cache for every set that has a listed piece, and for no other")
    check(len(caches) == 57 and sum(len(p) for p in pieces.values()) == 283, "57 caches holding 283 pieces")
    for entry, set_name in caches.items():
        got = pieces[entry]
        check(sorted(got) == sorted(want[set_name]), f"{set_name}: the cache holds exactly the set's listed pieces ({len(got)})")
        check(len(got) == len(set(got)), f"{set_name}: no piece twice")
        check(all(bases[i]["set_name"] == set_name and bases[i]["rarity"] == "set" for i in got), f"{set_name}: every piece belongs to the set")
    check(set(pieces) == set(caches), "no piece row for a cache that does not exist")
    check(len(pieces[next(e for e, n in caches.items() if n == "Hallowed Protectors")]) == 7, "Hallowed Protectors holds its 7 listed pieces (the Monk wears Hallowed Hold, the Demon Hunter Hallowed Condemnation, the Witch Doctor Hallowed Sufferance)")
    check(any(bases[i]["craft_only"] == "yes" for p in pieces.values() for i in p), "a Blacksmith-crafted set's pieces are in a cache")
    # Classes: a cache that mixes classes (Hallowed Protectors) still lists only pieces some playable class wears.
    wear = slot_test.applied_wear()
    check(all(wear[i] != 0 for p in pieces.values() for i in p), "no piece is one no playable class can wear")

    # The cache items.
    check(set(items) == set(caches), "one item_template row per cache")
    for entry, set_name in caches.items():
        row, got = items[entry], pieces[entry]
        description = "Contains " + ", ".join(sorted(names[i] for i in got)) + "."
        check(row["name"] == set_name, f"{set_name}: the cache is named after its set")
        check(row["description"] == description and len(description) <= 255, f"{set_name}: the description names every piece ({len(description)} of 255)")
        check((row["class"], row["subclass"], row["InventoryType"], row["Quality"]) == ("15", "0", "0", "2"),
              f"{set_name}: a plain green miscellaneous item")
        check(int(row["Flags"]) & 4 == 4, f"{set_name}: the has-loot flag is set, so the client draws Right Click to Open")
        check((row["BuyPrice"], row["SellPrice"], row["maxcount"], row["bonding"]) == ("0", "0", "0", "0"), f"{set_name}: free, sells for nothing")
    ids = {int(r["item_entry"]) for r in rows(D3 / "base_item_ids.csv")}
    # The caches follow the base items that shipped in 0002; a base item added since (the Shaman's, xnrvn.3) takes the next
    # free entry, after the caches, so it is a base item and never a cache's entry.
    shipped = generate_sql.shipped_entries(D3 / "base_items.csv")
    check(not (set(items) & ids) and ids >= shipped and min(items) > max(shipped) and max(items) < gen.SHELL_ENTRY_BASE,
          "the cache entries follow the base items and stay below the shell block")
    # 101141-101145 are the Horadric Caches (bounties_0003), so the six Monk caches (diablocraft-wna0c) start at 101146;
    # the six Crusader caches (diablocraft-jfd7p) take 101152-101157, the six Necromancer caches (diablocraft-ngybv) 101158-101163
    # the six Demon Hunter caches (diablocraft-vawmy.4) 101164-101169 and the six Witch Doctor caches (diablocraft-jjug3) 101170-101175.
    check(sorted(items) == list(range(101114, 101141)) + list(range(101146, 101176)), "the caches take 101114-101140 and 101146-101175")
    taken = set()
    for path in UPDATES.glob("*.sql"):
        if not path.name.startswith("set_caches_"):
            taken |= {int(m) for m in re.findall(r"\b(1011[1-7][0-9]|910113)\b", path.read_text(encoding="utf-8"))
                      if int(m) > 101113 or int(m) == 910113}
    check(not (taken & (set(items) | {910113})), "the cache and vendor entries are used by no other migration")

    # The client's own reader of migrations (Part 9) reads these rows the way the server table does.
    sys.path.insert(0, str(ROOT / "client-patch/dbc"))
    import build_item
    dbc = build_item.sql_item_rows(MIGRATION)
    check(set(dbc) == set(items), "build_item.py's migration reader finds all the caches")
    check(all(dbc[e][0:2] == (15, 0) and dbc[e][4] == int(items[e]["displayid"]) and dbc[e][5] == 0 for e in items),
          "the Item.dbc row it would write for a cache equals the server row (class, subclass, display, inventory type)")

    # The vendor: caches A to Z, free, gated by the set's level.
    vendor = rows(D3 / "set_cache_vendor.csv")[0]
    listed = parsed_vendor_rows(text)
    check(sorted(listed) == sorted(caches) and [caches[i] for i in listed] == sorted(caches.values()),
          "the vendor lists every cache once, by set name A to Z")
    check([caches[i] for i in listed] == sorted(caches.values(), key=lambda n: (n.casefold(), n)), "case-insensitive A to Z too")
    levels = {e: max((int(bases[i]["item_level"]) if bases[i]["item_level"] else 0) for i in pieces[e]) for e in caches}
    conds = parsed_conditions(text)
    check(conds == {(910113, e): lv for e, lv in levels.items() if lv}, "a level condition per cache whose set has a level, equal to the highest of its pieces, none else")
    check(len(conds) < len(caches), "a set with no level has no condition (it shows from level 1)")
    check(all(levels[e] >= (int(bases[i]["item_level"]) if bases[i]["item_level"] else 0) for e in caches for i in pieces[e]),
          "a cache never hands out a piece the slot vendors hide at that level")
    check(len(listed) <= slot_gen.MAX_VENDOR_ITEMS, "the vendor list is within the core's 150")
    check(vendor["npcflag"] == "128" and vendor["name"] == "Set Caches" and vendor["entry"] == "910113", "the fourteenth vendor, vendor flag only")
    slot_entries = {int(v["entry"]) for v in rows(D3 / "slot_vendors.csv")}
    check(910113 not in slot_entries and "dc_slot_vendor" not in text, "the cache vendor is not a slot vendor, so the slot hook leaves it to the stock purchase")
    # "Leg Guards of Mystery" is a Delsere's piece, so only Kadala's own Mystery items ("Mystery Helm") count.
    check(not re.search(r"910005|blood shard|102007|itemextendedcost|kadala", text, re.I) and not re.search(r"Mystery \w", text),
          "the migration names no Kadala entry, price row, Mystery item or Blood Shard")


def test_refusals():
    def tweak(change):
        with tempfile.TemporaryDirectory(dir=str(SCRATCH.parent) if SCRATCH.parent.exists() else None) as tmp:
            d3 = pathlib.Path(tmp)
            for name in SHEETS:
                shutil.copy(D3 / name, d3 / name)
            change(d3)
            gen.listed(d3)

    def rewrite(d3, name, edit):
        data = rows(d3 / name)
        edit(data)
        with (d3 / name).open("w", newline="", encoding="utf-8") as out:
            w = csv.DictWriter(out, fieldnames=list(data[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(data)

    tweak(lambda d3: None)
    check(True, "the real sheets pass")
    cases = [
        ("a set with a listed piece and no cache", "no cache", lambda d3: rewrite(d3, "set_caches.csv", lambda d: d.pop())),
        ("a cache for a set with no listed piece", "caches for a set with none",
         lambda d3: rewrite(d3, "set_caches.csv", lambda d: d.append({**d[0], "entry": "101200", "set_name": "No Such Set"}))),
        ("a cache entry that is a base item's", "base item",
         lambda d3: rewrite(d3, "set_caches.csv", lambda d: d[0].update(entry="101113"))),
        ("a cache entry twice", "twice", lambda d3: rewrite(d3, "set_caches.csv", lambda d: d[1].update(entry=d[0]["entry"]))),
        ("a cache entry in the shell block", "outside the item range",
         lambda d3: rewrite(d3, "set_caches.csv", lambda d: d[0].update(entry="199900"))),
    ]
    for what, needle, change in cases:
        try:
            tweak(change)
        except ValueError as error:
            check(needle in str(error), "refused: " + what)
        else:
            raise AssertionError("generated: " + what)

    def long_name(d3):
        def edit(data):
            donor = next(b for b in data if b["set_name"] == "Immortal King's Call")
            data.append({**donor, "d3_id": "Planted_1", "d3_name": "X" * 80})
        rewrite(d3, "base_items.csv", edit)
        ids = rows(d3 / "base_item_ids.csv")
        # Past the caches' entries: a base at the next free number after the base items would sit on a cache.
        cache_free = ids + [{"item_entry": str(max(int(r["entry"]) for r in rows(d3 / "set_caches.csv")))}]
        ids.append({"d3_id": "Planted_1", "item_entry": str(max(int(r["item_entry"]) for r in cache_free) + 1)})
        with (d3 / "base_item_ids.csv").open("w", newline="", encoding="utf-8") as out:
            w = csv.DictWriter(out, fieldnames=["d3_id", "item_entry"], lineterminator="\n")
            w.writeheader()
            w.writerows(ids)
    # The planted item is a set piece of an existing set, so it joins that cache and overruns its description.
    try:
        tweak(long_name)
    except ValueError as error:
        check("255" in str(error), "a description over the column's 255 characters is refused")
    else:
        raise AssertionError("an over-long description was generated")


# ---- the rule header -------------------------------------------------------------------------------------------------

def harness_source():
    text = MIGRATION.read_text(encoding="utf-8")
    caches, pieces = parsed_caches(text), parsed_pieces(text)
    ids = {int(r["item_entry"]): r["d3_id"] for r in rows(D3 / "base_item_ids.csv")}
    by_id = {r["d3_id"]: r for r in rows(D3 / "base_items.csv")}
    set_class = {r["set_name"]: r["class_key"] for r in rows(D3 / "set_classes.csv")}
    classes = [r["d3_class"].strip().lower() for r in rows(D3 / "class_map.csv")]
    roll_cases, cache_cases = [], []
    for entry, set_name in sorted(caches.items()):
        cache_cases.append("  {%s, %d}" % (cpp_str(set_name), len(pieces[entry])))
        for item in pieces[entry]:
            b = by_id[ids[item]]
            designated, sclass = b["designated_class"], set_class.get(b["set_name"], "")
            for opener in classes:
                expected = designated or sclass or opener  # 6.5 step 3 for each piece, second statement from the sheets
                roll_cases.append("  {%s, %s, %s, %s}" % tuple(cpp_str(x) for x in (designated, sclass, opener, expected)))
    return r"""
#include "dc_set_cache_rule.h"
#include "dc_slot_vendor_rule.h"
#include "dc_identify_rule.h"
#include <cstdio>
#include <string>
using namespace DC::SetCache;
static int bad = 0;
static void expect(bool ok, const char* what) { if (!ok) { std::printf("FAIL %s\n", what); bad = 1; } }
struct Roll { const char *designated, *setClass, *opener, *expected; };
static const Roll rolls[] = {
@ROLLS@
};
struct Set { const char* name; unsigned pieces; };
static const Set sets[] = {
@SETS@
};
static Facts good(unsigned pieces) {
  Facts f; f.alive = f.rollClassesKnown = true; f.pieces = pieces; f.freeSlots = SlotsNeeded(pieces); return f;
}
int main() {
  // Every piece of every cache, every playable opener: a class's own item or a class set's piece rolls for that class,
  // any other for the opener's (the slot vendors' rule, reused).
  for (const Roll& r : rolls)
    expect(DC::SlotVendor::RollClassFor(r.designated, r.setClass, r.opener) == r.expected, "each piece rolls for its class, else the opener's");

  for (const Set& s : sets) {
    unsigned need = s.pieces - 1;  // the cache's own slot is freed first
    expect(SlotsNeeded(s.pieces) == need, "a set needs one free slot fewer than it has pieces");
    expect(Judge(good(s.pieces)) == Verdict::Open, "exactly the free slots needed opens");
    { Facts f = good(s.pieces); f.freeSlots = 1000; expect(Judge(f) == Verdict::Open, "more than enough opens"); }
    if (need > 0) {
      Facts f = good(s.pieces); f.freeSlots = need - 1;
      expect(Judge(f) == Verdict::BagsShort, "one slot short is refused");
      std::string line = std::string(s.name) + " needs " + std::to_string(need) + " free bag slot" + (need == 1 ? "" : "s") +
                         "; you have " + std::to_string(need - 1) + ".";
      expect(Refusal(Verdict::BagsShort, s.name, s.pieces, need - 1) == line, "the refusal names the set, the slots needed and the slots held");
    }
  }
  expect(Refusal(Verdict::BagsShort, "Immortal King's Call", 7, 2) == "Immortal King's Call needs 6 free bag slots; you have 2.",
         "the plan's own example line (6.1)");
  expect(Refusal(Verdict::BagsShort, "Two", 2, 0) == "Two needs 1 free bag slot; you have 0.", "one slot is singular");
  expect(Judge(good(1)) == Verdict::Open, "a one-piece set opens into the cache's own slot");
  { Facts f = good(1); f.freeSlots = 0; expect(Judge(f) == Verdict::Open, "with no other free slot"); }
  { Facts f = good(3); f.alive = false; expect(Judge(f) == Verdict::Dead, "the dead cannot open"); }
  { Facts f = good(3); f.inCombat = true; expect(Judge(f) == Verdict::InCombat, "no open in combat"); }
  { Facts f = good(3); f.inTrade = true; expect(Judge(f) == Verdict::InTrade, "no open of a cache in a trade"); }
  { Facts f = good(3); f.rollClassesKnown = false; expect(Judge(f) == Verdict::NothingToRoll, "a piece with no roll class is refused"); }
  { Facts f = good(0); expect(Judge(f) == Verdict::NothingToRoll, "an empty cache is refused"); }
  { Facts f = good(3); f.alive = false; f.inCombat = true; f.freeSlots = 0; expect(Judge(f) == Verdict::Dead, "the order: dead first"); }
  { Facts f = good(3); f.inCombat = true; f.inTrade = true; f.freeSlots = 0; expect(Judge(f) == Verdict::InCombat, "combat before the trade"); }
  { Facts f = good(3); f.inTrade = true; f.freeSlots = 0; expect(Judge(f) == Verdict::InTrade, "the trade before the bags"); }
  { Facts f = good(3); f.rollClassesKnown = false; f.freeSlots = 0; expect(Judge(f) == Verdict::NothingToRoll, "the roll class before the bags"); }
  expect(Refusal(Verdict::Open, "x", 3, 3).empty(), "an open has no refusal line");
  for (Verdict v : {Verdict::Dead, Verdict::InCombat, Verdict::InTrade, Verdict::NothingToRoll, Verdict::BagsShort})
    expect(!Refusal(v, "x", 3, 0).empty(), "every refusal says something");

  // One rule with G7 (dc_identify_rule.h): the three conditions it refuses are refused here, and nothing else is
  // refused when the bags and the roll classes are fine.
  for (int mask = 0; mask < 8; ++mask) {
    bool alive = !(mask & 1), combat = mask & 2, trade = mask & 4;
    Facts f = good(3); f.alive = alive; f.inCombat = combat; f.inTrade = trade;
    expect((Judge(f) == Verdict::Open) == (DC::Identify::Refusal(alive, combat, trade) == nullptr), "the cache open and identify refuse the same states");
  }
  return bad;
}
""".replace("@ROLLS@", ",\n".join(roll_cases)).replace("@SETS@", ",\n".join(cache_cases))


# (what it breaks, old text, new text) in the production header; each must turn the harness red.
MUTANTS = [
    ("the cache's own slot is not counted", "return pieces > 0 ? pieces - 1 : 0;", "return pieces;"),
    ("one slot too few is enough", "if (f.freeSlots < SlotsNeeded(f.pieces))", "if (f.freeSlots + 1 < SlotsNeeded(f.pieces))"),
    ("full bags still open", "if (f.freeSlots < SlotsNeeded(f.pieces))", "if (false)"),
    ("the dead still open", "if (!f.alive)", "if (false)"),
    ("combat still opens", "if (f.inCombat)", "if (false)"),
    ("a trade still opens", "if (f.inTrade)", "if (false)"),
    ("no roll class still opens", "if (f.pieces == 0 || !f.rollClassesKnown)", "if (f.pieces == 0)"),
    ("an empty cache still opens", "if (f.pieces == 0 || !f.rollClassesKnown)", "if (!f.rollClassesKnown)"),
    ("bags checked before the trade", "    if (f.inTrade)\n            return Verdict::InTrade;\n", ""),
    ("combat checked before death", "    if (!f.alive)\n            return Verdict::Dead;\n", ""),
    ("the line leaves out the slots needed", "std::to_string(needed)", "std::to_string(pieces)"),
    ("the line leaves out the slots held", "std::to_string(freeSlots)", "std::to_string(needed)"),
    ("the line always says slots", '(needed == 1 ? "" : "s")', '"s"'),
]


def run_harness(header_text):
    try:
        binary = harness_env.build_text(harness_source(), flags=["-std=c++17"], files={
            "dc_set_cache_rule.h": header_text, "dc_slot_vendor_rule.h": SLOT_HEADER.read_text(encoding="utf-8"),
            "dc_identify_rule.h": IDENTIFY_HEADER.read_text(encoding="utf-8"), "dc_roll_class.h": ROLL_CLASS.read_text(encoding="utf-8")})
    except harness_env.BuildError as error:
        raise RuntimeError("harness did not compile:\n" + error.stderr)
    ran = harness_env.run([str(binary)], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout


def test_harness():
    text = HEADER.read_text(encoding="utf-8")
    ok, out = run_harness(text)
    check(ok, "rule header holds against the sheets" + ("" if ok else "\n" + out))
    for what, old, new in MUTANTS:
        survived, _ = run_harness(mutate(text, old, new))
        check(not survived, "mutant killed: " + what)


# ---- the hook's wiring -----------------------------------------------------------------------------------------------

def test_wiring(hook=None, items=None):
    hook = code(HOOK) if hook is None else hook
    items = code(ITEMS) if items is None else items
    entry = hook[hook.index("bool OnPlayerBeforeOpenItem"):]
    entry = squash(entry[:entry.index("void RegisterSetCacheScripts")])
    check("if (!player || !item || !Find(item->GetEntry(), cache)) return true;" in entry,
          "an item that is not a cache is left to the stock open")
    check(entry.index("Open(player, item, cache);") < entry.index("return false;") and entry.endswith("return false; } }; }"),
          "a cache is answered and the stock path is stopped, whatever the open did")
    check(entry.index("return true;") < entry.index("Open(player, item, cache)"), "the stock open is only for non-caches")
    open_ = hook[hook.index("void Open("):hook.index("class SetCacheWorld")]
    order = [open_.index(s) for s in ("SetCache::Judge(facts)", "PlayerEconomy::Scope operation", "Staged guard{player};",
                                      "DestroyWithRows(player, item, transaction)", "StageRoll(", "SaveInventoryAndGoldToDB(transaction)",
                                      "DC::AccountEconomy::Commit(player, transaction)", "guard.committed = true", "->Publish()",
                                      "player->SendNewItem(")]
    check(order == sorted(order), "refusals, the guard, the cache destroyed, every piece staged, one commit, then publish")
    check(open_.count("Commit(") == 1, "one commit")
    check(open_.count("StageRoll(") == 1 and open_.index("for (std::size_t i = 0; i < cache.pieces.size(); ++i)") < open_.index("StageRoll("),
          "every piece is staged, in one loop over the set's pieces")
    check(re.search(r"StageRoll\(player, cache\.pieces\[i\]\.entry, player->GetLevel\(\), \"\", transaction, rollClasses\[i\]\)", open_) is not None,
          "each piece's own base is staged at the opener's level, no rarity forced and no shell (identified)")
    check("SlotVendor::RollClassFor(piece.designated, piece.setClass, buyerClass)" in squash(open_), "the roll class is the slot vendors' rule")
    check("refuse(SetCache::Refusal(verdict, cache.setName, facts.pieces, facts.freeSlots))" in squash(open_), "a refusal says the rule's line")
    check("player->SendLootRelease(guid)" in open_ and open_.index("ObjectGuid const guid = item->GetGUID()") < open_.index("DestroyWithRows("),
          "a refusal gives the client its loot release, with the guid taken before the cache is destroyed")
    check(open_.index("facts.freeSlots = FreeSlotsFor(player, templates)") < open_.index("SetCache::Judge(facts)"), "the free slots are counted before anything changes")
    check("facts.inCombat = player->IsInCombat()" in open_ and "facts.inTrade = item->IsInTrade()" in open_ and "facts.alive = player->IsAlive()" in open_,
          "the states G7 reads")
    check("item = nullptr;" in open_ and open_.index("item = nullptr;") > open_.index("DestroyWithRows("), "the destroyed cache is not used again")
    check(not re.search(r"DebitMaterial|CreditMaterial|MaterialBalance|BloodShards|ExtendedCost|Kadala|kadala|Shell|DeliverShell|dc_item_unidentified", hook),
          "no price, no ledger, no Blood Shard, no shell, nothing of Kadala's")
    check(not re.search(r"(?<![A-Za-z])(_StoreOrEquipNewItem|StoreNewItem|StoreItem|SendLoot)\(", hook), "neither the stock store step nor the stock loot window is used")
    check(not re.search(r"OnPlayerCanSellItem|SellPrice|salvage|Salvage", hook), "the pieces are left to sell and salvage like any drop (6.7.3 not taken)")
    check("RegisterSetCacheScripts();" in items[items.index("void RegisterScripts()"):], "the hook is registered with the item scripts")


WIRING_MUTANTS = [
    ("the stock path is not stopped", "hook", "Open(player, item, cache); return false;", "Open(player, item, cache); return true;"),
    ("every item is taken over", "hook", "if (!player || !item || !Find(item->GetEntry(), cache))", "if (!player || !item)"),
    ("the cache is destroyed after the pieces are staged", "hook", "DestroyWithRows(player, item, transaction);",
     "/*moved*/"),
    ("the guard comes after the destroy", "hook", "Staged guard{player};", "/*late*/"),
    ("a piece is staged as a shell", "hook", 'StageRoll(player, cache.pieces[i].entry, player->GetLevel(), "", transaction, rollClasses[i])',
     'DeliverShell(player, cache.pieces[i].entry, player->GetLevel(), "set", 1, "x", 1, rollClasses[i])'),
    ("the roll class is the opener's", "hook", "SlotVendor::RollClassFor(piece.designated, piece.setClass, buyerClass)", "buyerClass"),
    ("a refusal leaves the cache locked", "hook", "player->SendLootRelease(guid);", ";"),
    ("the free slots are not read", "hook", "facts.freeSlots = FreeSlotsFor(player, templates);", "facts.freeSlots = 1000;"),
    ("combat is not read", "hook", "facts.inCombat = player->IsInCombat();", "facts.inCombat = false;"),
    ("the stock loot window opens", "hook", "Open(player, item, cache); return false;", "Open(player, item, cache); player->SendLoot(item->GetGUID(), LOOT_CORPSE); return false;"),
    ("a price is charged", "hook", "Staged guard{player};", "Staged guard{player}; DC::AccountEconomy::DebitMaterial(player, 1, 1);"),
    ("the hook is not registered", "items", "RegisterSetCacheScripts();", ""),
]


def test_wiring_mutants():
    for what, which, old, new in WIRING_MUTANTS:
        hook, items = code(HOOK), code(ITEMS)
        source = hook if which == "hook" else items
        if what == "the cache is destroyed after the pieces are staged":
            # Move the destroy to just before the save: staged first, destroyed after.
            source = source.replace(old, "/*moved*/", 1).replace("player->SaveInventoryAndGoldToDB(transaction);",
                                                                  "DestroyWithRows(player, item, transaction); player->SaveInventoryAndGoldToDB(transaction);", 1)
        elif what == "the guard comes after the destroy":
            source = source.replace(old, "/*late*/", 1).replace("DestroyWithRows(player, item, transaction);",
                                                               "DestroyWithRows(player, item, transaction); Staged guard{player};", 1)
        else:
            source = mutate(source, old, new)
        try:
            test_wiring(source, items) if which == "hook" else test_wiring(hook, source)
        except (AssertionError, ValueError, IndexError):
            print("PASS wiring mutant killed: " + what, flush=True)
            continue
        raise AssertionError("wiring mutant survived: " + what)


# ---- the free-slot count (diablocraft-wuvw) -------------------------------------------------------------------------
#
# The module's FreeSlotsFor, the core's own ItemCanGoIntoBag and its enums, and the rule header, compiled as they are.
# A full backpack whose only room is a herb bag, a quiver or an ammo pouch counts no room for armour, so the cache refuses
# with its line instead of failing the store after the destroy (which kicked the player). The old count
# (GetFreeInventorySpace: every free slot of every bag) passed it.

CORE_GAME = ROOT / "azerothcore-wotlk/src/server/game"


def braced(text, marker, end="}"):
    start = text.index(marker)
    at = text.index("{", start) + 1
    depth = 1
    while depth:
        depth += (text[at] == "{") - (text[at] == "}")
        at += 1
    return text[start:at] + (";" if end == "};" else "")


FREE_DOUBLES = r"""
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>
typedef std::uint8_t uint8; typedef std::uint32_t uint32;
#define INVENTORY_SLOT_BAG_0 255
struct ItemTemplate { uint32 Class = 0, SubClass = 0, BagFamily = 0; };
struct Item {};
struct Bag : Item { ItemTemplate proto; uint32 free = 0; ItemTemplate const* GetTemplate() const { return &proto; } uint32 GetFreeSlots() const { return free; } };
"""

FREE_PLAYER = r"""
struct Player {
    std::vector<bool> packUsed = std::vector<bool>(16, true); std::vector<Bag*> bags = std::vector<Bag*>(4, nullptr); Item used;
    Item* GetItemByPos(uint8 bag, uint8 slot) { assert(bag == INVENTORY_SLOT_BAG_0); return packUsed.at(slot - INVENTORY_SLOT_ITEM_START) ? &used : nullptr; }
    Bag* GetBagByPos(uint8 slot) { return bags.at(slot - INVENTORY_SLOT_BAG_START); }
};
"""

FREE_MAIN = r"""
using namespace DC::Items;
int main() {
    ItemTemplate armour; armour.Class = ITEM_CLASS_ARMOR;            // a set piece: armour, no bag family
    std::vector<ItemTemplate const*> pieces{&armour, &armour, &armour};
    auto bag = [](uint32 cls, uint32 sub, uint32 free) { Bag* b = new Bag; b->proto.Class = cls; b->proto.SubClass = sub; b->free = free; return b; };
    Player p;
    p.bags[0] = bag(ITEM_CLASS_CONTAINER, ITEM_SUBCLASS_CONTAINER, 0);
    p.bags[1] = bag(ITEM_CLASS_CONTAINER, ITEM_SUBCLASS_HERB_CONTAINER, 6);
    p.bags[2] = bag(ITEM_CLASS_QUIVER, ITEM_SUBCLASS_QUIVER, 4);
    p.bags[3] = bag(ITEM_CLASS_QUIVER, ITEM_SUBCLASS_AMMO_POUCH, 2);
    std::cout << "SPECIAL_ONLY " << FreeSlotsFor(&p, pieces) << "\n";
    DC::SetCache::Facts f; f.alive = true; f.rollClassesKnown = true; f.pieces = 3; f.freeSlots = FreeSlotsFor(&p, pieces);
    std::cout << "VERDICT " << (DC::SetCache::Judge(f) == DC::SetCache::Verdict::BagsShort ? "BagsShort" : "other") << "\n";
    std::cout << "LINE " << DC::SetCache::Refusal(DC::SetCache::Judge(f), "Aughild's Victory", 3, f.freeSlots) << "\n";
    p.bags[0]->free = 3; p.packUsed[5] = false;                         // generic room: the bag and the backpack count
    std::cout << "GENERIC " << FreeSlotsFor(&p, pieces) << "\n";
    ItemTemplate gem; gem.Class = ITEM_CLASS_GEM; gem.BagFamily = BAG_FAMILY_MASK_GEMS;   // a bag must take EVERY piece
    Player q; q.bags[0] = bag(ITEM_CLASS_CONTAINER, ITEM_SUBCLASS_GEM_CONTAINER, 5);
    std::cout << "MIXED " << FreeSlotsFor(&q, {&gem, &armour}) << " " << FreeSlotsFor(&q, {&gem}) << "\n";
}
"""


def free_slots_source(hook_text=None, rule_text=None):
    item_cpp = (CORE_GAME / "Entities/Item/Item.cpp").read_text(encoding="utf-8")
    template_h = (CORE_GAME / "Entities/Item/ItemTemplate.h").read_text(encoding="utf-8")
    player_h = (CORE_GAME / "Entities/Player/Player.h").read_text(encoding="utf-8")
    enums = "\n".join(braced(template_h, "enum " + name, "};") for name in
                      ("BAG_FAMILY_MASK", "ItemClass\n", "ItemSubclassContainer", "ItemSubclassQuiver"))
    slots = "\n".join(braced(player_h, "enum " + name, "};") for name in ("InventorySlots", "InventoryPackSlots"))
    hook = hook_text if hook_text is not None else HOOK.read_text(encoding="utf-8")
    rule = rule_text if rule_text is not None else HEADER.read_text(encoding="utf-8")
    rule = rule[rule.index("namespace DC::SetCache"):rule.rindex("#endif")]
    return (FREE_DOUBLES + enums + "\n" + slots + "\n" + FREE_PLAYER + braced(item_cpp, "bool ItemCanGoIntoBag(ItemTemplate const* pProto")
            + "\n#include <string>\n" + rule + "\nnamespace DC::Items {\n" + braced(hook, "unsigned FreeSlotsFor(") + "\n}\n" + FREE_MAIN)


def run_free_slots(source):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    folder = pathlib.Path(tempfile.mkdtemp(prefix="free-", dir=SCRATCH))
    try:
        (folder / "free.cpp").write_text(source, encoding="utf-8")
        built = subprocess.run(["c++", "-std=c++17", "-o", str(folder / "free"), str(folder / "free.cpp")], capture_output=True, text=True)
        if built.returncode:
            raise AssertionError("the free-slot harness did not compile:\n" + built.stderr[-3000:])
        out = harness_env.run([str(folder / "free")], capture_output=True, text=True, check=True).stdout
        return dict(re.findall(r"^(\w+) (.*)$", out, re.M))
    finally:
        shutil.rmtree(folder)


def test_free_slots(hook_text=None):
    got = run_free_slots(free_slots_source(hook_text))
    check(got["SPECIAL_ONLY"] == "0", "a herb bag, a quiver and an ammo pouch hold no room for set pieces")
    check(got["VERDICT"] == "BagsShort", "so the cache refuses before anything is destroyed")
    check(got["LINE"].endswith("; you have 0."), "with the free-slot line, not a kick")
    check(got["GENERIC"] == "4", "a generic bag's room and the backpack's count")
    check(got["MIXED"] == "0 5", "a special bag counts only when it takes every piece")
    text = hook_text if hook_text is not None else HOOK.read_text(encoding="utf-8")
    hook = "\n".join(line.split("//")[0] for line in text.splitlines()
                     if not line.strip().startswith(("//", "/*", "* ", "*/")))
    check("facts.freeSlots = FreeSlotsFor(player, templates);" in hook and "GetFreeInventorySpace" not in hook,
          "the open hook reads the new count, never the old one")


def test_free_slots_mutants():
    hook = HOOK.read_text(encoding="utf-8")
    for what, old, new in (
            ("every bag counted (the old count)", "if (std::all_of(pieces.begin(), pieces.end(),", "if (true || std::all_of(pieces.begin(), pieces.end(),"),
            ("one piece decides", "std::all_of(pieces.begin(), pieces.end(),", "std::any_of(pieces.begin(), pieces.end(),"),
            ("backpack ignored", "                    ++free;\n", "                    ;\n"),
            ("hook reads the old count", "facts.freeSlots = FreeSlotsFor(player, templates);", "facts.freeSlots = player->GetFreeInventorySpace();")):
        try:
            test_free_slots(mutate(hook, old, new) if what != "hook reads the old count" else hook.replace(old, new))
        except AssertionError:
            print("PASS free-slot mutant killed: " + what, flush=True)
            continue
        raise AssertionError("free-slot mutant survived: " + what)


# ---- the replay ------------------------------------------------------------------------------------------------------

STUB = slot_test.STUB + """
CREATE TABLE item_template (entry INT UNSIGNED PRIMARY KEY, class TINYINT UNSIGNED, subclass TINYINT UNSIGNED,
  name VARCHAR(255) CHARACTER SET utf8mb4, displayid INT UNSIGNED, Quality TINYINT UNSIGNED, Flags INT UNSIGNED,
  BuyCount TINYINT UNSIGNED, BuyPrice BIGINT, SellPrice INT UNSIGNED, InventoryType TINYINT UNSIGNED, maxcount INT,
  stackable INT, BagFamily INT UNSIGNED, Material TINYINT, bonding TINYINT UNSIGNED, ItemLevel SMALLINT UNSIGNED,
  description VARCHAR(255) CHARACTER SET utf8mb4);
"""


def test_mysql(port):
    command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
               "--batch", "--raw", "--skip-column-names", "--default-character-set=utf8mb4"]

    def sql(text, database=None):
        done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True,
                              capture_output=True, encoding="utf-8")
        if done.returncode:
            raise RuntimeError(done.stderr)
        return done.stdout.rstrip("\n")

    text = MIGRATION.read_text(encoding="utf-8")
    sql("CREATE DATABASE set_caches CHARACTER SET utf8mb4;")
    sql(STUB, "set_caches")
    sql(text, "set_caches")
    sql(text, "set_caches")
    caches, pieces = parsed_caches(text), parsed_pieces(text)
    check(sql("SELECT COUNT(*) FROM dc_set_cache", "set_caches") == str(len(caches)), "twice applied: the caches read back")
    check(sql("SELECT COUNT(*) FROM dc_set_cache_piece", "set_caches") == str(sum(len(p) for p in pieces.values())), "twice applied: the pieces read back")
    got = {int(e): n for e, n in (l.split("\t") for l in sql("SELECT entry, name FROM item_template ORDER BY entry", "set_caches").splitlines())}
    check(got == caches, "the item rows read back are the sets' names")
    check(sql("SELECT MAX(CHAR_LENGTH(description)), MIN(Flags & 4), MAX(SellPrice), MAX(BuyPrice) FROM item_template", "set_caches").split("\t")[1:] == ["4", "0", "0"],
          "the has-loot flag set and no price, read back")
    check(int(sql("SELECT MAX(CHAR_LENGTH(description)) FROM item_template", "set_caches")) <= 255, "the longest description fits the real column")
    check([int(i) for i in sql("SELECT item FROM npc_vendor WHERE entry=910113 ORDER BY slot", "set_caches").splitlines()] == parsed_vendor_rows(text),
          "the npc_vendor rows read back are the vendor's list")
    check(sql("SELECT COUNT(*) FROM conditions WHERE SourceTypeOrReferenceId=23 AND SourceGroup=910113", "set_caches") == str(len(parsed_conditions(text))),
          "the level conditions read back")
    vendor = rows(D3 / "set_cache_vendor.csv")[0]
    check(sql("SELECT entry, name, subname, minlevel, npcflag, gossip_menu_id, ScriptName, AIName FROM creature_template WHERE entry=910113", "set_caches")
          == "\t".join((vendor["entry"], vendor["name"], "", vendor["level"], vendor["npcflag"], "0", "", "")),
          "twice applied: one vendor creature, vendor flag only, no gossip, no script")
    check(sql("SELECT COUNT(*) FROM creature_template_model WHERE CreatureID=910113", "set_caches") == "1", "it has its model")
    for name, cut in (("npc_vendor", r"^DELETE FROM `npc_vendor`.*$"), ("item_template", r"^DELETE FROM `item_template`.*$")):
        sql(f"CREATE DATABASE mutant_{name} CHARACTER SET utf8mb4;")
        sql(STUB, f"mutant_{name}")
        mutant = re.sub(cut, "", text, count=1, flags=re.M)
        check(mutant != text, f"the mutant removed the {name} DELETE")
        sql(mutant, f"mutant_{name}")
        try:
            sql(mutant, f"mutant_{name}")
        except RuntimeError:
            check(True, f"mutant killed: without its {name} DELETE the migration does not replay")
        else:
            raise AssertionError(f"a migration that keeps its old {name} rows replayed")
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_data()
    test_refusals()
    test_harness()
    test_wiring()
    test_wiring_mutants()
    test_free_slots()
    test_free_slots_mutants()
    isolated(test_mysql)
