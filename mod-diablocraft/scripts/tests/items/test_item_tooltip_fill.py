"""diablocraft-quiver-token (GitHub #93): dc_item_tooltip never carries an unfilled token.

The addon draws power_text verbatim, so generate_crafting.item_tooltip_rows must
fill every token or stop the build. These tests run the real function on the real
reference data, and a mutant that drops the guard or the %{0}d fill fails them.
"""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_crafting as c
import text_guard

REFERENCE = json.loads((c.ROOT / "reference/d3planner/data.json").read_text(encoding="utf-8"))
QUIVER = "P41_Unique_Quiver_001"
QUIVER_TEXT = (
    "Elemental Arrow gains an effect based on the rune:\r\n"
    "   Ball Lightning now travels at 30% speed.\r\n"
    "   Frost Arrow damage and Chilled duration increased by 200–250%.\r\n"
    "   Immolation Arrow ground damage over time increased by 200–250%.\r\n"
    "   Lightning Bolts damage and Stun duration increased by 200–250%.\r\n"
    "   Nether Tentacles damage and healing amount increased by 200–250%."
)


class ItemTooltipFill(unittest.TestCase):
    def test_the_quivers_filled_text_is_pinned(self):
        self.assertEqual(c.item_tooltip_rows(REFERENCE)[QUIVER][2], QUIVER_TEXT)

    def test_the_guard_refuses_an_unfilled_token(self):
        def item(power="", flavour="", **custom):
            body = {"id": "X", "required": {"custom": {"format": power, **custom}}, "flavor": flavour}
            return {"items": [body]}
        with self.assertRaisesRegex(ValueError, "Unfilled token"):
            c.item_tooltip_rows(item("Gains %{0}d%% damage."))  # no min: nothing to fill with
        with self.assertRaisesRegex(ValueError, "Unfilled token"):
            c.item_tooltip_rows(item("Plain.", "Flavour [Name]"))
        self.assertEqual(c.item_tooltip_rows(item("Gains %{0}d%%.", min=5, max=5))["X"][2], "Gains 5%.")

    def test_the_guard_fails_on_the_old_fill(self):
        """The row that failed before the fix, replayed with the old pattern."""
        import re
        custom = next(i for i in REFERENCE["items"] if i["id"] == QUIVER)["required"]["custom"]
        old = re.sub(r"%[.0-9]*[df]", "200–250", custom["format"].replace("%%", "%"))
        self.assertIsNotNone(text_guard.UNFILLED_TOKEN.search(old))


if __name__ == "__main__":
    unittest.main()
