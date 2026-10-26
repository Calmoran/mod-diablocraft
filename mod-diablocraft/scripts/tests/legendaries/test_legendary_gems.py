"""diablocraft-vta6 (Legendary gems part 10a): the number columns of legendary_gems.csv
and the value-at-rank lookup.

  * every number column of the 21 gems equals d3planner's value/delta/maxlevel
    (reference/d3planner/data_gems.js, the legendaryGems table), and the text columns
    carry the same numbers, so text and numbers cannot drift;
  * the generated dc_legendary_gem rows are the CSV's, and the production rank math
    (src/common/dc_legendary_gem.h) is compiled and driven with the values parsed out
    of the generated SQL, against d3planner's own value + delta * rank;
  * mutants of that function (no max-rank clamp; rank off by one) fail the same driver.
"""
import csv
import re
import shutil
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import tempfile
import unittest
from pathlib import Path

import generate_legendary_gems

MODULE = Path(__file__).resolve().parents[3]
REPO = MODULE.parent
CSV = MODULE / "data/d3/legendary_gems.csv"
PLANNER = REPO / "reference/d3planner/data_gems.js"
GENERATED = MODULE / "data/generated/legendary_gems_0007_table.sql"
HEADER = MODULE / "src/common/dc_legendary_gem.h"
LOADER = MODULE / "src/common/dc_legendary_gem.cpp"
HARNESS = MODULE / "tests/legendary_gems/harness.cpp"
SCRATCH = REPO / "azerothcore-wotlk/build/_agent-scratch"
# Ruling 1 (ruling 2026-10-05): the gems with no numbers yet. Whisper of Atonement is not in d3planner.
OUT = {"Boon of the Hoarder", "Red Soul Shard", "Whisper of Atonement"}
GROUP_B = {"Bane of the Powerful", "Bane of the Stricken", "Bane of the Trapped", "Zei's Stone of Vengeance",
           "Taeguk", "Gogok of Swiftness", "Invigorating Gemstone"}
RANKS = (0, 1, 24, 25, 26, 49, 50, 51, 98, 99, 100, 101, 149, 150, 151, 300)


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def numbers(text):
    """Every number of a text, in order. The word "half" is 50 (Esoteric Alteration's "below half Life", 10b-4)."""
    return [50.0 if n == "half" else float(n) for n in re.findall(r"\d+(?:\.\d+)?|\bhalf\b", text.replace(",", ""))]


def planner():
    """gem name -> (id, [value...], [delta...], maxlevel or None), the effect that scales."""
    text = PLANNER.read_text(encoding="utf-8")
    text = text[text.index("DiabloCalc.legendaryGems = {"):]
    gems = {}
    for block in re.split(r"\n  \w+: \{\n    id:", text)[1:]:
        name = re.search(r'\n    name: "(.*?)"', block).group(1)
        scaling = re.search(r"value: \[([^\]]*)\],\s*delta: \[([^\]]*)\]", block)
        cap = re.search(r"\n    maxlevel: (\d+)", block)
        gems[name] = (re.search(r'"(Unique_Gem_\d+_x1)"', block).group(1),
                      [float(v) for v in scaling.group(1).split(",")],
                      [float(v) for v in scaling.group(2).split(",")],
                      int(cap.group(1)) if cap else None)
    return gems


def planner_fixed():
    """gem name -> the numbers d3planner's first effect text carries beyond its value placeholders (%.1f, %d), in order."""
    text = PLANNER.read_text(encoding="utf-8")
    text = text[text.index("DiabloCalc.legendaryGems = {"):]
    fixed = {}
    for block in re.split(r"\n  \w+: \{\n    id:", text)[1:]:
        name = re.search(r'\n    name: "(.*?)"', block).group(1)
        fmt = re.search(r'format: "(.*?)",', block).group(1).replace("%%", "")
        fixed[name] = numbers(re.sub(r"%[-+0-9.]*[a-z]", "", fmt))
    return fixed


def cell(row, column):
    return float(row[column]) if row[column] else None


