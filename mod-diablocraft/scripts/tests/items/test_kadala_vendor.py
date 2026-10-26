"""diablocraft-m2po - Kadala part 3, her vendor rows: the generated migration replayed on a real MySQL.

What this proves, and what it does not:

  * The newest migration (`kadala_0007_vendor.sql` since diablocraft-xnrvn.3; `kadala_0001_vendor.sql` is applied and stays
    as it was), and its `data/generated` mirror, is what `generate_kadala.py` renders.
  * It is replayed twice on a disposable MySQL built from the core's own CREATE TABLEs for `item_template`,
    `npc_vendor`, `itemextendedcost_dbc`, `creature_template` and `creature_template_model`, then read back and checked
    against the SHEETS, not against the generator: her list is `kadala_entries.csv` in order, each entry is charged
    `kadala.csv`'s price in the Blood Shard item `account_economy.csv` names, a class sees an entry exactly when it can wear
    a generic base of that kind (`items_0011`, the applied wear rule), the Mystery rows are plain miscellaneous items
    with no purchase-record flag, her creature is vendor-flag only, and no ExtendedCost id is a stock one.
  * Each rule has a mutant of the generator that must turn that check red; the generator also refuses bad sheets.
  * NOT covered: the client's ItemExtendedCost.dbc and Item.dbc rows (Part 4), the purchase itself (Part 5), the
    window on screen, the placement. Those are the GM script in docs/test-m2po.md and the later parts.
"""
import csv
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_kadala as generator
import generate_sql as gensql
from test_account_economy_sql import MYSQL, ROOT, isolated

MODULE = ROOT / "mod-diablocraft"
D3 = MODULE / "data/d3"
UPDATES = MODULE / "data/sql/db-world/updates"
CORE_SQL = ROOT / "azerothcore-wotlk/data/sql/base/db_world"
STOCK_COST_DBC = ROOT / "azerothcore-wotlk/build/server/data/dbc/ItemExtendedCost.dbc"
PURCHASE_RECORD = 0x08000000
DONOR_FLAG = 4225


def rows(name, directory=D3):
    with (directory / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def check(ok, name):
    if not ok:
        raise AssertionError(name)
    print("PASS " + name, flush=True)


def stock_cost_ids():
    data = STOCK_COST_DBC.read_bytes()
    _, count, _, size, _ = struct.unpack("<4sIIII", data[:20])
    return {struct.unpack_from("<I", data, 20 + i * size)[0] for i in range(count)}


def applied_wear():
    """{item entry: AllowableClass} from items_0011 and the delta for the classes added since (items_0020's set lock
    is not read: the Mystery rows are plain items and no set piece is checked here)."""
    out = {}
    for name in ("items_0011_item_allowable_class.sql", "items_0028_item_allowable_class_added.sql",
                 gensql.ADDED_WEAR_MIGRATION):
        text = (UPDATES / name).read_text(encoding="utf-8")
        for mask, found in re.findall(r"`AllowableClass`=(-?\d+) WHERE `entry` IN \(([^)]*)\)", text):
            out.update({int(e): int(mask) for e in found.split(",")})
    return out


def table_sql(name):
    text = (CORE_SQL / f"{name}.sql").read_text(encoding="utf-8")
    return re.search(r"CREATE TABLE `%s` \(.*?\) ENGINE=[^;]*;" % name, text, re.S).group(0)


def mutated_generator(old, new):
    source = (HERE / "generate/items/generate_kadala.py").read_text(encoding="utf-8")
    assert source.count(old) == 1, "mutant target moved: " + old
    module = type(sys)("generate_kadala_mutant")
    module.__file__ = str(HERE / "generate/items/generate_kadala.py")
    exec(compile(source.replace(old, new), module.__file__, "exec"), module.__dict__)
    return module


class Replay:
    def __init__(self, port):
        self.command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}",
                        "--user=root", "--batch", "--raw", "--skip-column-names"]
        self.count = 0

    def sql(self, text, database=None):
        command = self.command + ([f"--database={database}"] if database else [])
        done = subprocess.run(command, input=text, text=True, capture_output=True)
        if done.returncode:
            raise RuntimeError(done.stderr.strip())
        return [line.split("\t") for line in done.stdout.splitlines()]

    def fresh(self):
        """A database holding the core's tables and the Blacksmith donor, nothing of Kadala's."""
        self.count += 1
        name = f"kadala_{self.count}"
        self.sql(f"CREATE DATABASE {name} CHARACTER SET utf8mb4;")
        schema = "".join(table_sql(t) + "\n" for t in ("item_template", "npc_vendor", "itemextendedcost_dbc",
                                                        "creature_template", "creature_template_model"))
        self.sql(schema, name)
        self.sql("INSERT INTO creature_template (entry,name,subname,minlevel,maxlevel,npcflag,faction,gossip_menu_id,ScriptName,AIName)"
                 f" VALUES (910000,'Blacksmith','Macecrafter',42,42,{DONOR_FLAG},35,7777,'dc_hub_blacksmith','SmartAI');"
                 "INSERT INTO creature_template_model VALUES (910000,0,12345,1,1,0);", name)
        return name

    def replay(self, migration):
        name = self.fresh()
        self.sql(migration, name)
        self.sql(migration, name)  # the updater may run it again on a restore: it must be idempotent
        return name

    def read(self, name, query):
        return self.sql(query, name)


