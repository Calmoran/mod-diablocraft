"""diablocraft-aeo7 - Kadala part 5, the purchase: the rule header executed, the hook's wiring read, the entry table replayed.

What this proves, and what it does not:

  * The production header `src/loot/dc_kadala_rule.h` (the hook's decisions) is compiled into a harness and driven with
    the SHEETS' values, never a literal: each vendor row's price comes from the ExtendedCost row the newest Kadala migration (`generate_kadala.NAME`)
    writes and is compared with `kadala.csv`; the legendary chance is the `loot.csv` tunable, cross-checked against
    `kadala.csv`; the slot filter is run over `base_items.csv` with the production `dc_roll_class.h`, so a Wizard's
    Mystery Source rolls only Sources, a Barbarian's rolls nothing, and so on for every entry and every playable class.
    Every rule has a mutant of the header that must turn the harness red.
  * The hook's WIRING (`dc_kadala.cpp`, `dc_loot.cpp`) is checked by reading the code with comments removed: the
    take-over only for the entries, the price only from the server's ExtendedCost row, every refusal before the first
    mutation, the stage before the debit before the commit before the publish, the item staged identified (no shell), no
    drop path given a filter. It is NOT executed: that needs a Player, a vendor and a running ledger, which is the GM
    script in docs/test-diablocraft-aeo7.md.
  * `kadala_0002_entries.sql` is replayed twice on a disposable MySQL and read back against `kadala_entries.csv`.
"""
import csv
import pathlib
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_kadala
from class_names import item_key
import harness_env
from test_account_economy_sql import MYSQL, ROOT, isolated

MODULE = ROOT / "mod-diablocraft"
D3 = MODULE / "data/d3"
SRC = MODULE / "src"
HEADER = SRC / "loot/dc_kadala_rule.h"
HOOK = SRC / "loot/dc_kadala.cpp"
LOOT = SRC / "loot/dc_loot.cpp"
DELIVERY = SRC / "loot/dc_loot_delivery.cpp"   # R4: FirstBossKill, a drop that calls PickBaseItem, moved here
ROLL_CLASS = SRC / "items/dc_roll_class.h"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/kadala_purchase_test"
SHARD = 102007
# Classes in class_map.csv that have no weapon bases yet, so a weapon entry has nothing for them to roll. None now: the Shaman's
# Ritual Mace and Totem and her usable_by entries are diablocraft-xnrvn.3 (Shaman 1b). A class added to the sheet before its
# bases are is named here, and the test below fails if a listed class gains a weapon base, so its entry goes with them.
AWAITING_BASES = ()


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def check(ok, name):
    if not ok:
        raise AssertionError(name)
    print("PASS " + name, flush=True)


def code(path):
    """Source with comments removed, so prose cannot satisfy a wiring check."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(("//", "/*", "* ", "*/")):
            continue
        lines.append(line.split("//")[0])
    return "\n".join(lines)


def loot_code():
    """dc_loot.cpp then dc_loot_delivery.cpp, comments removed."""
    return code(LOOT) + "\n" + code(DELIVERY)


def tunable(name):
    row = next(r for r in rows(MODULE / "data/tunables/loot.csv") if r["name"] == name)
    return float(row["value"] or row["d3_value"])


def sheet_data():
    """Everything the harness is driven with, read from the sheets."""
    entries = rows(D3 / "kadala_entries.csv")
    rules = {r["rule"]: r["value"] for r in rows(D3 / "kadala.csv")}
    price = {e["item_entry"]: int(re.match(r"(\d+) Blood Shards", rules[e["cost_rule"]]).group(1)) for e in entries}
    vendor = (MODULE / "data/sql/db-world/updates" / generate_kadala.NAME).read_text(encoding="utf-8")
    costs = {}
    for m in re.finditer(r"^\((\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+), (\d+)\)[,;]$",
                         vendor, re.M):
        v = [int(x) for x in m.groups()]
        if v[0] >= 3000:
            costs[v[0]] = v
    listed = [(int(a), int(b), int(c)) for a, b, c in
              re.findall(r"^\(910005, (\d+), (\d+), 0, 0, (\d+), 0\)[,;]$", vendor, re.M)]
    classes = [item_key(r["d3_class"]) for r in rows(D3 / "class_map.csv")]
    bases = [r for r in rows(D3 / "base_items.csv") if not r["rarity"]]
    return entries, price, costs, listed, classes, bases


def squash(text):
    return " ".join(text.split())


def cpp_str(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def harness_source():
    entries, price, costs, listed, classes, bases = sheet_data()
    pct = tunable("kadala_legendary_pct")
    lines = []
    # vendor rows: (item, cost row fields..., expected price)
    vendor_rows = ",\n".join(
        "  {%d, {%s}, {%s}, %d, %d, %d, %d}" % (item, ",".join(map(str, costs[cost][4:9])), ",".join(map(str, costs[cost][9:14])),
                                                 costs[cost][1], costs[cost][2], costs[cost][14], price[str(item)])
        for _, item, cost in listed)
    entry_rows = ",\n".join("  {%d, %s, %s}" % (int(e["item_entry"]), cpp_str(e["slot"]), cpp_str(e["base_types"])) for e in entries)
    base_rows = ",\n".join("  {%s, %s, %s, %s}" % tuple(cpp_str(b[k]) for k in ("slot", "type", "usable_by", "designated_class"))
                           for b in bases)
    class_rows = ", ".join(cpp_str(c) for c in classes)
    awaiting_rows = ", ".join(cpp_str(c) for c in AWAITING_BASES)
    return r"""
