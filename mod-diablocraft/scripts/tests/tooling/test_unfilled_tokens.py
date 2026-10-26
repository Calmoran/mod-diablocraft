"""diablocraft-unfilled-tokens (GitHub #87): every generator that fills text refuses an unfilled token.

One helper (text_guard) holds the pattern and the message. Each guarded
generator is driven here with a planted token and must refuse, naming the token
and the source row; the real data must produce no refusal today.
"""
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_crafting as c
import generate_spells as spells
import generate_sql as g
import text_guard

REFERENCE = json.loads((c.ROOT / "reference/d3planner/data.json").read_text(encoding="utf-8"))


class SharedHelper(unittest.TestCase):
    def test_the_pattern_lives_in_one_place(self):
        self.assertFalse(hasattr(g, "UNFILLED_TOKEN"))
        self.assertFalse(hasattr(c, "UNFILLED_TOKEN"))

    def test_it_names_the_token_and_the_source_row(self):
        with self.assertRaisesRegex(text_guard.UnfilledToken, r"'\{x\}'.*row 7"):
            text_guard.refuse_unfilled("row 7", "fine", "has {x} in it")

    def test_clean_text_passes(self):
        text_guard.refuse_unfilled("row", "Gain 50% damage; 100% weapon damage.", "")


class EachGeneratorRefuses(unittest.TestCase):
    def test_item_descriptions(self):
        for planted in ("Deals %d damage", "Gains {0}", "Uses $1", "Name [Token]"):
            with self.assertRaisesRegex(text_guard.UnfilledToken, "P_ITEM"):
                g.item_description(planted, "", "P_ITEM")

    def test_item_tooltips(self):
        body = {"id": "P_TIP", "required": {"custom": {"format": "Gains %{0}d%% damage."}}, "flavor": ""}
        with self.assertRaisesRegex(text_guard.UnfilledToken, "P_TIP"):
            c.item_tooltip_rows({"items": [body]})

    def test_spell_descriptions(self):
        for planted in ("Deals {damage} damage.", "Casts [Name].", "Costs %d Fury."):
            with self.assertRaisesRegex(text_guard.UnfilledToken, "spell Bash / Onslaught"):
                spells.spell_description(planted, set(), "", "spell Bash / Onslaught")

    def test_spell_text_keeps_the_clients_own_tokens(self):
        text = "Hits ${$x1-1} enemies within $a1 yards for $s1 over $d."
        self.assertEqual(spells.spell_description(text, set(), "", "spell"), text)


class RealDataRefusesNothing(unittest.TestCase):
    def test_item_tooltips_and_descriptions(self):
        rows = c.item_tooltip_rows(REFERENCE)
        self.assertGreater(len(rows), 1000)
        for d3_id, _set, power, flavour in rows.values():
            self.assertIsNone(text_guard.find_unfilled(power, flavour), d3_id)


if __name__ == "__main__":
    unittest.main()
