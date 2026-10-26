"""diablocraft-wpt7l.2 - Kanai's Cube bead 2: salvage pays by quality.

What this proves, and what it does not:

  * `salvage_rules.csv` carries a `quality_id` column; a non-crafted Legendary and Set item pays 3 Forgotten Souls when
    Ancient and 55 Primordial Ashes when Primal (the second source is `rarity_tiers.csv`'s display text for the two
    tiers, matched by material name), and every other row pays as before under quality `normal`.
  * The generated `dc_salvage_rule` table (data/generated/crafting.sql and the newest crafting migration) holds those
    rows with the quality in its key.
  * `Salvage` in dc_crafting.cpp reads the item's quality (shell or identified) through `SalvageQuality` and puts it in
    the rule query; each source check is also run on a reverted copy of the source and must then fail.
  * The pure rule `SalvageQuality` (a crafted item never pays by quality) is compiled and run in
    `tests/security_world/gate_harness.cpp`, which test_security_world.py builds.
  * NOT covered: Salvage itself against a database (it needs the live core), and the in-game receipt: the designer's Checks.
"""
import re
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import crafting_source  # noqa: E402
import generate_crafting as crafting

MODULE = Path(__file__).resolve().parents[3]
ASHES, SOUL = 102013, 102004


def read(path):
    return (MODULE / path).read_text(encoding="utf-8")


def function_body(source, marker):
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def wiring_problems(source):
    problems = []
    body = function_body(source, "void Salvage(Player* player")
    if "dc_salvage_rule WHERE rarity='{}' AND crafted={} AND quality='{}'" not in body:
        problems.append("the rule query does not key on quality")
    shell, rolled = body.split("auto instance = Rolled(item);")
    if "SalvageQuality(false, shell->qualityTier)" not in shell:
        problems.append("a shell does not pay by its quality")
    if "SalvageQuality(crafted, instance.qualityTier)" not in rolled.split("auto rows")[0]:
        problems.append("an identified item does not pay by its quality")
    return problems


class SalvageQualityTests(unittest.TestCase):
    def rows(self):
        return {(r, c, q, e): (lo, hi) for r, c, q, e, lo, hi in crafting.salvage_rows()}

    def test_ancient_and_primal_pay_their_own_materials(self):
        rows = self.rows()
        for rarity in ("legendary", "set"):
            self.assertEqual(rows[(rarity, 0, "ancient", SOUL)], (3, 3))
            self.assertEqual(rows[(rarity, 0, "primal", ASHES)], (55, 55))
            for quality in ("ancient", "primal"):
                paid = [k for k in rows if k[:3] == (rarity, 0, quality)]
                self.assertEqual(len(paid), 1, (rarity, quality))

    def test_only_non_crafted_legendary_and_set_have_a_quality_row(self):
        for rarity, crafted, quality, _ in self.rows():
            if quality != "normal":
                self.assertIn((rarity, crafted), {("legendary", 0), ("set", 0)})

    def test_amounts_match_the_second_source(self):
        names = {int(r["item_entry"]): r["name"] for r in crafting.read("account_economy.csv")}
        text = {r["rarity"].split(" (")[0].lower(): r["salvage_result"] for r in crafting.read("rarity_tiers.csv")}
        for (rarity, crafted, quality, entry), (lo, hi) in self.rows().items():
            if quality != "normal":
                self.assertEqual(lo, hi)
                self.assertTrue(text[quality].startswith(f"{lo} {names[entry]}"), (quality, text[quality]))

    def test_generated_table_keys_on_quality(self):
        generated = read("data/generated/crafting.sql")
        self.assertIn("quality VARCHAR(16)", generated)
        self.assertIn("PRIMARY KEY(rarity,crafted,quality,item_entry)", generated)
        updates = MODULE / "data/sql/db-world/updates"
        newest = max(updates.glob("crafting_*_crafting_tunables.sql"), key=lambda p: int(p.name.split("_")[1]))
        for text in (generated, newest.read_text(encoding="utf-8")):
            self.assertIn(f"INSERT INTO `dc_salvage_rule` VALUES ('legendary',0,'ancient',{SOUL},3,3);", text)
            self.assertIn(f"INSERT INTO `dc_salvage_rule` VALUES ('set',0,'primal',{ASHES},55,55);", text)

    def test_salvage_reads_the_items_quality(self):
        source = crafting_source.source()
        self.assertEqual(wiring_problems(source), [])

    def test_each_wiring_check_fails_on_a_reverted_copy(self):
        source = crafting_source.source()
        for old, new in (("AND crafted={} AND quality='{}'", "AND crafted={}"),
                         ("SalvageQuality(false, shell->qualityTier)", "std::string(\"normal\")"),
                         ("SalvageQuality(crafted, instance.qualityTier)", "std::string(\"normal\")")):
            self.assertIn(old, source)
            self.assertTrue(wiring_problems(source.replace(old, new)), old)


if __name__ == "__main__":
    unittest.main()