class LegendaryGemNumbers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read(CSV)
        cls.d3p = planner()
        cls.live = [r for r in cls.rows if r["gem_id"]]

    def test_the_21_gems_and_no_others_have_numbers(self):
        self.assertEqual(24, len(self.rows))
        self.assertEqual(OUT, {r["gem_name"] for r in self.rows if not r["gem_id"]})
        self.assertEqual(21, len(self.live))
        for r in self.rows:
            if not r["gem_id"]:
                for c in generate_legendary_gems.NUMBERS:
                    self.assertEqual("", r[c], "%s is outside the 21 but has %s" % (r["gem_name"], c))
        self.assertEqual(set(self.d3p) - {"Boon of the Hoarder", "Red Soul Shard"},
                         {r["gem_name"] for r in self.live})

    def test_ids_are_the_gems_sheets(self):
        sheet = {r["gem_name"]: r["gem_id"] for r in read(MODULE / "data/d3/gems.csv") if r["is_legendary"] == "1"}
        for r in self.live:
            self.assertEqual(sheet[r["gem_name"]], r["gem_id"])
            self.assertEqual(self.d3p[r["gem_name"]][0], r["gem_id"])

    def test_every_number_is_d3planners(self):
        for r in self.live:
            _id, value, delta, cap = self.d3p[r["gem_name"]]
            name = r["gem_name"]
            self.assertEqual(value[0], cell(r, "base_value"), name)
            self.assertEqual(delta[0], cell(r, "per_rank"), name)
            self.assertEqual(value[1] if len(value) > 1 else None, cell(r, "base_value_2"), name)
            self.assertEqual(delta[1] if len(delta) > 1 else None, cell(r, "per_rank_2"), name)
            self.assertEqual(None if cap is None else float(cap), cell(r, "max_rank"), name)
            self.assertLessEqual(len(value), 2, name)

    def test_fixed_numbers_are_the_base_text_minus_the_scaled_ones_and_d3planners(self):
        """fixed_1..3 (10b-2): the numbers of base_effect that do not scale, in text order. The text rule and
        d3planner's own format string must give the same list, so a number cannot be typed in by hand."""
        planner_text = planner_fixed()
        for r in self.live:
            name = r["gem_name"]
            rest = numbers(r["base_effect"])
            for column in ("base_value", "base_value_2"):
                if r[column]:
                    rest.remove(float(r[column]))
            got = [float(r[c]) for c in ("fixed_1", "fixed_2", "fixed_3") if r[c]]
            self.assertEqual(rest, got, name)
            # The seven gems whose fixed numbers 10b-2's code reads. d3planner's first `format:` is not the base
            # effect for the others (Gem of Ease has none; Wildebeest's first is the rank-25 text).
            if name in GROUP_B:
                self.assertEqual(rest, planner_text[name], "%s: d3planner's text disagrees with the sheet" % name)
            # filled from the left, never with a gap
            cells = [bool(r[c]) for c in ("fixed_1", "fixed_2", "fixed_3")]
            self.assertEqual(sorted(cells, reverse=True), cells, name)

    def test_the_text_columns_carry_the_same_numbers(self):
        for r in self.live:
            name = r["gem_name"]
            base, per = numbers(r["base_effect"]), numbers(r["per_rank_scaling"])
            for column, text in (("base_value", base), ("base_value_2", base),
                                 ("per_rank", per), ("per_rank_2", per)):
                if r[column]:
                    self.assertIn(float(r[column]), text, "%s: %s is not in its text" % (name, column))
            want25 = [c for c in ("rank25_value_1", "rank25_value_2") if r[c]]
            self.assertEqual(numbers(r["rank_25_bonus"]), [float(r[c]) for c in want25], name)
            capped = re.search(r"caps at ([\d.]+)[^()]*? at rank (\d+)", r["per_rank_scaling"])
            self.assertEqual(bool(capped), bool(r["max_rank"]), "%s: the caps text and max_rank disagree" % name)
            if capped:
                self.assertEqual(int(capped.group(2)), int(r["max_rank"]), name)
                self.assertAlmostEqual(float(capped.group(1)),
                                       float(r["base_value"]) + float(r["per_rank"]) * int(r["max_rank"]), 6, name)

    def test_the_five_ruled_caps(self):
        caps = {r["gem_name"]: int(r["max_rank"]) for r in self.live if r["max_rank"]}
        # Ruling 4, alex-gem-max-ranks.png: the capped gems among the 21
        self.assertEqual({"Iceblink": 50, "Legacy of Dreams": 99, "Esoteric Alteration": 100,
                          "Mutilation Guard": 100, "Gogok of Swiftness": 150}, caps)


