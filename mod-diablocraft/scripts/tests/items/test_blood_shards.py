"""diablocraft-gw9h - Kadala part 1, Blood Shards: the ledger material and its cap, executed.

What this proves, and what it does not:

  * The cap rule is the production header `src/common/dc_blood_shards.h`, compiled into a harness and
    driven with the numbers the sheet carries (`data/tunables/loot.csv` d3_value, cross-checked against
    `data/d3/kadala.csv`), never a literal. Each rule has a mutant that must turn the harness red.
  * The account's best solo level is the production statement of `RaiseAccountSolo`
    (`src/rifts/dc_gr_level.cpp`), run on a disposable MySQL against `rifts_0010_account_gr_solo.sql`:
    it only raises, it is per mode, and it survives the character's deletion. The generated world SQL
    (`account_economy_world.sql`) is replayed there too and the Blood Shard item row read back.
  * The WIRING - that `MaterialChange` and `TopUp` in `dc_account_economy.cpp` call the header and
    `ShardCap`, and the two `dc_character_gr` writes call `RaiseAccountSolo` - is checked by reading the
    code with comments removed. It is not executed: that needs a Player and a running ledger; it is the
    GM script in docs/test-kadala-blood-shards.md.
"""
import csv
import pathlib
import re
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
from test_account_economy_sql import MYSQL, ROOT, isolated

MODULE = ROOT / "mod-diablocraft"
HEADER = MODULE / "src/common/dc_blood_shards.h"
ECONOMY = MODULE / "src/common/dc_account_economy.cpp"
GR_LEVEL = MODULE / "src/rifts/dc_gr_level.cpp"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/blood_shards_test"
ENTRY = 102007


