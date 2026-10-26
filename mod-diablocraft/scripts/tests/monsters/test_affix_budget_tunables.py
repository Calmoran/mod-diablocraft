"""diablocraft-geyf (GitHub #58): item affix budgets and dual-wield IAS are data.

What runs: the module's own `CountsFor` (dc_items_roll.cpp) and `DualWieldIas`
(dc_stats.cpp), cut out of the source and compiled against a `Tunables::Get`
that answers from the rows `generate_tunables.read_all` produces - the value the
generator emits, not a literal typed here. Then the table is moved and the
answers must move with it. A reverted (literal) source cannot do that, and
`test_a_reverted_source_is_caught` plants exactly that to prove the check fails.

What it does not run: `RefreshWeapon` (needs a Player) - a source guard pins that
it calls DualWieldIas(). Nothing here says how the running server behaves; the
C++ is held for the next update's binary.
"""
import csv
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import items_source  # noqa: E402
import harness_env
from generate_tunables import MODULE_ROOT, read_all

MODULE = MODULE_ROOT
REPO = MODULE.parent
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch/affix_budgets"
ITEMS = items_source.read("dc_items_roll.cpp")
STATS = (MODULE / "src/stats/dc_stats.cpp").read_text(encoding="utf-8")
HARNESS = MODULE / "tests/affix_budgets/harness.cpp"
WANTED = {("loot", "magic_primary_affixes"), ("loot", "magic_secondary_affixes"),
          ("loot", "full_roll_primary_affixes"), ("loot", "full_roll_secondary_affixes"),
          ("combat", "dual_wield_ias_pct")}


def definition(marker, source):
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def generated_table():
    """{(category, name): value} exactly as dc_tunables would answer Get()."""
    table = {}
    for category, name, d3, tuned, *_ in read_all(MODULE):
        if (category, name) in WANTED:
            table[(category, name)] = tuned if tuned is not None else d3
    assert set(table) == WANTED, "the generator does not emit every row: %s" % (WANTED - set(table))
    return table


def extracts(items=ITEMS, stats=STATS):
    return ("#include <string>\nnamespace DC::Items\n{\nstruct Counts { unsigned primary = 0, secondary = 0; };\n"
            + definition("Counts CountsFor(std::string const& rarity)", items) + "\n}\n",
            "namespace DC::Stats\n{\n" + definition("double DualWieldIas()", stats) + "\n}\n")


def run(table, items=ITEMS, stats=STATS, tag="run"):
    folder = SCRATCH / tag
    folder.mkdir(parents=True, exist_ok=True)
    items_h, stats_h = extracts(items, stats)
    (folder / "dc_items_extract.h").write_text(items_h, encoding="utf-8")
    (folder / "dc_stats_extract.h").write_text(stats_h, encoding="utf-8")
    rows = ",\n".join('    {"%s", "%s", %r}' % (c, n, float(v)) for (c, n), v in sorted(table.items()))
    (folder / "generated_table.h").write_text(
        "struct Row { char const* category; char const* name; double value; };\n"
        "static Row const kTable[] = {\n" + rows + "\n};\n", encoding="utf-8")
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    binary = folder / "harness"
    built = subprocess.run([compiler, "-std=c++17", "-I", str(folder), "-o", str(binary), str(HARNESS)],
                           capture_output=True, text=True)
    assert built.returncode == 0, "the harness did not compile:\n" + built.stderr[-4000:]
    out = harness_env.run([str(binary)], capture_output=True, text=True, check=True).stdout
    result = {}
    for line in out.splitlines():
        parts = line.split()
        result[parts[1] if parts[0] == "counts" else "dual"] = tuple(float(p) for p in parts[2:]) \
            if parts[0] == "counts" else float(parts[1])
    return result


class AffixBudgetTests(unittest.TestCase):
    def test_generated_values_reproduce_todays_literals(self):
        got = run(generated_table(), tag="baseline")
        for rarity in ("rare", "legendary", "set", "ethereal", "normal", "empty"):
            self.assertEqual(got[rarity], (4.0, 2.0), rarity)
        self.assertEqual(got["magic"], (1.0, 1.0))
        self.assertEqual(got["dual"], 15.0)

    def test_moving_the_generated_table_moves_the_compiled_answer(self):
        table = generated_table()
        moved = {key: value + 3 for key, value in table.items()}
        got = run(moved, tag="moved")
        self.assertEqual(got["magic"], (4.0, 4.0))
        self.assertEqual(got["rare"], (7.0, 5.0))
        self.assertEqual(got["legendary"], (7.0, 5.0))
        self.assertEqual(got["dual"], 18.0)

    def test_a_reverted_source_is_caught(self):
        """Put the literals back: the moved-table check above must then fail."""
        items = ITEMS.replace(
            definition("Counts CountsFor(std::string const& rarity)", ITEMS),
            'Counts CountsFor(std::string const& rarity)\n{\n    if (rarity == "magic") return {1, 1};\n'
            '    return {4, 2};\n}')
        stats = STATS.replace(definition("double DualWieldIas()", STATS),
                              "double DualWieldIas() { return 15.0; }")
        self.assertNotEqual(items, ITEMS)
        self.assertNotEqual(stats, STATS)
        moved = {key: value + 3 for key, value in generated_table().items()}
        got = run(moved, items, stats, tag="reverted")
        self.assertEqual(got["dual"], 15.0)            # did not move: the check would fail
        self.assertEqual(got["rare"], (4.0, 2.0))
        self.assertNotEqual(got["rare"], (7.0, 5.0))

    def test_sources_are_pinned(self):
        with (MODULE / "data/d3/stats.csv").open(encoding="utf-8-sig", newline="") as stream:
            row = next(r for r in csv.DictReader(stream) if r["stat"] == "Attack Speed")
        self.assertEqual(row["dual_wield_ias_pct"], "15")
        self.assertIn("15% IAS", row["how_it_stacks"])
        with (MODULE / "data/d3/rarity_tiers.csv").open(encoding="utf-8-sig", newline="") as stream:
            rare = next(r for r in csv.DictReader(stream) if r["rarity"] == "Rare")
        self.assertEqual((rare["primary_affix_max"], rare["secondary_affix_max"]), ("4", "2"))
        self.assertIn("up to 4", rare["primary_affixes"])
        self.assertIn("up to 2", rare["secondary_affixes"])
        with (MODULE / "data/tunables/loot.csv").open(encoding="utf-8-sig", newline="") as stream:
            loot = {r["name"]: r for r in csv.DictReader(stream)}
        for name in ("magic_primary_affixes", "magic_secondary_affixes"):
            self.assertEqual(loot[name]["value"], "1")
            self.assertEqual(loot[name]["d3_value"], "")
            self.assertIn("NOT a D3 number", loot[name]["notes"])

    def test_the_callers_use_the_functions_not_literals(self):
        refresh = definition("void RefreshWeapon(Player* player)", STATS)
        self.assertIn("DualWieldIas()", refresh)
        self.assertIsNone(re.search(r"\b15(\.0)?\b", refresh))
        self.assertNotIn("DUAL_WIELD_IAS", STATS)
        self.assertIn("CountsFor(base.rarity)", ITEMS)
        counts = definition("Counts CountsFor(std::string const& rarity)", ITEMS)
        self.assertIsNone(re.search(r"return \{\s*\d", counts))


if __name__ == "__main__":
    unittest.main()
