"""diablocraft-2mzw: the power text of a legendary gem for its tooltip.

  * dc_legendary_gem carries base_effect (the rank-scaled number marked {v:N}, Zei's second {v2:N}) and
    rank_25_bonus, both from legendary_gems.csv's own columns. Driven the way the tooltip does: the marker
    is filled with the rank-0 number the generated row carries, and the result is the CSV's text again;
    at every rank the number keeps the per-rank decimals;
  * the generator refuses a text whose scaled number it cannot find exactly once;
  * flavour_text (a CSV column, empty for now) reaches item_template.description through
    generate_legendary_gem_items.py, gem by gem, and an empty cell leaves description ''.
"""
import csv
import re
import shutil
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_legendary_gem_items as items_gen
import generate_legendary_gems as gen

MODULE = Path(__file__).resolve().parents[3]
CSV = MODULE / "data/d3/legendary_gems.csv"
MARKER = re.compile(r"\{(v2?):(\d+)(,?)\}")


def read(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def live():
    return [r for r in read(CSV) if r["gem_id"]]


def fill(text, base, base2, per, per2, rank):
    """What the tooltip does with a marker: Value(rank) (or Value2) with the marker's decimals, thousands grouped on ','."""
    def one(m):
        base_value, per_rank = (base, per) if m.group(1) == "v" else (base2, per2)
        return format(base_value + per_rank * rank, ",.%df" % int(m.group(2)) if m.group(3) else ".%df" % int(m.group(2)))
    return MARKER.sub(one, text)


def unquote(sql_string):
    return sql_string.replace("''", "'").replace("\\\\", "\\")


def table_rows(sql):
    """gem_id -> (base_effect, rank_25_bonus, base_value, per_rank, base_value_2, per_rank_2) from the generated INSERT."""
    out = {}
    string = r"'((?:[^'\\]|''|\\.)*)'"
    pattern = re.compile(r"^\('(Unique_Gem_\d+_x1)'," + string + "," + string + "," + string + r",(.*)\)[,;]$", re.M)
    for gem_id, _name, effect, bonus, cells in pattern.findall(sql):
        c = [None if x == "NULL" else float(x) for x in cells.split(",")]
        out[gem_id] = (unquote(effect), unquote(bonus), c[0], c[1], c[2], c[3])
    return out


class PowerText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = gen.render(MODULE)
        cls.table = table_rows(cls.sql)

    def test_the_table_has_the_two_text_columns(self):
        create = re.search(r"CREATE TABLE IF NOT EXISTS dc_legendary_gem \((.*?)\);", self.sql).group(1)
        self.assertIn("base_effect VARCHAR(255) NOT NULL", create)
        self.assertIn("rank_25_bonus VARCHAR(255) NOT NULL", create)
        self.assertNotIn("flavour", self.sql)       # the designer's change: the flavour goes to item_template.description

    def test_filling_the_marker_at_rank_0_gives_the_csv_text_back(self):
        self.assertEqual(21, len(self.table))
        for r in live():
            effect, bonus, base, per, base2, per2 = self.table[r["gem_id"]]
            self.assertEqual(r["base_effect"], fill(effect, base, base2, per, per2, 0), r["gem_name"])
            self.assertEqual(r["rank_25_bonus"], bonus, r["gem_name"])      # plain text, no marker
            self.assertIsNone(MARKER.search(bonus), r["gem_name"])

    def test_one_marker_for_each_scaling_number_and_nothing_else_marked(self):
        for r in live():
            effect, _, _, _, base2, _ = self.table[r["gem_id"]]
            kinds = [m.group(1) for m in MARKER.finditer(effect)]
            self.assertEqual(["v"] if base2 is None else ["v", "v2"], kinds, r["gem_name"])
            self.assertNotIn("{", MARKER.sub("", effect), r["gem_name"])

    def test_a_rank_shows_the_per_rank_decimals(self):
        for r in live():
            effect, _, base, per, base2, per2 = self.table[r["gem_id"]]
            for m in MARKER.finditer(effect):
                step = per if m.group(1) == "v" else per2
                places = len(repr(step).partition(".")[2].rstrip("0"))
                self.assertGreaterEqual(int(m.group(2)), places, r["gem_name"])
        effect, _, base, per, _, _ = self.table["Unique_Gem_010_x1"]       # Enforcer: 15.00 +0.3 a rank
        self.assertEqual("Increase the damage of your pets by 15.00%.", fill(effect, base, None, per, None, 0))
        self.assertEqual("Increase the damage of your pets by 18.00%.", fill(effect, base, None, per, None, 10))
        effect, _, base, per, _, _ = self.table["Unique_Gem_017_x1"]       # Molten Wildebeest: thousands grouped
        self.assertEqual("Regenerates 20,000 Life per Second.", fill(effect, base, None, per, None, 10))

    def test_a_text_without_exactly_one_scaling_number_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            (module / "data/d3").mkdir(parents=True)
            for mutate in (lambda t: t.replace("by 15.00%.", "by 16.00%.", 1),     # Enforcer: base_value 15 not in the text
                           lambda t: t.replace("by 15.00%.", "by 15.00% and 15%.", 1),   # twice
                           lambda t: t.replace("by 15.00%.", "by 15%.", 1)):    # 0 decimals, per rank is 0.3
                shutil.copy(CSV, module / "data/d3/legendary_gems.csv")
                path = module / "data/d3/legendary_gems.csv"
                path.write_text(mutate(path.read_text(encoding="utf-8")), encoding="utf-8", newline="")
                with self.assertRaises(ValueError):
                    gen.render(module)

    def test_every_gem_has_a_rank_25_line_legacy_of_dreams_its_doubling(self):
        """diablocraft-5s8z6 (ruling 2026-10-12): Legacy of Dreams' Ancient doubling is its rank-25 power, so it has the
        line like every gem (reverses p3dku's exception); blanking it, or any other gem's, is refused."""
        self.assertFalse(hasattr(gen, "NO_RANK_25"))
        rows = {r["gem_id"]: r for r in read(CSV) if r["gem_id"]}
        self.assertEqual(rows["Unique_Gem_023_x1"]["rank_25_bonus"], "This bonus is doubled for Ancient items.")
        self.assertNotIn("Ancient", rows["Unique_Gem_023_x1"]["base_effect"])
        self.assertEqual([i for i, r in rows.items() if not r["rank_25_bonus"]], [])
        self.assertEqual(self.table["Unique_Gem_023_x1"][1], "This bonus is doubled for Ancient items.")
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            (module / "data/d3").mkdir(parents=True)
            path = module / "data/d3/legendary_gems.csv"
            text = CSV.read_text(encoding="utf-8")
            invigorating = ",You are immune from control impairing effects.,"
            legacy = ",This bonus is doubled for Ancient items.,"
            for name, cell in (("Invigorating blanked", invigorating), ("Legacy of Dreams blanked", legacy)):
                with self.subTest(mutant=name):
                    self.assertEqual(text.count(cell), 1)
                    path.write_text(text.replace(cell, ",,"), encoding="utf-8", newline="")
                    with self.assertRaises(ValueError):
                        gen.render(module)

class Flavour(unittest.TestCase):
    def test_the_sheet_has_a_flavour_text_column(self):
        self.assertIn("flavour_text", read(CSV)[0])

    def render(self, flavour):
        """world_sql of a sheet copy where the named gems carry flavour text."""
        with tempfile.TemporaryDirectory() as tmp:
            module = Path(tmp)
            shutil.copytree(MODULE / "data/d3", module / "data/d3")
            shutil.copy(MODULE / "data/legendary_gem_items.csv", module / "data/legendary_gem_items.csv")
            rows = read(CSV)
            for r in rows:
                r["flavour_text"] = flavour.get(r["gem_name"], "")
            with (module / "data/d3/legendary_gems.csv").open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            return items_gen.world_sql(items_gen.items(module), module)

    def test_flavour_lands_in_the_right_templates_description(self):
        sql = self.render({"Enforcer": "It's a pet's life.", "Taeguk": "Back\\slash"})
        statements = [s for s in sql.split("\n") if s.startswith("UPDATE dc_legendary_gem_template")]
        self.assertEqual(21, len(statements))
        for statement in statements:
            name = re.search(r"name='((?:[^']|'')*)',class=7", statement).group(1).replace("''", "'")
            want = {"Enforcer": "It''s a pet''s life.", "Taeguk": "Back\\\\slash"}.get(name, "")
            self.assertTrue(statement.endswith("description='%s';" % want), name)

    def test_an_empty_flavour_leaves_description_empty(self):
        sql = self.render({})
        self.assertEqual(21, sql.count("description='';"))

    def test_a_flavour_over_the_description_limit_is_dropped_whole(self):
        limit = items_gen.DESCRIPTION_LIMIT
        sql = self.render({"Enforcer": "x" * limit, "Taeguk": "x" * (limit + 1)})
        for statement in [s for s in sql.split("\n") if s.startswith("UPDATE dc_legendary_gem_template")]:
            name = re.search(r"name='((?:[^']|'')*)',class=7", statement).group(1)
            if name == "Enforcer":
                self.assertTrue(statement.endswith("description='%s';" % ("x" * limit)), name)
            elif name == "Taeguk":
                self.assertTrue(statement.endswith("description='';"), statement)


if __name__ == "__main__":
    unittest.main()