#include "dc_kadala_rule.h"
#include "dc_roll_class.h"
#include <cstdio>
#include <cstdlib>
using namespace DC::Kadala;
static int bad = 0;
static void expect(bool ok, const char* what) { if (!ok) { std::printf("FAIL %s\n", what); bad = 1; } }
struct VendorRow { std::uint32_t item; std::uint32_t reqitem[5], reqcount[5]; std::uint32_t honor, arena, rating, price; };
struct EntryRow { std::uint32_t item; const char* slot; const char* types; };
struct BaseRow { const char *slot, *type, *usable, *designated; };
static const VendorRow vendor[] = {
@VENDOR@
};
static const EntryRow entries[] = {
@ENTRIES@
};
static const BaseRow bases[] = {
@BASES@
};
static const char* classes[] = { @CLASSES@ };
static const char* awaitingBases[] = { @AWAITING@ };
static const double LEGENDARY_PCT = @PCT@;
static const std::uint32_t SHARD = @SHARD@;

static Facts good() {
  Facts f; f.alive = f.inReach = f.onList = f.classAllowed = f.priced = f.rolled = f.bagFree = true;
  f.count = 1; f.price = 25; f.held = 25; return f;
}
int main() {
  // The price is the server's ExtendedCost row: every vendor row charges the sheet's price, in shards only.
  for (const VendorRow& v : vendor) {
    CostRow row; for (int i = 0; i < 5; ++i) { row.item[i] = v.reqitem[i]; row.count[i] = v.reqcount[i]; }
    row.honor = v.honor; row.arena = v.arena; row.arenaRating = v.rating;
    std::uint64_t p = 0;
    expect(ShardPrice(row, SHARD, p) && p == v.price, "a vendor row is charged the sheet's price in Blood Shards");
  }
  { CostRow r; r.item[0] = SHARD; r.count[0] = 25; std::uint64_t p = 0;
    expect(ShardPrice(r, SHARD, p) && p == 25, "plain price");
    r.item[1] = SHARD; r.count[1] = 5; expect(ShardPrice(r, SHARD, p) && p == 30, "two shard lines add up");
    CostRow h = r; h.honor = 1; expect(!ShardPrice(h, SHARD, p), "honor on the row is not a Blood Shard price");
    CostRow a = r; a.arena = 1; expect(!ShardPrice(a, SHARD, p), "arena points on the row are refused");
    CostRow g = r; g.arenaRating = 1; expect(!ShardPrice(g, SHARD, p), "an arena rating on the row is refused");
    CostRow o = r; o.item[2] = SHARD + 1; o.count[2] = 1; expect(!ShardPrice(o, SHARD, p), "another item on the row is refused");
    CostRow z; z.item[0] = SHARD; z.count[0] = 0; expect(!ShardPrice(z, SHARD, p), "a free row is not a price");
    CostRow e; expect(!ShardPrice(e, SHARD, p), "an empty row is not a price"); }

  // The judgement: the first refusal wins, a refusal charges nothing (the hook stages and debits only on Buy).
  expect(Judge(good()) == Verdict::Buy, "everything in order buys");
  { Facts f = good(); f.held = 24; expect(Judge(f) == Verdict::TooFewShards, "one shard short is refused"); }
  { Facts f = good(); f.held = 25; f.price = 25; expect(Judge(f) == Verdict::Buy, "exactly the price buys"); }
  { Facts f = good(); f.held = 0; expect(Judge(f) == Verdict::TooFewShards, "no shards"); }
  { Facts f = good(); f.bagFree = false; expect(Judge(f) == Verdict::BagsFull, "full bags are refused"); }
  { Facts f = good(); f.classAllowed = false; expect(Judge(f) == Verdict::WrongClass, "a class entry is refused to another class"); }
  { Facts f = good(); f.count = 2; expect(Judge(f) == Verdict::BadCount, "a count above one is refused"); }
  { Facts f = good(); f.count = 0; expect(Judge(f) == Verdict::BadCount, "a count of zero is refused"); }
  { Facts f = good(); f.alive = false; expect(Judge(f) == Verdict::Dead, "the dead cannot buy"); }
  { Facts f = good(); f.inReach = false; expect(Judge(f) == Verdict::TooFar, "out of reach is refused"); }
  { Facts f = good(); f.onList = false; expect(Judge(f) == Verdict::NotListed, "an entry not at that position is refused"); }
  { Facts f = good(); f.priced = false; expect(Judge(f) == Verdict::NoPrice, "no server price is refused"); }
  { Facts f = good(); f.rolled = false; expect(Judge(f) == Verdict::NothingToRoll, "nothing to roll is refused"); }
  { Facts f = good(); f.alive = false; f.held = 0; expect(Judge(f) == Verdict::Dead, "the stock order: dead first"); }
  { Facts f = good(); f.held = 0; f.bagFree = false; expect(Judge(f) == Verdict::TooFewShards, "shards before bags"); }

  // The legendary chance: a flat tunable, the boundary exclusive.
  expect(RollsLegendary(LEGENDARY_PCT, 0.0), "roll 0 is legendary");
  expect(RollsLegendary(LEGENDARY_PCT, LEGENDARY_PCT / 100.0 - 0.0001), "just under the chance is legendary");
  expect(!RollsLegendary(LEGENDARY_PCT, LEGENDARY_PCT / 100.0), "exactly the chance is not");
  expect(!RollsLegendary(LEGENDARY_PCT, 0.9999), "high roll is not");
  expect(!RollsLegendary(0, 0.0), "chance 0 never");
  expect(RollsLegendary(100, 0.9999), "chance 100 always");
  { int hits = 0; for (int i = 0; i < 100000; ++i) hits += RollsLegendary(LEGENDARY_PCT, i / 100000.0);
    expect(std::abs(hits - 1000 * (int)LEGENDARY_PCT) <= 1, "one in ten over an even sweep"); }

  // The slot filter against base_items.csv with the production roll-class rules: what each entry can roll, per class.
  for (const EntryRow& e : entries) {
    SlotFilter filter{e.slot, SplitTypes(e.types)};
    for (const char* cls : classes) {
      int eligible = 0, wrongSlot = 0, wrongKind = 0;
      for (const BaseRow& b : bases) {
        bool admitted = filter.Admits(b.slot, b.type);
        bool wearable = DC::RollClass::DropEligible(b.usable, b.designated, "", cls);
        if (admitted && wearable) {
          ++eligible;
          if (std::string(b.slot) != e.slot) ++wrongSlot;
          if (*e.types && !filter.Admits(e.slot, b.type)) ++wrongKind;
        }
      }
      expect(wrongSlot == 0 && wrongKind == 0, "a filtered roll stays in the entry's slot and kinds");
      // Cross-source: a class sees an entry exactly when some base of its kind is usable by that class.
      int expected = 0;
      for (const BaseRow& b : bases) {
        bool kind = std::string(b.slot) == e.slot &&
                    (!*e.types || (std::string(";") + e.types + ";").find(std::string(";") + b.type + ";") != std::string::npos);
        std::string usable = std::string(";") + b.usable + ";";
        bool classOk = !*b.usable || usable.find(std::string(";") + cls + ";") != std::string::npos;
        bool own = !*b.designated || std::string(b.designated) == cls;
        if (kind && classOk && own) ++expected;
      }
      expect(eligible == expected, "the roll pool is the sheet's: same bases the class can wear");
      bool awaiting = false;
      for (const char* waiting : awaitingBases) if (std::string(waiting) == cls) awaiting = true;
      if (std::string(e.slot) != "offhand" && !awaiting) expect(eligible > 0, "every non-offhand entry has a base for every class");
    }
  }
  return bad;
}
""".replace("@VENDOR@", vendor_rows).replace("@ENTRIES@", entry_rows).replace("@BASES@", base_rows) \
       .replace("@CLASSES@", class_rows).replace("@AWAITING@", awaiting_rows).replace("@PCT@", repr(pct)).replace("@SHARD@", str(SHARD))


# (what it breaks, old text, new text) in the production header; each must turn the harness red.
MUTANTS = [
    ("price ignores honor", "if (row.honor || row.arena || row.arenaRating)", "if (row.arena || row.arenaRating)"),
    ("price ignores arena points", "if (row.honor || row.arena || row.arenaRating)", "if (row.honor || row.arenaRating)"),
    ("price ignores an arena rating", "if (row.honor || row.arena || row.arenaRating)", "if (row.honor || row.arena)"),
    ("price accepts another item", "if (row.item[i] != shardEntry)\n            return false;", ""),
    ("price takes only the last shard line", "total += row.count[i];", "total = row.count[i];"),
    ("a free row is a price", "return total > 0;", "return true;"),
    ("too few shards still buys", "if (f.held < f.price)", "if (false)"),
    ("one shard short still buys", "if (f.held < f.price)", "if (f.held + 1 < f.price)"),
    ("a count above one is allowed", "if (f.count != 1)", "if (f.count < 1)"),
    ("a count of zero is allowed", "if (f.count != 1)", "if (f.count > 1)"),
    ("full bags still buy", "if (!f.bagFree)", "if (false)"),
    ("the wrong class still buys", "if (!f.classAllowed)", "if (false)"),
    ("an unlisted position still buys", "if (!f.onList)", "if (false)"),
    ("out of reach still buys", "if (!f.inReach)", "if (false)"),
    ("the dead still buy", "if (!f.alive)", "if (false)"),
    ("no price still buys", "if (!f.priced)", "if (false)"),
    ("nothing rolled still buys", "if (!f.rolled)", "if (false)"),
    ("bags checked before shards", "    if (f.held < f.price)\n        return Verdict::TooFewShards;\n", ""),
    ("legendary boundary inclusive", "roll * 100.0 < legendaryPct", "roll * 100.0 <= legendaryPct"),
    ("legendary never", "roll * 100.0 < legendaryPct", "false"),
    ("filter ignores the slot", "if (baseSlot != slot)\n            return false;", ""),
    ("filter ignores the kinds", "if (types.empty())\n            return true;", "return true;"),
    ("a named kind admits any other", "if (type == baseType)", "if (type != baseType)"),
]


def mutate(text, old, new):
    """Replace the one place `old` appears, whatever the formatter did to the whitespace around it."""
    pattern = re.compile(r"\s+".join(re.escape(token) for token in old.split()))
    assert len(pattern.findall(text)) == 1, "mutant target moved: " + old
    return pattern.sub(lambda _: new, text)


def run_harness(header_text):
    # the cached compile: the same header text and harness are the same binary (the green run repeats once per mutant)
    try:
        binary = harness_env.build_text(harness_source(), flags=["-std=c++17"],
                                        files={"dc_kadala_rule.h": header_text, "dc_roll_class.h": ROLL_CLASS.read_text(encoding="utf-8")})
    except harness_env.BuildError as error:
        raise RuntimeError("harness did not compile:\n" + error.stderr)
    ran = harness_env.run([str(binary)], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout


def test_data():
    d3 = {r["rule"]: r["value"] for r in rows(D3 / "kadala.csv")}
    check(tunable("kadala_legendary_pct") == float(d3["legendary_gamble_chance"].rstrip("%")), "the chance is kadala.csv's 10%")
    entries, price, costs, listed, classes, bases = sheet_data()
    check(len(listed) == len(entries) == 17 and [i for _, i, _ in listed] == [int(e["item_entry"]) for e in entries],
          "her list is the sheet's entries in order")
    check({p for p in price.values()} == {25, 50, 75, 100}, "the sheet's four prices")
    check(classes == ["barbarian", "wizard", "monk", "crusader", "necromancer", "demonhunter", "witchdoctor", "shaman"], "the playable classes are read from class_map.csv")
    for key in AWAITING_BASES:
        weapons = [b for b in bases if b["slot"] in ("onehand", "twohand") and b["pool_version"] == "yes"
                   and (key in b["usable_by"].split(";") or b["designated_class"] == key)]
        check(key in classes and not weapons, f"{key} is awaiting its weapon bases (xnrvn.3) and has none; drop it from AWAITING_BASES once it has")
    # Every entry names a slot and kinds base_items.csv really has.
    for e in entries:
        wanted = [t for t in e["base_types"].split(";") if t]
        kinds = {b["type"] for b in bases if b["slot"] == e["slot"]}
        check(kinds and set(wanted) <= kinds, f"{e['name']}: slot {e['slot']} and kinds {wanted or 'any'} exist in base_items.csv")


def test_harness():
    ok, out = run_harness(HEADER.read_text(encoding="utf-8"))
    check(ok, "rule header holds against the sheets" + ("" if ok else "\n" + out))
    text = HEADER.read_text(encoding="utf-8")
    for what, old, new in MUTANTS:
        survived, _ = run_harness(mutate(text, old, new))
        check(not survived, "mutant killed: " + what)


def test_wiring(hook=None, loot=None):
    hook = code(HOOK) if hook is None else hook
    loot = loot_code() if loot is None else loot
    check("sItemExtendedCostStore.LookupEntry(listed->ExtendedCost)" in hook and "Kadala::ShardPrice(cost," in hook and
          len(re.findall(r"facts\.price\s*=", hook)) == 0 and "Kadala::ShardPrice(cost, BloodShards::Entry, facts.price)" in hook,
          "the price is read from the server's ExtendedCost row and only there")
    check(not re.search(r"(?<![.\w])count\b", re.search(r"Kadala::CostRow cost;.*?facts\.priced = [^;]*;", hook, re.S).group(0)),
          "the client's count never reaches the price")
    take_over = hook[hook.index("void OnPlayerBeforeBuyItemFromVendor"):]
    check(take_over.index("FilterOf(item)") < take_over.index("item = 0") < take_over.index("Buy(player"),
          "the hook takes over (item = 0) only for an item in dc_kadala_entry, then runs the purchase")
    check("if (!player || !filter) return;" in squash(take_over),
          "any other item is left to the stock path")
    buy = hook[hook.index("void Buy("):hook.index("class KadalaWorld")]
    order = [buy.index(s) for s in ("Kadala::Judge(facts)", "PlayerEconomy::Scope operation", "DC::Items::StageRoll(",
                                    "DC::AccountEconomy::DebitMaterial(", "SaveInventoryAndGoldToDB(transaction)",
                                    "DC::AccountEconomy::Commit(player, transaction)", "guard.committed = true",
                                    "staged->Publish()", "player->SendNewItem(")]
    check(order == sorted(order), "refusals, then stage, debit, one commit, then publish and the confirmation")
    check(buy.count("DebitMaterial(") == 1 and buy.count("Commit(") == 1, "one debit and one commit")
    check(re.search(r"StageRoll\(player, base, level, \"\", transaction, rollClass,\s+DC::Items::RollQuality\(player, base, level, 0, true\)\)", buy) is not None,
          "the item is staged by the roller with no rarity forced and no shell (a legendary arrives identified), its quality decided as a gamble (level gate only)")
    check(not re.search(r"Shell|IdentifyItemSpell|dc_item_unidentified|DeliverShell", hook), "no shell anywhere in the purchase")
    check(not re.search(r"(?<![A-Za-z])(_StoreOrEquipNewItem|StoreNewItem|StoreItem)\(", hook), "the stock store step is never used")
    check("ClassKeyOf(player->getClass())" in buy, "the roll class is the buyer's")
    check("PickGamble(filter, level, rollClass, DC::Tunables::Get(\"loot\", \"kadala_legendary_pct\"))" in squash(buy),
          "the gamble rolls at the buyer's level and class with the tunable chance")
    check("Staged guard{player};" in buy and buy.index("Staged guard") > buy.index("StageRoll(") and
          buy.index("Staged guard") < buy.index("DebitMaterial("), "a failure after the stage fails the whole operation")
    check(buy.index("CanStoreNewItem(") < buy.index("Kadala::Judge(facts)"), "the bag cell is checked before anything is staged")
    # The roller: one more argument on PickBaseItem, no second roller, drops untouched.
    pick = loot[loot.index("std::uint32_t PickBaseItem("):loot.index("namespace Detail\n{", loot.index("std::uint32_t PickBaseItem("))]
    check("filter && !filter->Admits(item.slot, item.type)" in pick and "DropEligible(" in pick and "item.itemLevel > monsterLevel" in pick,
          "PickBaseItem applies the slot filter beside the class and level rules")
    gamble = pick[pick.index("PickGamble("):]
    check("PickBaseItem(Rarity::Legendary, level, rollClass, 0, &filter)" in gamble and "PickBaseItem(Rarity::Rare, level, rollClass, 0, &filter)" in gamble,
          "the gamble uses PickBaseItem for both outcomes, filtered")
    drop_calls = re.findall(r"PickBaseItem\([^;]*;", loot[loot.index("namespace Detail\n{", loot.index("std::uint32_t PickGamble")):])
    check(drop_calls and all("filter" not in c and "&" not in c for c in drop_calls), "every drop still calls PickBaseItem with no filter")
    check("b.slot, b.type" in loot and "item.slot = " in loot and "item.type = " in loot, "the base items carry their slot and kind")
    check("RegisterKadalaScripts();" in loot[loot.index("void RegisterScripts()"):], "the hook is registered with the loot scripts")


WIRING_MUTANTS = [
    ("the take-over is dropped", "hook", "item = 0;", "item = item;"),
    ("the debit comes after the commit", "hook", "DC::AccountEconomy::DebitMaterial(player, BloodShards::Entry, facts.price)",
     "true"),
    ("the item is staged as a shell", "hook", 'StageRoll(player, base, level, "", transaction, rollClass,',
     'DeliverShell(player, base, level, "legendary", 1, "kadala", 1, rollClass,'),
    ("the price comes from the client's count", "hook", "facts.price = ", "facts.price = count * "),
    ("the stock store step is used", "hook", "Staged guard{player};", "Staged guard{player}; StoreNewItem(cell, base, true);"),
    ("a drop is given the filter", "loot", "PickBaseItem(rarity, monsterLevel, rollClass, tier)", "PickBaseItem(rarity, monsterLevel, rollClass, tier, &filter)"),
    ("the loader forgets the kinds", "loot", "item.type = ", "item.kind = "),
]


def test_wiring_mutants():
    for what, which, old, new in WIRING_MUTANTS:
        hook, loot = code(HOOK), loot_code()
        source = hook if which == "hook" else loot
        if which == "hook" and old == "facts.price = ":
            source = source.replace("Kadala::ShardPrice(cost, BloodShards::Entry, facts.price);",
                                    "(facts.price = count * 25) > 0;")
        else:
            assert source.count(old) >= 1, "wiring mutant target moved: " + old
            source = source.replace(old, new, 1)
        try:
            test_wiring(source, loot) if which == "hook" else test_wiring(hook, source)
        except (AssertionError, ValueError, IndexError):
            print("PASS wiring mutant killed: " + what, flush=True)
            continue
        raise AssertionError("wiring mutant survived: " + what)


def test_mysql(port):
    sheet = rows(D3 / "kadala_entries.csv")
    migration = MODULE / "data/sql/db-world/updates/kadala_0002_entries.sql"
    mirror = MODULE / "data/generated/kadala_0002_entries.sql"
    check(migration.read_text(encoding="utf-8") == mirror.read_text(encoding="utf-8"), "the generated mirror and the migration are one file")
    command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
               "--batch", "--raw", "--skip-column-names"]

    def sql(text, database=None):
        done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True, capture_output=True)
        if done.returncode:
            raise RuntimeError(done.stderr)
        return done.stdout.rstrip("\n")

    sql("CREATE DATABASE kadala_entries CHARACTER SET utf8mb4;")
    text = migration.read_text(encoding="utf-8")
    sql(text, "kadala_entries")
    sql(text, "kadala_entries")
    got = [tuple(line.split("\t")) for line in sql("SELECT item_entry, slot, base_types FROM dc_kadala_entry ORDER BY item_entry", "kadala_entries").splitlines()]
    want = sorted((e["item_entry"], e["slot"], e["base_types"]) for e in sheet)
    check(got == want, "the migration replays twice and the table is kadala_entries.csv")
    sql("CREATE DATABASE kadala_mutant CHARACTER SET utf8mb4;")
    sql(text.replace("'Shield;Crusader Shield'", "''"), "kadala_mutant")
    mutant = [tuple(line.split("\t")) for line in sql("SELECT item_entry, slot, base_types FROM dc_kadala_entry ORDER BY item_entry", "kadala_mutant").splitlines()]
    check(mutant != want, "mutant killed: an entry table that drops a kind no longer equals the sheet")
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_data()
    test_harness()
    test_wiring()
    test_wiring_mutants()
    isolated(test_mysql)