def expected():
    """What the sheets say Kadala sells, with no help from the generator."""
    entries, rules = rows("kadala_entries.csv"), {r["rule"]: r["value"] for r in rows("kadala.csv")}
    shard = [r for r in rows("account_economy.csv") if r["name"] == "Blood Shard"]
    assert len(shard) == 1
    price = {e["item_entry"]: int(re.fullmatch(r"(\d+) Blood Shards", rules[e["cost_rule"]]).group(1)) for e in entries}
    return entries, price, shard[0]["item_entry"]


def facts_hold(replay, name):
    """Every claim about the replayed database; raises AssertionError on the first that fails."""
    entries, price, shard = expected()
    npc = rows("kadala_npc.csv")[0]
    got = replay.read(name, "SELECT slot, item, ExtendedCost FROM npc_vendor WHERE entry=%s ORDER BY slot" % npc["entry"])
    assert [r[1] for r in got] == [e["item_entry"] for e in entries], "her list is the sheet's, in order"
    assert [int(r[0]) for r in got] == list(range(len(entries))), "slots count from 0 with no gap"
    costs = {r[0]: r for r in replay.read(name, "SELECT ID, HonorPoints, ArenaPoints, ArenaBracket, ItemID_1, ItemID_2, ItemID_3, "
                                                  "ItemID_4, ItemID_5, ItemCount_1, ItemCount_2, ItemCount_3, ItemCount_4, ItemCount_5, "
                                                  "RequiredArenaRating FROM itemextendedcost_dbc")}
    assert len(costs) == len(set(price.values())), "one ExtendedCost row per distinct price"
    assert not set(map(int, costs)) & stock_cost_ids(), "no ExtendedCost id is a stock one"
    for _, item, cost in got:
        row = costs[cost]
        assert row[4] == shard and row[9] == str(price[item]), f"{item} costs {price[item]} Blood Shards (item {shard})"
        assert [row[i] for i in (1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13, 14)] == ["0"] * 12, "the price is only Blood Shards"
    wear, classes = applied_wear(), {r["wow_class_id"] for r in rows("class_map.csv")}
    generic = [r for r in rows("base_items.csv") if not r["rarity"]]
    ids = {r["d3_id"]: int(r["item_entry"]) for r in rows("base_item_ids.csv")}
    items = {r[0]: r for r in replay.read(name, "SELECT entry, class, subclass, name, displayid, Flags, InventoryType, "
                                                "AllowableClass, bonding, BuyPrice, SellPrice, spellid_1, description "
                                                "FROM item_template WHERE entry BETWEEN 102300 AND 102399")}
    assert set(items) == {e["item_entry"] for e in entries}, "exactly the Mystery rows"
    displays = {(r["slot"], r["type"]): r["wow_display_id"] for r in rows("item_display.csv")}
    for e in entries:
        row = items[e["item_entry"]]
        assert row[1] == "15" and row[2] == "0" and row[6] == "0", f"{e['name']} is a plain miscellaneous item"
        assert row[3] == e["name"] and row[12] == e["description"], f"{e['name']} name and description"
        assert row[4] == displays[(e["slot"], e["display_type"])], f"{e['name']} icon is its slot's"
        assert not int(row[5]) & PURCHASE_RECORD, f"{e['name']} cannot be refunded"
        assert row[9] == "0" and row[10] == "0" and row[11] == "0", f"{e['name']} has no gold price, sell price or spell"
        wanted = set(filter(None, e["base_types"].split(";")))
        kinds = [b for b in generic if b["slot"] == e["slot"] and (not wanted or b["type"] in wanted)]
        assert kinds, f"{e['name']} stands for a base kind"
        mask = int(row[7])
        for wow_class in classes:
            bit = 1 << (int(wow_class) - 1)
            can = any(wear[ids[b["d3_id"]]] in (-1,) or wear[ids[b["d3_id"]]] & bit for b in kinds)
            assert (mask == -1 or bool(mask & bit)) == can, f"{e['name']} is wearable by class {wow_class} exactly when a base of its kind is"
        assert (row[8] == "1") == (mask != -1), f"{e['name']} is bind-on-pickup exactly when it is class-limited"
    donor = replay.read(name, "SELECT name, subname, minlevel, maxlevel, npcflag, faction, gossip_menu_id, ScriptName, AIName "
                              "FROM creature_template WHERE entry=%s" % npc["entry"])
    assert donor == [[npc["name"], npc["subname"], npc["level"], npc["level"], npc["npcflag"], "35", "0", "", ""]], \
        "Kadala is the sheet's row: vendor flag only, no gossip menu, no script"
    assert npc["npcflag"] == "128", "the sheet's flag is the vendor bit alone"
    assert replay.read(name, "SELECT COUNT(*) FROM creature_template_model WHERE CreatureID=%s AND CreatureDisplayID=12345" % npc["entry"]) == [["1"]], \
        "she wears the donor's model until the designer picks hers"
    assert replay.read(name, "SELECT npcflag, gossip_menu_id, subname FROM creature_template WHERE entry=910000") == [[str(DONOR_FLAG), "7777", "Macecrafter"]], \
        "the donor is untouched"
    assert replay.read(name, "SELECT COUNT(*) FROM npc_vendor WHERE entry<>%s" % npc["entry"]) == [["0"]], "no other vendor is touched"