def code(path):
    """Source with comments removed, so prose cannot satisfy a wiring check."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(("//", "/*", "* ", "*/")):
            continue
        lines.append(line.split("//")[0])
    return "\n".join(lines)


def check(ok, name):
    if not ok:
        raise AssertionError(name)
    print("PASS " + name, flush=True)


def rows(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def tunable(name):
    row = next(r for r in rows(MODULE / "data/tunables/loot.csv") if r["name"] == name)
    return int(row["value"] or row["d3_value"])


def function_body(source, name):
    start = source.index(name)
    opening = source.index("{", start)
    depth, end = 1, opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[opening:end]


HARNESS = r"""
#include "dc_blood_shards.h"
#include <cstdio>
using namespace DC::BloodShards;
static int bad = 0;
static void expect(bool ok, const char* what) { if (!ok) { std::printf("FAIL %s\n", what); bad = 1; } }
int main() {
  const std::uint64_t base = BASE, per = PER, best = BEST;
  expect(Entry == ENTRY, "entry");
  expect(Cap(base, per, 0) == base, "no solo level: the base");
  expect(Cap(base, per, best) == base + per * best, "base plus per level");
  expect(Cap(base, per, 1) - Cap(base, per, 0) == per, "each level adds per");
  auto cap = Cap(base, per, best);
  auto a = Fit(0, 100, cap);                       expect(a.granted == 100 && a.lost == 0, "room: all granted");
  auto b = Fit(cap - 30, 100, cap);                expect(b.granted == 30 && b.lost == 70, "fills to the cap, rest lost");
  auto c = Fit(cap, 100, cap);                     expect(c.granted == 0 && c.lost == 100, "at the cap: nothing");
  auto d = Fit(cap + 5, 100, cap);                 expect(d.granted == 0 && d.lost == 100, "above a lowered cap: nothing, balance kept");
  auto e = Fit(cap - 100, 100, cap);               expect(e.granted == 100 && e.lost == 0, "exactly to the cap is whole");
  auto f = Fit(0, 0, cap);                         expect(f.granted == 0 && f.lost == 0, "zero credit");
  auto g = Fit(0, cap + 1, cap);                   expect(g.granted == cap && g.lost == 1, "one over the cap from empty");
  return bad;
}
"""

# (what it breaks, old text, new text) in the production header; each must turn the harness red.
MUTANTS = [
    ("cap forgets the per-level raise", "base + perLevel * bestSolo", "base"),
    ("cap adds one level too many", "base + perLevel * bestSolo", "base + perLevel * (bestSolo + 1)"),
    ("room off by one", "held >= cap ? 0 : cap - held", "held > cap ? 0 : cap - held + 1"),
    ("overflow not cut", "amount < room ? amount : room", "amount"),
    ("lost not counted", "amount - granted}", "0}"),
    ("balance above the cap underflows", "held >= cap ? 0 : cap - held", "cap - held"),
]


def run_harness(header_text, base, per, best):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "dc_blood_shards.h").write_text(header_text, encoding="utf-8")
    source = (HARNESS.replace("BASE", str(base)).replace("PER", str(per)).replace("BEST", str(best))
              .replace("ENTRY", str(ENTRY)))
    (SCRATCH / "harness.cpp").write_text(source, encoding="utf-8")
    built = subprocess.run(["g++", "-std=c++17", "-I", str(SCRATCH), str(SCRATCH / "harness.cpp"),
                            "-o", str(SCRATCH / "harness")], capture_output=True, text=True)
    if built.returncode:
        raise RuntimeError("harness did not compile:\n" + built.stderr)
    return harness_env.run([str(SCRATCH / "harness")], capture_output=True, text=True).returncode == 0


def test_data():
    kinds = {r["item_entry"]: r for r in rows(MODULE / "data/d3/account_economy.csv")}
    check(str(ENTRY) in kinds and kinds[str(ENTRY)]["kind"] == "material" and kinds[str(ENTRY)]["copper_per_item"] == "0",
          "Blood Shard is a ledger material")
    check(len({r["item_entry"] for r in kinds.values()}) == len(kinds) and
          kinds.get(str(ENTRY - 1), {}).get("kind") == "retired_gold", "its entry is the next one after the Gold Bar")
    d3 = {r["rule"]: r["value"] for r in rows(MODULE / "data/d3/kadala.csv")}
    check(tunable("blood_shard_cap_base") == int(d3["blood_shard_capacity_base"]), "cap base is kadala.csv's 500")
    check(tunable("blood_shard_cap_per_gr_level") == int(re.search(r"\d+", d3["blood_shard_capacity_increase_per_gr"]).group()),
          "cap per level is kadala.csv's 10")
    world = (MODULE / "data/generated/account_economy_world.sql").read_text(encoding="utf-8")
    # The mirror follows the newest ledger migration (0005 since Primordial Ashes); 0003 is applied and frozen.
    migration = (MODULE / "data/sql/db-world/updates/account_economy_0005_primordial_ashes.sql").read_text(encoding="utf-8")
    check(world == migration, "the generated mirror and the migration are the same file")
    check(f"({ENTRY}, 10, 0, 'Blood Shard', 7045, 1, 2048," in world, "the item row is generated, white, currency class")


def test_cap():
    base, per = tunable("blood_shard_cap_base"), tunable("blood_shard_cap_per_gr_level")
    greater_rift_max = int(next(r for r in rows(MODULE / "data/tunables/rifts.csv")
                                if r["name"] == "greater_rift_max_level")["value"])
    check(run_harness(HEADER.read_text(encoding="utf-8"), base, per, greater_rift_max),
          f"cap rule holds at the Greater Rift maximum ({base} + {per} x {greater_rift_max} = {base + per * greater_rift_max})")
    check(base + per * greater_rift_max == 1250, "the most an account can hold today is 1,250")
    text = HEADER.read_text(encoding="utf-8")
    for what, old, new in MUTANTS:
        assert text.count(old) == 1, "mutant target moved: " + old
        check(not run_harness(text.replace(old, new), base, per, greater_rift_max), "mutant killed: " + what)


def test_wiring():
    economy = code(ECONOMY)
    change = function_body(economy, "bool MaterialChange(")
    check("entry == BloodShards::Entry" in change and "!debit" in change and "BloodShards::Fit(" in change and
          "ShardCap(account, hardcore)" in change, "a Blood Shard credit goes through Fit under the account's cap")
    check(change.index("BloodShards::Fit(") < change.index("operation->Adjust({account, hardcore, entry}, grant"),
          "the cut amount is what is adjusted, not the request")
    check("*lost = fit.lost" in change and "*lost = 0" in economy[economy.index("bool MaterialChange("):], "the loss is reported")
    top_up = function_body(economy, "bool TopUp(")
    check("BloodShards::Entry" in top_up and "ShardCap(account, hardcore)" in top_up, "the tester coffer fills shards only to the cap")
    cap = function_body(economy, "uint64 ShardCap(")
    names = re.findall(r'tunable\("([a-z_]+)"\)', cap)
    check(sorted(names) == ["blood_shard_cap_base", "blood_shard_cap_per_gr_level"] and "dc_account_gr_solo" in cap,
          "ShardCap reads the two tunables and the account table")
    for name in names:
        tunable(name)
    level = code(GR_LEVEL)
    check(level.count("RaiseAccountSolo(guid,") == 2, "both beaten_solo writes raise the account's best")
    check(re.search(r"RecordGreaterRiftBeaten.*?RaiseAccountSolo\(guid, reach\.beatenSolo\)", level, re.S) is not None,
          "a recorded Greater Rift raises it by the character's best")


def test_mysql(port):
    pieces = re.findall(r'"([^"]*)"', function_body(code(GR_LEVEL), "void RaiseAccountSolo("))
    template = "".join(pieces[:2]).replace("{}", "%s")
    assert template.count("%s") == 3 and "dc_account_gr_solo" in template, "RaiseAccountSolo statement not found"
    command = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root",
               "--batch", "--raw", "--skip-column-names", "--database=blood_shards"]

    def sql(text):
        done = subprocess.run(command, input=text, text=True, capture_output=True)
        if done.returncode:
            raise RuntimeError(done.stderr)
        return done.stdout.strip()

    def raise_best(mode, level_, guid, mutant=None):
        text = template % (mode, level_, guid)
        sql(text.replace("GREATEST(beaten_solo,VALUES(beaten_solo))", mutant) if mutant else text)

    base = [str(MYSQL), "--no-defaults", "--protocol=tcp", "--host=127.0.0.1", f"--port={port}", "--user=root"]
    subprocess.run(base, input="CREATE DATABASE blood_shards CHARACTER SET utf8mb4;", text=True, check=True)
    sql("CREATE TABLE characters (guid INT PRIMARY KEY, account INT NOT NULL) ENGINE=InnoDB;"
        "INSERT INTO characters VALUES (5, 9), (6, 9);")
    sql((MODULE / "data/sql/db-characters/updates/rifts_0010_account_gr_solo.sql").read_text(encoding="utf-8"))
    sql((MODULE / "data/sql/db-characters/updates/rifts_0010_account_gr_solo.sql").read_text(encoding="utf-8"))
    best = lambda mode: sql(f"SELECT COALESCE((SELECT beaten_solo FROM dc_account_gr_solo WHERE account_id=9 AND mode='{mode}'),0)")
    check(best("normal") == "0", "the migration replays and an account starts at no solo level")
    raise_best("normal", 30, 5)
    raise_best("normal", 20, 6)
    check(best("normal") == "30", "a lower level from another character of the account does not lower it")
    raise_best("normal", 45, 6)
    check(best("normal") == "45", "a higher one raises it")
    raise_best("hardcore", 12, 5)
    check(best("hardcore") == "12" and best("normal") == "45", "each mode keeps its own best")
    sql("DELETE FROM characters WHERE guid IN (5, 6);")
    check(best("normal") == "45", "deleting the characters keeps the raise")
    raise_best("normal", 99, 77)
    check(sql("SELECT COUNT(*) FROM dc_account_gr_solo") == "2", "a guid with no character row writes nothing")
    sql("DELETE FROM dc_account_gr_solo; INSERT INTO characters VALUES (5, 9);")
    raise_best("normal", 30, 5)
    raise_best("normal", 20, 5, mutant="beaten_solo=VALUES(beaten_solo)")
    check(best("normal") != "30", "mutant killed: a plain overwrite lets a lower level lower the best")

    sql("CREATE TABLE item_template (entry INT UNSIGNED PRIMARY KEY, class TINYINT, subclass TINYINT, name VARCHAR(255), "
        "displayid INT, Quality TINYINT, Flags INT UNSIGNED, BuyCount TINYINT, BuyPrice BIGINT, SellPrice INT, "
        "InventoryType TINYINT, maxcount INT, stackable INT, BagFamily INT, Material TINYINT, bonding TINYINT, "
        "ItemLevel SMALLINT, description VARCHAR(255)) ENGINE=InnoDB;"
        "CREATE TABLE dc_account_economy_kind (item_entry INT UNSIGNED PRIMARY KEY, name VARCHAR(80), kind VARCHAR(20), "
        "copper_per_item BIGINT UNSIGNED, source VARCHAR(255)) ENGINE=InnoDB;"
        "INSERT INTO item_template (entry, name) VALUES (102006, 'Gold Bar');")
    world = (MODULE / "data/sql/db-world/updates/account_economy_0003_blood_shards.sql").read_text(encoding="utf-8")
    sql(world)
    sql(world)
    row = sql(f"SELECT class, name, displayid, Quality, stackable, BagFamily, bonding, BuyPrice, SellPrice FROM item_template WHERE entry={ENTRY}")
    check(row == "10\tBlood Shard\t7045\t1\t2147483647\t8192\t1\t0\t0", "the world migration replays and writes the item row")
    check(sql(f"SELECT kind FROM dc_account_economy_kind WHERE item_entry={ENTRY}") == "material", "and the ledger kind row")
    print("PASS isolated MySQL checks; no live database selected", flush=True)


if __name__ == "__main__":
    test_data()
    test_cap()
    test_wiring()
    isolated(test_mysql)