class LegendaryGemLookup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d3p = planner()
        cls.sql = GENERATED.read_text(encoding="utf-8")

    def sql_rows(self):
        """gem_id -> the nine columns, as written in the generated INSERT."""
        out = {}
        string = r"'(?:[^'\\]|''|\\.)*'"     # gem_name, base_effect, rank_25_bonus (2mzw)
        for tup in re.findall(r"^\('(Unique_Gem_\d+_x1)'," + ",".join([string] * 3) + r",(.*)\)[,;]$", self.sql, re.M):
            cells = [None if c == "NULL" else float(c) for c in tup[1].split(",")]
            out[tup[0]] = cells
        return out

    def test_the_generated_sql_is_the_generators_output_and_the_sheets(self):
        self.assertEqual(generate_legendary_gems.render(MODULE), self.sql)
        self.assertEqual(self.sql, (MODULE / "data/sql/db-world/updates/legendary_gems_0007_table.sql").read_text(encoding="utf-8"))
        rows = self.sql_rows()
        self.assertEqual(21, len(rows))
        for r in read(CSV):
            if r["gem_id"]:
                want = [cell(r, c) for c in generate_legendary_gems.NUMBERS]
                self.assertEqual(want, rows[r["gem_id"]], r["gem_name"])

    def test_the_loader_selects_only_columns_the_table_has(self):
        selected = re.search(r'SELECT ([a-z0-9_,]+)"\s*"([a-z0-9_,]+) FROM dc_legendary_gem',
                             LOADER.read_text(encoding="utf-8"))
        wanted = (selected.group(1) + selected.group(2)).split(",")
        create = re.search(r"CREATE TABLE IF NOT EXISTS dc_legendary_gem \((.*?)\);", self.sql).group(1)
        columns = re.findall(r"(?:^|, )([a-z0-9_]+) (?:VARCHAR|DOUBLE|INT)", create)
        columns.remove("base_effect")       # the text columns are the tooltip's (Lua reads them, 2mzw), not the loader's
        columns.remove("rank_25_bonus")
        self.assertEqual(wanted, columns)

    @classmethod
    def build(cls, header_text, name):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        files = {"dc_legendary_gem.h": header_text}
        binary = harness_env.build([HARNESS], flags=["-std=c++17", "-O1"], files=files)
        work = Path(tempfile.mkdtemp(prefix="legendary-%s-" % name, dir=str(SCRATCH)))
        return work, binary

    def drive(self, header_text, name):
        """-> {label: (driven value, d3planner's value + delta * min(rank, maxlevel))}"""
        cases, want = [], {}
        for gem_id, c in self.sql_rows().items():
            planner_gem = next(g for g in self.d3p.values() if g[0] == gem_id)
            cap = None if c[4] is None else int(c[4])
            for slot, (base, per) in enumerate(((c[0], c[1]), (c[2], c[3]))):
                if base is None:
                    continue
                for rank in RANKS:
                    label = "%s/%d/%d" % (gem_id, slot, rank)
                    cases.append("%s %r %r %s %d" % (label, base, per, "none" if cap is None else cap, rank))
                    top = rank if planner_gem[3] is None else min(rank, planner_gem[3])
                    want[label] = planner_gem[1][slot] + planner_gem[2][slot] * top
        work, binary = self.build(header_text, name)
        try:
            (work / "cases.txt").write_text("\n".join(cases) + "\n")
            run = harness_env.run([str(binary), str(work / "cases.txt")], capture_output=True, text=True)
            self.assertEqual(0, run.returncode, run.stderr)
            got = {line.split()[0]: float(line.split()[1]) for line in run.stdout.splitlines()}
            self.assertEqual(set(want), set(got))
            return got, want
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def agrees(self, got, want):
        return all(abs(got[k] - want[k]) < 1e-9 * max(1.0, abs(want[k])) for k in want)

    def test_value_at_rank_is_d3planners_for_every_gem_and_rank(self):
        got, want = self.drive(HEADER.read_text(encoding="utf-8"), "real")
        self.assertGreater(len(want), 300)
        self.assertTrue(self.agrees(got, want))
        # spot values from the sheet's own text: Esoteric 10% + 0.5% per rank caps at 60% at rank 100
        self.assertAlmostEqual(60.0, got["Unique_Gem_016_x1/0/100"])
        self.assertAlmostEqual(60.0, got["Unique_Gem_016_x1/0/300"])
        self.assertAlmostEqual(375.0, got["Unique_Gem_023_x1/0/99"])

    def test_the_mutants_fail_the_same_driver(self):
        real = HEADER.read_text(encoding="utf-8")
        no_clamp = real.replace("rank = *maxRank;", "rank = rank;")
        off_by_one = real.replace("return base + perRank * rank;", "return base + perRank * (rank + 1);")
        for name, mutant in (("no_clamp", no_clamp), ("off_by_one", off_by_one)):
            self.assertNotEqual(real, mutant, "the %s mutation no longer applies to the header" % name)
            got, want = self.drive(mutant, name)
            self.assertFalse(self.agrees(got, want), "mutant %s passed" % name)


if __name__ == "__main__":
    unittest.main()
