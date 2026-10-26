"""diablocraft-dm9vg.8 - the act legendaries come only from the Horadric Cache (the designer, decisions 2026-10-12 (1)).

Every legendary in a cache pool (`dc_bounties_cache_legendary`, from bounty_cache_legendaries.csv) is out of
every other source:

  * Drops: kills, chests, the rift and GR guardians, the act-boss first kill and Kadala's gamble all pick
    through PickBaseItem, which reads only the pools the loader fills behind DC::RollClass::InDropPool.
    The production header is compiled and fed every dc_base_item row of the generated base_items.sql with
    the cache flag taken from the generated bounties_0003_caches.sql rows. The loader's query and call are
    read with comments removed (not executed: that needs the world database).
  * The slot vendors: test_slot_vendors compares every list with the wear-mask set less the cache pools' items.
  * The Blacksmith (rare outputs from generic bases only, a catalogue that names none of them) and the
    class starter kits (no legendary kit row of their type).
Each rule has named mutants that must turn it red.

    python3 mod-diablocraft/scripts/tests/items/test_cache_only_legendaries.py
"""
import csv
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
from test_class_roll_rules import code, sql_rows  # noqa: E402
from test_slot_vendors import check, mutate, rows, squash  # noqa: E402

MODULE = pathlib.Path(__file__).resolve().parents[3]
ROOT = MODULE.parent
D3 = MODULE / "data/d3"
GENERATED = MODULE / "data/generated"
HEADER = MODULE / "src/items/dc_roll_class.h"
LOOT = MODULE / "src/loot/dc_loot.cpp"
SCRATCH = ROOT / "azerothcore-wotlk/build/_agent-scratch/cache_only_legendaries"

DRIVER = r"""
#include "dc_roll_class.h"
#include <iostream>
#include <sstream>
#include <string>
int main()
{
    std::string line;
    while (std::getline(std::cin, line))
    {
        std::istringstream in(line);
        std::string entry, rarity, pool, craft, cache;
        std::getline(in, entry, '\t'); std::getline(in, rarity, '\t'); std::getline(in, pool, '\t');
        std::getline(in, craft, '\t'); std::getline(in, cache, '\t');
        if (DC::RollClass::InDropPool(rarity, pool, craft, cache))
            std::cout << entry << "\n";
    }
}
"""

HEADER_MUTANTS = [
    ("the cache flag is ignored", 'if (cacheOnly == "yes") return false;', ""),
    ("the cache flag is read as another word", 'if (cacheOnly == "yes") return false;', 'if (cacheOnly == "true") return false;'),
]

CALL = ("DC::RollClass::InDropPool(rarity, fields[7].Get<std::string>(), fields[8].Get<std::string>(), "
        "fields[11].Get<std::string>())")
JOIN = "LEFT JOIN (SELECT DISTINCT item_entry FROM dc_bounties_cache_legendary) c ON c.item_entry=b.entry"
FLAG = "IF(c.item_entry IS NULL,'no','yes')"
LOOT_MUTANTS = [
    ("the loader passes no cache flag", "fields[11].Get<std::string>())", '"no")'),
    ("the loader passes another column", "fields[11].Get<std::string>())", "fields[10].Get<std::string>())"),
    ("the query reads no cache pool", JOIN, ""),
    ("the flag says yes for every row", FLAG, "'yes'"),
]


def cache_entries():
    """The cache pools' items, as the generated world rows carry them."""
    return {int(r["item_entry"]) for r in sql_rows(GENERATED / "bounties_0003_caches.sql", "dc_bounties_cache_legendary")}


def bases():
    return sql_rows(GENERATED / "base_items.sql", "dc_base_item")


