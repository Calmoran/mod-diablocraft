"""diablocraft-item-descriptions: item_template.description from dc_item_tooltip.

The column is varchar(255) and a player reads it verbatim, so the generated
migration must never carry a string over the limit or a token the fill step
missed. These tests read the rows the generator EMITS, not a literal, so a
regression in the real render fails them.
"""
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_sql as g
import text_guard

BASE_ITEMS = g.MODULE_ROOT / "data" / "d3" / "base_items.csv"
MIGRATION = g.MODULE_ROOT / "data" / "sql" / "db-world" / "updates" / g.DESCRIPTION_MIGRATION
ROW = re.compile(r"^UPDATE `item_template` SET `description`=(.*) WHERE `entry`=(\d+);$")
HEX = re.compile(r"^CONVERT\(X'([0-9a-f]*)' USING utf8mb4\)$")

# Pinned: a power that cannot ship is a decision, so a new one must fail here.
POWER_TOO_LONG = {"P41_Unique_Quiver_001", "P73_Unique_Spear_001", "P74_Unique_Scythe1H_01", "Unique_Sword_2H_104_x1"}


def decode(literal):
    found = HEX.match(literal)
    if found:
        return bytes.fromhex(found.group(1)).decode("utf-8")
    assert literal.startswith("'") and literal.endswith("'"), literal
    return literal[1:-1].replace("''", "'")


class ItemDescriptions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql, cls.report = g.render_item_descriptions(BASE_ITEMS)
        cls.rows = [ROW.match(line) for line in cls.sql.splitlines() if line.startswith("UPDATE")]
        assert all(cls.rows), "every statement is a description UPDATE"
        cls.texts = [decode(row.group(1)) for row in cls.rows]

    def test_the_excluded_bases_are_exactly_the_known_ones(self):
        self.assertEqual(set(self.report["power_too_long"]), POWER_TOO_LONG)
        self.assertEqual(self.report["texts"], len(self.texts))

    def test_entries_are_unique_base_entries(self):
        entries = [int(row.group(2)) for row in self.rows]
        self.assertEqual(len(entries), len(set(entries)))
        self.assertTrue(all(entry >= g.ENTRY_BASE for entry in entries))

    def test_the_applied_file_is_the_current_render(self):
        self.assertEqual(MIGRATION.read_text(encoding="utf-8"), self.sql)

    def test_rules(self):
        power, flavour = "P" * 100, "F" * 100
        self.assertEqual(g.item_description(power, flavour), (power + "\n" + flavour, ""))
        self.assertEqual(g.item_description("P" * 200, "F" * 100), ("P" * 200, "flavour_dropped"))
        self.assertEqual(g.item_description("P" * 256, "F"), ("", "power_too_long"))
        self.assertEqual(g.item_description("", "Only flavour."), ("Only flavour.", ""))
        self.assertEqual(g.item_description("a\r\nb", ""), ("a\nb", ""))
        for bad in ("Increased by %{0}d%.", "Deals %d damage", "Deals %.1f damage", "Uses $1", "Gains {0}"):
            with self.assertRaises(text_guard.UnfilledToken, msg=bad):
                g.item_description(bad, "")
        self.assertEqual(g.item_description("Gain 50% damage; 100% weapon damage.", ""),
                         ("Gain 50% damage; 100% weapon damage.", ""))


if __name__ == "__main__":
    unittest.main()
