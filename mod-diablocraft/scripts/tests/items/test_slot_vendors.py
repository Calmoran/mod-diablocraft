"""diablocraft-y2gt - the legendary slot vendors (kadala.md section 6, Part 7): lists, rule header, hook wiring, replay.

What this proves, and what it does not:

  * The lists. The newest slot-vendor migration (`slot_vendors_0008.sql`: without the Horadric Cache's legendaries since
    diablocraft-dm9vg.8, with the Necromancer since diablocraft-ngybv and the Crusader since diablocraft-jfd7p) is parsed and each vendor's rows are compared with a list computed a second way:
    from base_items.csv, base_item_ids.csv and the AllowableClass the APPLIED migrations (items_0011, items_0020, then the added-classes deltas) write,
    not from the generator's own wear rule, less the cache pools' items as the generated bounties_0003 rows carry them. Names are read from the generated item_template rows and must be A to Z, case aside.
    Free (no ExtendedCost), one condition row per entry that has a level and none for one that has not, no vendor over
    150 entries (a planted 151st is refused), and nothing that names Kadala, Blood Shards or a price.
  * The decisions. The production header `src/items/dc_slot_vendor_rule.h` is compiled into a harness and driven with
    the sheets' values: the roll class of every listed item for every playable buyer, and every refusal of the stock
    order. Each rule has a mutant of the header that must turn the harness red.
  * The hook's WIRING (`dc_slot_vendor.cpp`) is read with comments removed: the take-over only at a slot vendor, the
    stage before the commit before the publish, no ledger, no shell, no stock store step, one commit. It is NOT
    executed: that needs a Player and a vendor, which is the GM script in docs/test-diablocraft-y2gt.md.
  * The applied `slot_vendors_0001.sql` and `slot_vendors_0002.sql` (dev), then the newest, twice, are replayed on a disposable MySQL with stub core tables and read back.
"""
import csv
import itertools
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_slot_vendors as gen
from class_names import item_key
import generate_sql as gensql
import harness_env
from test_account_economy_sql import MYSQL, ROOT, isolated

MODULE = ROOT / "mod-diablocraft"
D3 = MODULE / "data/d3"
SRC = MODULE / "src"
HEADER = SRC / "items/dc_slot_vendor_rule.h"
HOOK = SRC / "items/dc_slot_vendor.cpp"
ITEMS = SRC / "items/dc_items.cpp"
ROLL_CLASS = SRC / "items/dc_roll_class.h"
UPDATES = MODULE / "data/sql/db-world/updates"
MIGRATION = UPDATES / gen.NAME
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/slot_vendors_test"


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


def squash(text):
    return " ".join(text.split())