# Her earlier renders, applied: the same ids by design, superseded by generator.NAME (diablocraft-ngybv, vawmy.4, jjug3, r0d0h, xnrvn.3).
APPLIED_RENDERS = ("kadala_0001_vendor.sql", "kadala_0003_vendor.sql", "kadala_0004_vendor.sql", "kadala_0005_vendor.sql",
                   "kadala_0006_vendor.sql")
# Where the designer's Sanctum layout (bb67) and the one-copy work (k4ce) place her: her creature id, and no item id, may be here.
PLACEMENT_FILES = ("world_0032_sanctum_hub_move.sql", "world_0037_sanctum_one_copy.sql",
                   "world_hub_placements.csv", "world_sanctum_retired_copies.csv")


def named_elsewhere(taken, texts, creature):
    """The ids of `taken` that appear in a migration or sheet other than Kadala's own. An outfit migration
    (outfits_*.sql) may carry her creature id as the first column of its dc_npc_outfit rows, and the hub placement
    files (PLACEMENT_FILES) may carry her creature id anywhere; nowhere else."""
    found = []
    for name, text in texts.items():
        if name in PLACEMENT_FILES:
            found += [i for i in taken if i != creature and re.search(r"(?<![0-9])%s(?![0-9])" % i, text)]
            continue
        if name.startswith("outfits_") and name.endswith(".sql"):
            text = "\n".join(line for line in text.splitlines() if not re.match(r"\(%s," % creature, line))
        found += [i for i in taken if re.search(r"(?<![0-9])%s(?![0-9])" % i, text)]
    return found


