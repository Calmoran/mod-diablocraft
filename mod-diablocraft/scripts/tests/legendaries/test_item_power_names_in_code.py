"""No combat code names the legendary items whose power is a row.

An item whose whole power is a `legendary_powers.csv` row must not be named in the combat code: a name there is a second place that
decides what the item does. One scan over `src/combat/*.cpp` for each of these owners (one test per item before), plus the Monk
file the Fist of Az'Turrasq also reaches. The first test fails if an owner is not a row of the sheet, so a rename cannot leave a scan looking for a
name nothing has, and the last plants a name that the scan must find.

    python mod-diablocraft/scripts/tests/legendaries/test_item_power_names_in_code.py
"""
import csv
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
OWNERS = {
    "Unique_Dagger_103_x1": (),             # Envious Blade
    "P4_Unique_Shoulder_101": (),           # Lefebvre's Soliloquy
    "P6_Unique_Ring_04": (),                # Lornelle's Sunstone
    "Unique_Boots_009_x1": (),              # Lut Socks
    "P4_Unique_Boots_001": (),              # Rivera Dancers
    "P61_Unique_Bracer_109": (),            # Spirit Guards
    "P61_Unique_Fist_009_x1": ("classes/monk/dc_monk_exploding_palm.cpp",),   # The Fist of Az'Turrasq
}


def sheet_owners():
    with (MODULE / "data/legendary_powers.csv").open(encoding="utf-8", newline="") as stream:
        return {row["owner"] for row in csv.DictReader(stream)}


def named_in(owner, text_of):
    """The names of the files in `text_of` ({name: text}) that carry the owner's id."""
    return sorted(name for name, text in text_of.items() if owner in text)


def code_of(owner):
    paths = list((SRC / "combat").glob("*.cpp")) + [SRC / extra for extra in OWNERS[owner]]
    return {p.name: p.read_text(encoding="utf-8") for p in paths}


class NamesInCode(unittest.TestCase):
    def test_every_owner_is_a_row_of_the_sheet(self):
        self.assertEqual(set(), set(OWNERS) - sheet_owners())

    def test_nothing_in_the_combat_code_names_the_item(self):
        for owner in OWNERS:
            with self.subTest(owner):
                self.assertEqual([], named_in(owner, code_of(owner)))

    def test_the_scan_finds_a_name_that_is_there(self):
        for owner in OWNERS:
            with self.subTest(owner):
                planted = dict(code_of(owner), planted="if (id == \"%s\") {}" % owner)
                self.assertEqual(["planted"], named_in(owner, planted))


if __name__ == "__main__":
    unittest.main()