def cpp_str(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---- the lists ----------------------------------------------------------------------------------------------------

def parsed_lists(text):
    """{vendor: [item entry]} in list order, from the migration's npc_vendor rows."""
    found = re.findall(r"^\((9101\d\d), (\d+), (\d+), 0, 0, (\d+), 0\)[,;]$", text, re.M)
    out = {}
    for vendor, position, item, cost in found:
        assert cost == "0", "a slot vendor row carries an ExtendedCost"
        out.setdefault(int(vendor), []).append((int(position), int(item)))
    for vendor, pairs in out.items():
        assert [p for p, _ in pairs] == list(range(len(pairs))), "slot positions run 0.."
        out[vendor] = [i for _, i in pairs]
    return out


def parsed_conditions(text):
    return re.findall(r"^\(23, (\d+), (\d+), 0, 0, 27, 0, (\d+), 3, 0, 0, 0, 0, '', '[^']*'\)[,;]$", text, re.M)


def item_names():
    names = {}
    for line in (MODULE / "data/generated/item_template.sql").read_text(encoding="utf-8").splitlines():
        m = re.match(r"\((\d+), \d+, \d+, '((?:[^']|'')*)'", line)
        if m:
            names[int(m.group(1))] = m.group(2).replace("''", "'")
    return names


def applied_wear():
    """AllowableClass per item entry as the migrations leave it (items_0011, items_0020's delta, items_0028's for the Monk,
    then the newest added-classes delta, generate_sql.ADDED_WEAR_MIGRATION, for the Necromancer, the Crusader, the Demon Hunter and the Witch Doctor too)."""
    wear = {}
    for name in ("items_0011_item_allowable_class.sql", "items_0020_set_wear_class.sql",
                 "items_0028_item_allowable_class_added.sql", gensql.ADDED_WEAR_MIGRATION,
                 gensql.ADDED_BASE_MIGRATION):     # the base items added since 0002 carry their own wear mask
        for mask, found in re.findall(r"SET `AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)",
                                      (UPDATES / name).read_text(encoding="utf-8")):
            for entry in found.split(","):
                wear[int(entry)] = int(mask)
    return wear


def expected_lists():
    """Each slot's list a second way: pool legendary and set items some playable class may wear, by applied wear."""
    ids = {r["d3_id"]: int(r["item_entry"]) for r in rows(D3 / "base_item_ids.csv")}
    wear, names = applied_wear(), item_names()
    cache = {int(e) for e in re.findall(r"^\(\d+, (\d+)\)[,;]$", (MODULE / "data/generated/bounties_0003_caches.sql")
                                         .read_text(encoding="utf-8").split("INSERT INTO `dc_bounties_cache_legendary`")[1], re.M)}
    out = {}
    for r in rows(D3 / "base_items.csv"):
        if r["rarity"] in ("legendary", "set") and r["pool_version"] == "yes" and wear[ids[r["d3_id"]]] != 0 \
                and ids[r["d3_id"]] not in cache:
            out.setdefault(r["slot"], []).append(ids[r["d3_id"]])
    return {slot: sorted(items, key=lambda i: (names[i].casefold(), names[i], i)) for slot, items in out.items()}


def test_lists():
    text = MIGRATION.read_text(encoding="utf-8")
    check(text == (MODULE / "data/generated" / gen.NAME).read_text(encoding="utf-8"), "the generated mirror and the migration are one file")
    check(text == gen.render(), "the migration is what the generator renders from the sheets")
    vendors = rows(D3 / "slot_vendors.csv")
    lists, want, names = parsed_lists(text), expected_lists(), item_names()
    check(len(vendors) == 13 and len(lists) == 13, "thirteen vendors, one list each")
    check(set(want) == {v["slot"] for v in vendors}, "every slot that has a listed item has a vendor, and no vendor is for an empty slot")
    for v in vendors:
        got = lists[int(v["entry"])]
        check(got == want[v["slot"]], f"{v['name']}: the list is the {v['slot']} items a playable class can wear, by name ({len(got)})")
        ns = [names[i] for i in got]
        check(ns == sorted(ns, key=lambda n: (n.casefold(), n)), f"{v['name']}: A to Z, case aside")
        check(len(got) <= gen.MAX_VENDOR_ITEMS, f"{v['name']}: within the core's 150")
    flat = [i for items in lists.values() for i in items]
    check(len(flat) == len(set(flat)), "no item on two vendors")
    # The older versions, the Ethereals and what no playable class can wear are not listed; crafted sets are.
    by_id = {r["d3_id"]: r for r in rows(D3 / "base_items.csv")}
    bases = {int(r["item_entry"]): by_id[r["d3_id"]] for r in rows(D3 / "base_item_ids.csv")}
    check(all(bases[i]["pool_version"] == "yes" and bases[i]["rarity"] in ("legendary", "set") for i in flat),
          "only current-pool legendary and set items")
    check(any(bases[i]["craft_only"] == "yes" for i in flat), "a Blacksmith-crafted set piece is listed (free here)")
    wear = applied_wear()
    check(all(wear[i] != 0 for i in flat), "no listed item is one no playable class can wear")
    # Conditions: one per entry with a level, from the sheet's item_level, and none without.
    conds = {(int(g), int(e)): int(lv) for g, e, lv in parsed_conditions(text)}
    levelled = {(v, i): int(bases[i]["item_level"]) for v, items in lists.items() for i in items if bases[i]["item_level"]}
    check(conds == levelled and len(conds) == len(parsed_conditions(text)), "a level condition per entry with an item_level, equal to it, none else")
    check(len(conds) < len(flat), "entries with no level have no condition (they show from level 1)")
    # Nothing of Kadala's.
    check(not re.search(r"910005|blood shard|102007|itemextendedcost|kadala|mystery", text, re.I),
          "the migration names no Kadala entry, price row or Blood Shard")
    entries = [int(v["entry"]) for v in vendors]
    taken = set()
    for path in UPDATES.glob("*.sql"):
        if not path.name.startswith("slot_vendors_"):
            taken |= {int(m) for m in re.findall(r"\b(9101[0-9]{2})\b", path.read_text(encoding="utf-8"))}
    check(not (set(entries) & taken), "the vendor entries are used by no other migration")


def test_refuses_over_150():
    with tempfile.TemporaryDirectory(dir=str(SCRATCH.parent) if SCRATCH.parent.exists() else None) as tmp:
        d3 = pathlib.Path(tmp)
        for f in ("slot_vendors.csv", "base_items.csv", "base_item_ids.csv", "set_classes.csv", "class_map.csv",
                  "bounty_cache_legendaries.csv"):
            shutil.copy(D3 / f, d3 / f)
        gen.listed(d3)  # the real sheets pass
        bases = rows(d3 / "base_items.csv")
        ids = rows(d3 / "base_item_ids.csv")
        donor = next(b for b in bases if b["rarity"] == "legendary" and b["slot"] == "onehand" and b["pool_version"] == "yes")
        top = max(int(r["item_entry"]) for r in ids)
        for n in range(1, 90):  # 70 listed + 89 > 150
            bases.append({**donor, "d3_id": f"Planted_{n}", "d3_name": f"Planted {n:03d}"})
            ids.append({"d3_id": f"Planted_{n}", "item_entry": str(top + n)})
        for name, content in (("base_items.csv", bases), ("base_item_ids.csv", ids)):
            with (d3 / name).open("w", newline="", encoding="utf-8") as out:
                w = csv.DictWriter(out, fieldnames=list(content[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(content)
        try:
            gen.listed(d3)
        except ValueError as error:
            check("150" in str(error), "a list over 150 is refused, not cut by the core")
        else:
            raise AssertionError("a list over 150 was generated")


# ---- the rule header -----------------------------------------------------------------------------------------------

def harness_source():
    text = MIGRATION.read_text(encoding="utf-8")
    listed = {i for items in parsed_lists(text).values() for i in items}
    ids = {int(r["item_entry"]): r["d3_id"] for r in rows(D3 / "base_item_ids.csv")}
    by_id = {r["d3_id"]: r for r in rows(D3 / "base_items.csv")}
    set_class = {r["set_name"]: r["class_key"] for r in rows(D3 / "set_classes.csv")}
    classes = [item_key(r["d3_class"]) for r in rows(D3 / "class_map.csv")]
    cases = []
    for item in sorted(listed):
        b = by_id[ids[item]]
        designated, sclass = b["designated_class"], set_class.get(b["set_name"], "") if b["rarity"] == "set" else ""
        for buyer in classes:
            expected = designated or sclass or buyer  # second statement of 6.5 step 3, from the sheets
            cases.append("  {%s, %s, %s, %s}" % tuple(cpp_str(x) for x in (designated, sclass, buyer, expected)))
    return r"""
#include "dc_slot_vendor_rule.h"
#include <cstdio>
using namespace DC::SlotVendor;
static int bad = 0;
static void expect(bool ok, const char* what) { if (!ok) { std::printf("FAIL %s\n", what); bad = 1; } }
struct Case { const char *designated, *setClass, *buyer, *expected; };
static const Case cases[] = {
@CASES@
};
static Facts good() {
  Facts f; f.alive = f.inReach = f.onList = f.conditionMet = f.rollClassKnown = f.bagFree = true; f.count = 1; return f;
}
int main() {
  // Every listed item, every playable buyer: a class's own item or a class set's piece rolls for that class, any
  // other for the buyer's.
  for (const Case& c : cases)
    expect(RollClassFor(c.designated, c.setClass, c.buyer) == c.expected, "the roll class is the item's class, else the set's, else the buyer's");
  expect(RollClassFor("", "", "wizard") == "wizard", "a classless item rolls for the buyer");
  expect(RollClassFor("barbarian", "", "wizard") == "barbarian", "a class-only item rolls for its own class");
  expect(RollClassFor("", "barbarian", "wizard") == "barbarian", "a class set's piece rolls for its set's class");
  expect(RollClassFor("wizard", "barbarian", "barbarian") == "wizard", "a class-only item's own class wins over the set's");
  expect(RollClassFor("", "", "").empty(), "no class anywhere is nothing to roll");

  expect(Judge(good()) == Verdict::Buy, "everything in order buys");
  { Facts f = good(); f.bagFree = false; expect(Judge(f) == Verdict::BagsFull, "full bags are refused"); }
  { Facts f = good(); f.count = 2; expect(Judge(f) == Verdict::BadCount, "a count above one is refused"); }
  { Facts f = good(); f.count = 0; expect(Judge(f) == Verdict::BadCount, "a count of zero is refused"); }
  { Facts f = good(); f.alive = false; expect(Judge(f) == Verdict::Dead, "the dead cannot buy"); }
  { Facts f = good(); f.inReach = false; expect(Judge(f) == Verdict::TooFar, "out of reach is refused"); }
  { Facts f = good(); f.onList = false; expect(Judge(f) == Verdict::NotListed, "an entry not at that position is refused"); }
  { Facts f = good(); f.conditionMet = false; expect(Judge(f) == Verdict::ConditionNotMet, "a level below the entry's is refused"); }
  { Facts f = good(); f.rollClassKnown = false; expect(Judge(f) == Verdict::NothingToRoll, "no roll class is refused"); }
  { Facts f = good(); f.alive = false; f.bagFree = false; expect(Judge(f) == Verdict::Dead, "the stock order: dead first"); }
  { Facts f = good(); f.conditionMet = false; f.bagFree = false; expect(Judge(f) == Verdict::ConditionNotMet, "the level before the bags"); }
  { Facts f = good(); f.inReach = false; f.onList = false; expect(Judge(f) == Verdict::TooFar, "reach before the list"); }
  return bad;
}
""".replace("@CASES@", ",\n".join(cases))


# (what it breaks, old text, new text) in the production header; each must turn the harness red.
MUTANTS = [
    ("the roll class is always the buyer's", "return own.empty() ? buyerClass : own;", "return buyerClass;"),
    ("the roll class ignores the buyer", "return own.empty() ? buyerClass : own;", "return own;"),
    ("the set's class wins over the item's own", "DC::RollClass::DropClass(designated, setClass)",
     "(setClass.empty() ? designated : setClass)"),
    ("the set's class is ignored", "DC::RollClass::DropClass(designated, setClass)", "designated"),
    ("a count above one is allowed", "if (f.count != 1)", "if (f.count < 1)"),
    ("a count of zero is allowed", "if (f.count != 1)", "if (f.count > 1)"),
    ("full bags still buy", "if (!f.bagFree)", "if (false)"),
    ("an unlisted position still buys", "if (!f.onList)", "if (false)"),
    ("out of reach still buys", "if (!f.inReach)", "if (false)"),
    ("the dead still buy", "if (!f.alive)", "if (false)"),
    ("a level below the entry's still buys", "if (!f.conditionMet)", "if (false)"),
    ("no roll class still buys", "if (!f.rollClassKnown)", "if (false)"),
    ("bags checked before the level", "    if (!f.conditionMet)\n        return Verdict::ConditionNotMet;\n", ""),
]


def mutate(text, old, new):
    """Replace the one place `old` appears, whatever the formatter did to the whitespace around it."""
    pattern = re.compile(r"\s+".join(re.escape(token) for token in old.split()))
    assert len(pattern.findall(text)) == 1, "mutant target moved: " + old
    return pattern.sub(lambda _: new, text)


def run_harness(header_text):
    try:
        binary = harness_env.build_text(harness_source(), flags=["-std=c++17"],
                                        files={"dc_slot_vendor_rule.h": header_text, "dc_roll_class.h": ROLL_CLASS.read_text(encoding="utf-8")})
    except harness_env.BuildError as error:
        raise RuntimeError("harness did not compile:\n" + error.stderr)
    ran = harness_env.run([str(binary)], capture_output=True, text=True)
    return ran.returncode == 0, ran.stdout


def test_harness():
    ok, out = run_harness(HEADER.read_text(encoding="utf-8"))
    check(ok, "rule header holds against the sheets" + ("" if ok else "\n" + out))
    text = HEADER.read_text(encoding="utf-8")
    for what, old, new in MUTANTS:
        survived, _ = run_harness(mutate(text, old, new))
        check(not survived, "mutant killed: " + what)


# ---- the hook's wiring ---------------------------------------------------------------------------------------------

def test_wiring(hook=None, items=None):
    hook = code(HOOK) if hook is None else hook
    items = code(ITEMS) if items is None else items
    take_over = hook[hook.index("void OnPlayerBeforeBuyItemFromVendor"):]
    check(take_over.index("IsSlotVendor(vendor->GetEntry())") < take_over.index("item = 0") < take_over.index("Buy(player"),
          "the hook takes over (item = 0) only at a slot vendor, then runs the purchase")
    check("if (!vendor || !IsSlotVendor(vendor->GetEntry())) return;" in squash(take_over), "any other vendor is left to the stock path")
    buy = hook[hook.index("void Buy("):hook.index("class SlotVendorWorld")]
    order = [buy.index(s) for s in ("SlotVendor::Judge(facts)", "PlayerEconomy::Scope operation", "StageRoll(",
                                    "SaveInventoryAndGoldToDB(transaction)", "DC::AccountEconomy::Commit(player, transaction)",
                                    "guard.committed = true", "staged->Publish()", "player->SendNewItem(")]
    check(order == sorted(order), "refusals, then stage, one commit, then publish and the confirmation")
    check(buy.count("Commit(") == 1, "one commit")
    check(re.search(r"StageRoll\(player, entry, player->GetLevel\(\), \"\", transaction, rollClass,\s+RollQuality\(player, entry, player->GetLevel\(\), 0, true\)\)", buy) is not None,
          "the entry's own base is staged by the roller at the buyer's level, no rarity forced and no shell (identified), its quality decided as a purchase (level gate only)")
    check("RollClassFor(roll.designated, roll.setClass, ClassKeyOf(player->getClass()))" in squash(buy), "the roll class is the rule's")
    check("GetConditionsForNpcVendorEvent(creature->GetEntry(), entry)" in squash(buy), "the entry's stock condition is checked here, since the stock check never runs")
    check(buy.index("CanStoreNewItem(") < buy.index("SlotVendor::Judge(facts)"), "the bag cell is checked before anything is staged")
    check("Staged guard{player};" in buy and buy.index("Staged guard") > buy.index("StageRoll(") and
          buy.index("Staged guard") < buy.index("Commit("), "a failure after the stage fails the whole operation")
    check(not re.search(r"DebitMaterial|CreditMaterial|MaterialBalance|BloodShards|ExtendedCost|Kadala|kadala|Shell|DeliverShell|dc_item_unidentified",
                        hook), "no price, no ledger, no Blood Shard, no shell, nothing of Kadala's")
    check(not re.search(r"(?<![A-Za-z])(_StoreOrEquipNewItem|StoreNewItem|StoreItem)\(", hook), "the stock store step is never used")
    check("RegisterSlotVendorScripts();" in items[items.index("void RegisterScripts()"):], "the hook is registered with the item scripts")
    check(not re.search(r"OnPlayerCanSellItem|SellPrice|salvage|Salvage", hook), "a bought item is left to sell and salvage like any drop (6.7.3 not taken)")


WIRING_MUTANTS = [
    ("the take-over is dropped", "hook", "item = 0;", "item = item;"),
    ("every vendor is taken over", "hook", "if (!vendor || !IsSlotVendor(vendor->GetEntry()))", "if (!vendor)"),
    ("the item is staged as a shell", "hook", 'StageRoll(player, entry, player->GetLevel(), "", transaction, rollClass,',
     'DeliverShell(player, entry, player->GetLevel(), "legendary", 1, "x", 1, rollClass,'),
    ("the stock store step is used", "hook", "Staged guard{player};", "Staged guard{player}; StoreNewItem(cell, entry, true);"),
    ("the level condition is not checked", "hook", "GetConditionsForNpcVendorEvent(creature->GetEntry(), entry)",
     "GetConditionsForNpcVendorEvent(creature->GetEntry(), 0)"),
    ("a price is charged", "hook", "Staged guard{player};", "Staged guard{player}; DC::AccountEconomy::DebitMaterial(player, 1, 1);"),
    ("the hook is not registered", "items", "RegisterSlotVendorScripts();", ""),
    ("the roll class is the buyer's", "hook", "SlotVendor::RollClassFor(roll.designated, roll.setClass, ClassKeyOf(player->getClass()))",
     "ClassKeyOf(player->getClass())"),
]


def test_wiring_mutants():
    for what, which, old, new in WIRING_MUTANTS:
        hook, items = code(HOOK), code(ITEMS)
        source = hook if which == "hook" else items
        assert source.count(old) >= 1, "wiring mutant target moved: " + old
        source = source.replace(old, new, 1)
        try:
            test_wiring(source, items) if which == "hook" else test_wiring(hook, source)
        except (AssertionError, ValueError, IndexError):
            print("PASS wiring mutant killed: " + what, flush=True)
            continue
        raise AssertionError("wiring mutant survived: " + what)


# ---- the replay -----------------------------------------------------------------------------------------------------

STUB = """
CREATE TABLE creature_template (entry INT PRIMARY KEY, name VARCHAR(100), subname VARCHAR(100), minlevel INT, maxlevel INT,
  npcflag INT, gossip_menu_id INT, ScriptName VARCHAR(64), AIName VARCHAR(64));
INSERT INTO creature_template VALUES (910000, 'Blacksmith', 'Smith', 70, 70, 4739, 21, 'dc_blacksmith', 'SmartAI');
CREATE TABLE creature_template_model (CreatureID INT, Idx INT, CreatureDisplayID INT, DisplayScale FLOAT, Probability FLOAT,
  VerifiedBuild INT, PRIMARY KEY (CreatureID, Idx));
INSERT INTO creature_template_model VALUES (910000, 0, 4000, 1, 1, 0);
CREATE TABLE npc_vendor (entry INT, slot INT, item INT, maxcount INT, incrtime INT, ExtendedCost INT, VerifiedBuild INT,
  PRIMARY KEY (entry, item));
CREATE TABLE conditions (SourceTypeOrReferenceId INT, SourceGroup INT UNSIGNED, SourceEntry INT, SourceId INT,
  ElseGroup INT UNSIGNED, ConditionTypeOrReference INT, ConditionTarget TINYINT UNSIGNED, ConditionValue1 INT UNSIGNED,
  ConditionValue2 INT UNSIGNED, ConditionValue3 INT UNSIGNED, NegativeCondition TINYINT UNSIGNED, ErrorType INT UNSIGNED,
  ErrorTextId INT UNSIGNED, ScriptName CHAR(64), Comment VARCHAR(255),
  PRIMARY KEY (SourceTypeOrReferenceId, SourceGroup, SourceEntry, SourceId, ElseGroup, ConditionTypeOrReference,
               ConditionTarget, ConditionValue1, ConditionValue2, ConditionValue3));
"""


def test_mysql(port):
    command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
               "--batch", "--raw", "--skip-column-names"]

    def sql(text, database=None):
        done = subprocess.run(command + ([f"--database={database}"] if database else []), input=text, text=True, capture_output=True)
        if done.returncode:
            raise RuntimeError(done.stderr)
        return done.stdout.rstrip("\n")

    text = MIGRATION.read_text(encoding="utf-8")
    sql("CREATE DATABASE slot_vendors CHARACTER SET utf8mb4;")
    sql(STUB, "slot_vendors")
    sql((UPDATES / "slot_vendors_0001.sql").read_text(encoding="utf-8"), "slot_vendors")  # what the live world holds
    sql((UPDATES / "slot_vendors_0002.sql").read_text(encoding="utf-8"), "slot_vendors")  # and what dev holds
    sql(text, "slot_vendors")
    sql(text, "slot_vendors")
    vendors = rows(D3 / "slot_vendors.csv")
    creatures = [tuple(l.split("\t")) for l in sql(
        "SELECT entry, name, subname, minlevel, npcflag, gossip_menu_id, ScriptName, AIName FROM creature_template "
        "WHERE entry>910000 ORDER BY entry", "slot_vendors").splitlines()]
    check(creatures == [(v["entry"], v["name"], "", v["level"], v["npcflag"], "0", "", "") for v in vendors],
          "twice applied: thirteen vendor creatures, vendor flag only, no gossip, no script, the sheet's names")
    check(sql("SELECT COUNT(*) FROM creature_template_model WHERE CreatureID>910000", "slot_vendors") == "13", "each has its model")
    got = {}
    for line in sql("SELECT entry, item FROM npc_vendor ORDER BY entry, slot", "slot_vendors").splitlines():
        entry, item = map(int, line.split("\t"))
        got.setdefault(entry, []).append(item)
    check(got == parsed_lists(text), "the npc_vendor rows read back are the lists")
    check(sql("SELECT COUNT(*) FROM conditions WHERE SourceTypeOrReferenceId=23", "slot_vendors") == str(len(parsed_conditions(text))),
          "the level conditions read back")
    check(sql("SELECT COUNT(*), SUM(slot LIKE '%'), MIN(entry), MAX(entry) FROM dc_slot_vendor", "slot_vendors") == "13\t13\t910100\t910112",
          "dc_slot_vendor lists the thirteen")
    sql("CREATE DATABASE slot_mutant CHARACTER SET utf8mb4;")
    sql(STUB, "slot_mutant")
    mutant = re.sub(r"^DELETE FROM `npc_vendor`.*$", "", text, count=1, flags=re.M)
    check(mutant != text, "the mutant removed the npc_vendor DELETE")
    sql(mutant, "slot_mutant")
    try:
        sql(mutant, "slot_mutant")
    except RuntimeError:
        check(True, "mutant killed: without its DELETE the migration does not replay")
    else:
        raise AssertionError("a migration that keeps its old rows replayed")
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_lists()
    test_refuses_over_150()
    test_harness()
    test_wiring()
    test_wiring_mutants()
    isolated(test_mysql)