def test_files():
    sql = generator.render()
    check((UPDATES / generator.NAME).read_text(encoding="utf-8") == sql, "the migration is the render of the sheets")
    check((MODULE / "data/generated" / generator.NAME).read_text(encoding="utf-8") == sql, "and so is its data/generated mirror")
    entries, price, _ = expected()
    check(len(entries) == 17, "17 entries: 13 for every class and the four class off-hands")
    check(sorted(set(price.values())) == [25, 50, 75, 100], "four prices, the sheet's 25, 50, 75 and 100")
    texts = {path.name: path.read_text(encoding="utf-8", errors="ignore")
             for path in list(UPDATES.glob("*.sql")) + list(D3.glob("*.csv"))
             if path.name not in (generator.NAME, generator.ENTRIES_NAME, "kadala_entries.csv", "kadala_npc.csv",
                                  *APPLIED_RENDERS)}
    taken = [e["item_entry"] for e in entries] + [rows("kadala_npc.csv")[0]["entry"]]
    creature = rows("kadala_npc.csv")[0]["entry"]
    check(not named_elsewhere(taken, texts, creature),
          "no Mystery item or creature id appears in any other migration or sheet")
    check(any(re.match(r"\(%s," % creature, line) for line in texts.get("outfits_0003_npc_outfits.sql", "").splitlines()),
          "Kadala's own outfit row is there (the one place besides her sheets her creature id may appear)")
    outfit_row = "(%s,1,1,0,4,1,0,0,3732,0,0,7711,0,0,0,0,0,0,0,'look')," % creature
    check(not named_elsewhere(taken, {"outfits_9999.sql": outfit_row}, creature), "a row of an outfit migration may carry her id")
    check(named_elsewhere(taken, {"outfits_9999.sql": "UPDATE creature_template SET npcflag=0 WHERE entry=%s;" % creature}, creature),
          "but another statement in an outfit migration may not")
    check(named_elsewhere(taken, {"monsters_9999.sql": outfit_row}, creature), "nor may an outfit row in any other migration")
    check(named_elsewhere(taken, {"outfits_9999.sql": outfit_row.replace("(%s," % creature, "(1,") + " -- item %s" % taken[0]}, creature),
          "and an outfit migration may not carry a Mystery item id at all")
    check(not named_elsewhere(taken, {n: "x,%s,y" % creature for n in PLACEMENT_FILES}, creature),
          "the hub placement files may carry her creature id")
    check(named_elsewhere(taken, {"world_hub_placements.csv": "x,%s,y" % taken[0]}, creature),
          "but not a Mystery item id")
    check(named_elsewhere(taken, {"world_0099_other.sql": "x,%s,y" % creature}, creature),
          "and no other file may carry her creature id")
    check(min(generator.EXTENDED_COST_FIRST + i for i in range(4)) > max(stock_cost_ids()), "our ExtendedCost ids start above the stock file's")


