"""diablocraft-0189: the 21 legendary gem items have a row in the client's Item.dbc, so the bag shows an icon.

The 3.3.5a client takes an item's icon from its own Item.dbc (client-patch/dbc/README.md), and a miss is a "?".
Cross-source: the entries come from legendary_gem_items.csv through the generator, the look from gem_icons.csv
(diablocraft-fpo9l: each gem its own icon, no longer the donor's), and the icon string from ItemDisplayInfo.dbc.
The committed patch-4.MPQ must carry the same Item.dbc, or the fix never reaches the client.
"""
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import generate_gem_icons
import generate_legendary_gem_items as gen

REPO = Path(__file__).resolve().parents[4]
DBC = REPO / "client-patch/dbc"


def item_rows(data):
    _, records, _, size, _ = struct.unpack("<4sIIII", data[:20])
    return {struct.unpack_from("<I", data, 20 + n * size)[0]: struct.unpack_from("<IIIiiIII", data, 20 + n * size)
            for n in range(records)}


def icon_of(display):
    data = (DBC / "ItemDisplayInfo.dbc").read_bytes()
    _, records, fields, size, _ = struct.unpack("<4sIIII", data[:20])
    strings = data[20 + records * size:]
    for n in range(records):
        row = struct.unpack_from("<" + "I" * fields, data, 20 + n * size)
        if row[0] == display:
            return strings[row[5]:strings.index(b"\0", row[5])].decode()
    return None


class LegendaryGemItemDbc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = item_rows((DBC / "Item.dbc").read_bytes())
        cls.gems = gen.items()

    def test_every_gem_has_a_row_with_its_own_look_and_icon(self):
        looks = {entry: display for entry, display, _icon in generate_gem_icons.rows()}
        self.assertEqual(21, len(self.gems))
        for gem_id, _name, entry, _slots in self.gems:
            self.assertTrue(entry in self.rows, f"{gem_id}: no Item.dbc row for entry {entry}")
            row = self.rows[entry]
            self.assertEqual((7, 4, 0), (row[1], row[2], row[6]), gem_id)  # gem, not equippable
            self.assertEqual(looks[entry], row[5], gem_id)
            self.assertEqual(f"DC_Gem_{gem_id}", icon_of(row[5]), gem_id)

    def test_the_committed_archive_carries_this_item_dbc(self):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["smpq", "-x", str(REPO / "client-patch/patch-4.MPQ"), "DBFilesClient/Item.dbc"],
                           cwd=tmp, check=True, capture_output=True)
            packed = (Path(tmp) / "DBFilesClient/Item.dbc").read_bytes()
        self.assertEqual((DBC / "Item.dbc").read_bytes(), packed)


if __name__ == "__main__":
    unittest.main()