def droppable(header_text, strict=True):
    """Entries the compiled InDropPool admits, fed every base row with its generated cache flag."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "dc_roll_class.h").write_text(header_text, encoding="utf-8")
    (SCRATCH / "driver.cpp").write_text(DRIVER, encoding="utf-8")
    flags = ["-Wall", "-Wextra", "-Werror"] if strict else []
    built = subprocess.run(["g++", "-std=c++17", *flags, "-I", str(SCRATCH), str(SCRATCH / "driver.cpp"),
                            "-o", str(SCRATCH / "driver")], capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("the InDropPool driver did not compile:\n" + built.stderr[-4000:])
    cache = cache_entries()
    feed = "".join("%s\t%s\t%s\t%s\t%s\n" % (r["entry"], r["rarity"], r["pool_version"], r["craft_only"],
                                             "yes" if int(r["entry"]) in cache else "no") for r in bases())
    ran = harness_env.run([str(SCRATCH / "driver")], input=feed, capture_output=True, text=True)
    if ran.returncode:
        raise AssertionError("the driver failed:\n" + ran.stderr)
    return {int(line) for line in ran.stdout.split()}


def drop_problems(admitted):
    cache = cache_entries()
    problems = [f"{e} can drop" for e in sorted(cache & admitted)]
    # Every other pool legendary still drops: the rule takes out the cache's items and nothing else.
    others = {int(r["entry"]) for r in bases() if r["rarity"] == "legendary" and r["pool_version"] == "yes"
              and r["craft_only"] != "yes" and int(r["entry"]) not in cache}
    problems += [f"{e} no longer drops" for e in sorted(others - admitted)]
    return problems


def test_drops():
    cache = cache_entries()
    check(cache == {100089, 100570, 100950, 100951}, "the cache pools hold the four act legendaries (generated rows)")
    text = HEADER.read_text(encoding="utf-8")
    check(not drop_problems(droppable(text)), "the compiled InDropPool admits none of the four and every other pool legendary")
    for what, old, new in HEADER_MUTANTS:
        check(bool(drop_problems(droppable(mutate(text, old, new), strict=False))), "mutant killed: " + what)


def select_columns(query):
    """The SELECT list split at top-level commas."""
    body = query[query.index("SELECT") + 6:query.index(" FROM dc_base_item b")]
    out, depth, cell = [], 0, ""
    for ch in body:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            out.append(cell.strip())
            cell = ""
        else:
            cell += ch
    return out + [cell.strip()]


def loot_problems(text):
    problems = []
    if text.count("DC::RollClass::InDropPool(") != 1 or CALL not in text:
        problems.append("the loader's one InDropPool call does not pass column 11")
    found = re.search(r'WorldDatabase\.Query\(\s*((?:"[^"]*"\s*)+)\);\s*if \(!items\)', text)
    query = "".join(re.findall(r'"([^"]*)"', found.group(1))) if found else ""
    if JOIN not in query:
        problems.append("the base-item query does not join the cache pools")
    columns = select_columns(query) if "SELECT" in query and " FROM dc_base_item b" in query else []
    if len(columns) != 12 or columns[11] != FLAG:
        problems.append("column 11 is not the cache flag")
    if text.count("uniques = std::move(") != 1 or text.count("FROM dc_base_item b") != 1:
        problems.append("a second path fills the drop pools")
    return problems


def test_loader():
    text = squash(code(LOOT))
    check(not loot_problems(text), "the loader joins the cache pools and passes the flag to InDropPool, its one gate")
    for what, old, new in LOOT_MUTANTS:
        check(bool(loot_problems(mutate(text, old, new))), "mutant killed: " + what)


def test_other_sources():
    cache = cache_entries()
    named = {r["d3_name"] for r in bases() if int(r["entry"]) in cache}
    types = {r["type"] for r in bases() if int(r["entry"]) in cache}
    check({r["base_rarity"] for r in rows(D3 / "blacksmith_rules.csv")} == {""},
          "the Blacksmith's rules make outputs from generic bases only")
    catalog = (D3 / "blacksmith_catalog.csv").read_text(encoding="utf-8")
    check(not any(n in catalog for n in named) and not any(re.search(rf"\b{e}\b", catalog) for e in cache),
          "the Blacksmith's catalogue names none of the four")
    kits = re.findall(r"INSERT INTO dc_class_starter_kit VALUES \(\d+,'\w+','legendary',\d+,'([^']*)'",
                      (GENERATED / "class_starts.sql").read_text(encoding="utf-8"))
    check(kits and all(k and k not in types for k in kits), "no starter kit legendary row can pick one (by type)")


if __name__ == "__main__":
    test_drops()
    test_loader()
    test_other_sources()
    print("PASS all")