def test_refusals():
    cases = {
        "a price row kadala.csv does not have": lambda d: edit(d, "kadala_entries.csv", lambda r: r.__setitem__(0, dict(r[0], cost_rule="cost_nonsense"))),
        "an entry out of the sheet's order": lambda d: edit(d, "kadala_entries.csv", lambda r: r.reverse()),
        "a duplicate Mystery item id": lambda d: edit(d, "kadala_entries.csv", lambda r: r.__setitem__(1, dict(r[1], item_entry=r[0]["item_entry"]))),
        "a base kind base_items.csv does not have": lambda d: edit(d, "kadala_entries.csv", lambda r: r.__setitem__(9, dict(r[9], base_types="Sourcerer"))),
        "an icon item_display.csv does not have": lambda d: edit(d, "kadala_entries.csv", lambda r: r.__setitem__(0, dict(r[0], display_type="Nonsense"))),
        "a list past the core's 150": lambda d: edit(d, "kadala_entries.csv", lambda r: r.extend(dict(r[-1], item_entry=str(200000 + i)) for i in range(140))),
        "a non-numeric level": lambda d: edit(d, "kadala_npc.csv", lambda r: r.__setitem__(0, dict(r[0], level="seventy"))),
    }
    for what, mutate in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for name in ("kadala.csv", "kadala_entries.csv", "kadala_npc.csv", "account_economy.csv", "item_display.csv",
                         "base_items.csv", "class_map.csv"):
                shutil.copy(D3 / name, directory / name)
            mutate(directory)
            try:
                generator.render(directory)
            except ValueError:
                check(True, "refuses " + what)
            else:
                raise AssertionError("accepted " + what)
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        for name in ("kadala.csv", "kadala_entries.csv", "kadala_npc.csv", "account_economy.csv", "item_display.csv", "base_items.csv", "class_map.csv"):
            shutil.copy(D3 / name, directory / name)
        check(generator.render(directory) == generator.render(), "the same sheets in another folder render the same migration")


def edit(directory, name, change):
    data = rows(name, directory)
    fields = list(data[0])
    change(data)
    with (directory / name).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(data)


MUTANTS = [
    ("the price is the wrong count", "{shard}, 0, 0, 0, 0, {price}, 0,", "{shard}, 0, 0, 0, 0, {price + 1}, 0,"),
    ("the price item is not the Blood Shard", "0, 0, 0, {shard}, 0, 0, 0, 0,", "0, 0, 0, 5075, 0, 0, 0, 0,"),
    ("the list is in the wrong order", "for slot_no, e in enumerate(entries)", "for slot_no, e in enumerate(reversed(entries))"),
    ("a class entry is not bind-on-pickup", "bonding = BIND_ON_PICKUP if mask != -1 else 0", "bonding = 0"),
    ("a mixed kind is limited to the classes all its bases share", "functools.reduce(operator.or_, masks)\n    # Every", "functools.reduce(operator.and_, masks)\n    # Every"),
    ("our ExtendedCost ids collide with stock", "EXTENDED_COST_FIRST = 3000", "EXTENDED_COST_FIRST = 2997"),
    ("she is a vendor and more", "npcflag={number(npc, \"npcflag\", \"Kadala\")}", "npcflag={number(npc, \"npcflag\", \"Kadala\") | 4097}"),
    ("she keeps the donor's gossip menu", " gossip_menu_id=0,", ""),
    ("she keeps the donor's script", " ScriptName='', AIName='';", ";"),
    ("a Mystery item can be refunded", "{QUALITY_WHITE}, 0, 1, 0, 0, 0, {mask}", "{QUALITY_WHITE}, {ITEM_FLAG_PURCHASE_RECORD}, 1, 0, 0, 0, {mask}"),
    ("a Mystery item is wearable", "1, 0, 0, 0, {mask}", "1, 0, 0, 4, {mask}"),
    ("a Mystery item has a gold price", "{QUALITY_WHITE}, 0, 1, 0, 0, 0,", "{QUALITY_WHITE}, 0, 1, 500, 0, 0,"),
    ("a replay doubles her list", "DELETE FROM `npc_vendor` WHERE `entry`={entry};\n", ""),
    ("a replay doubles her items", "DELETE FROM `item_template` WHERE `entry` IN ({ids});\n", ""),
]


def test_mysql(port):
    replay = Replay(port)
    name = replay.replay(generator.render())
    facts_hold(replay, name)
    check(True, "the migration replays twice on the core's tables and every fact holds against the sheets")
    for what, old, new in MUTANTS:
        try:
            sql = mutated_generator(old, new).render()
            facts_hold(replay, replay.replay(sql))
        except (AssertionError, RuntimeError, KeyError, ValueError):
            check(True, "mutant killed: " + what)
        else:
            raise AssertionError("mutant survived: " + what)
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_files()
    test_refusals()
    isolated(test_mysql)
