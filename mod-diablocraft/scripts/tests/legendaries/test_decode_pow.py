"""diablocraft-npxrh (legendary build bead 0b): the D3 .pow decoder (decode_pow.py).

  * the formula stack machine and the tag-id -> SF_n -> label rule, on a .pow built in the test (no MPQ needed);
  * against the real client data (skipped, loudly, when reference/blizzless-diiis or smpq is absent):
      - known numbers decode: Overpower SF_7 'Base: Radius' = 9 and SF_15 = 50 (placeholder-values-d3-data.md),
        Band of Hollow Whispers' five labelled constants (the catalogue named 12, 40, 30 and two 1s but not the labels);
      - cross-source: every simple `ProcCoefficient` in docs/research/proc-coefficients.csv (read by another decoder in
        2026-09) equals the one this decoder reads;
      - an item's attribute 1293 reaches its Power file (Vigilance 0.05 -> sanctuary labels);
      - the 46 catalogue rows named in decode_pow.ROWS (the ones that had no chance / no number) all get a row, and the committed
        docs/research/legendary-pow-data.csv is what the script prints now.
"""
import csv
import io
import re
import struct
import unittest
from contextlib import redirect_stdout
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import decode_pow as D

REPO = Path(__file__).resolve().parents[4]
needs_mpq = unittest.skipUnless(D.available(), "reference/blizzless-diiis (main checkout) or /usr/bin/smpq is absent")


def f32(x):
    return struct.unpack("<i", struct.pack("<f", x))[0]


def build_pow(sno, labels, sf_values):  # sf_values: {tag id: formula text}
    """A minimal .pow: the General tag map holds one type-4 entry per SF_n in sf_values, the details list the labels."""
    d = bytearray(5000)
    struct.pack_into("<i", d, 16, sno)
    entries = b""
    for tag, text in sf_values.items():
        raw = text.encode() + b"\0"
        pad = {0: 0, 1: 3, 2: 2, 3: 1}[len(text) % 4]
        op = b"\x06\0\0\0" + struct.pack("<f", float(text)) + b"\0\0\0\0"
        entries += struct.pack("<ii", 4, tag) + struct.pack("<8i", 0, 0, 0, 0, 0, len(text), 0, len(op)) + raw + b"\0" * pad + op
    entries += struct.pack("<iii", 0, 329983, 1)  # a type-0 tag, so non-formula entries are skipped
    blob = struct.pack("<i", len(sf_values) + 1) + entries
    at = 1400
    d[at:at + len(blob)] = blob
    struct.pack_into("<ii", d, 112, at - 16, len(blob))
    details = b"".join(l.encode().ljust(256, b"\0") + b"\0" * 512 + struct.pack("<ii", 0, i) for i, l in enumerate(labels))
    d[at + len(blob) + 16: at + len(blob) + 16 + len(details)] = details
    struct.pack_into("<ii", d, 1088, at + len(blob), len(details))
    return bytes(d)


class Formula(unittest.TestCase):
    def test_constant_range_divide(self):
        self.assertEqual(D.evaluate([6, f32(0.05), 0]), (f32_back(0.05),) * 2)
        # RandomIntMinMax(70, 85) / 100, the shape of '+[70-85]%'
        lo, hi = D.evaluate([6, f32(70), 6, f32(85), 1, 4, 6, f32(100), 14, 0])
        self.assertAlmostEqual(lo, 0.7)
        self.assertAlmostEqual(hi, 0.85)
        # RandomIntMinRange(3, 2) is 3..5
        self.assertEqual(D.evaluate([6, f32(3), 6, f32(2), 1, 3, 0]), (3.0, 5.0))

    def test_attribute_read_is_not_a_number(self):
        self.assertIsNone(D.evaluate([5, 107, 0, 0, 0, 0]))


def f32_back(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


class Layout(unittest.TestCase):
    def test_sf_index_is_tag_offset_and_label_is_list_position(self):
        p = D.parse_power(build_pow(77, ["a", "b", "c", "d"], {266512: "40", 266544: "12", 266832: "50"}))
        self.assertEqual(p["sno"], 77)
        self.assertEqual(p["labels"], ["a", "b", "c", "d"])
        # the tens digit steps the tag by 256, not 160: tag 266832 is SF_15
        self.assertEqual(p["sf"], {1: "40", 3: "12", 15: "50"})
        self.assertEqual(p["tags"], {329983: 1})


@needs_mpq
class RealData(unittest.TestCase):
    def test_overpower_known_numbers(self):
        p = D.parse_power(D.extract("Power/Barbarian_Overpower.pow"))
        self.assertEqual((p["labels"][7], p["sf"][7]), ("Base: Radius", "9"))
        self.assertEqual((p["labels"][15], p["sf"][15]), ("B: Projectile Search Radius", "50.0"))

    def test_band_of_hollow_whispers_labels(self):
        p = D.parse_power(D.extract("Power/ItemPassive_Unique_Ring_001_x1.pow"))
        got = {p["labels"][n]: v for n, v in p["sf"].items()}
        self.assertEqual(got, {"pulse frequency": "1", "dot damage": "40", "Internal coolup/down": "1",
                               "dot duration": "12", "Haunt Search Radius": "30"})

    def test_proc_coefficients_match_the_2026_09_research(self):
        checked = 0
        for r in csv.DictReader(open(REPO / "docs/research/proc-coefficients.csv", encoding="utf-8")):
            m = re.match(r"(\w+\.pow) \(GTM ProcCoefficient = '([0-9.]+)'\)$", r["source"])
            if not m:
                continue
            p = D.parse_power(D.extract("Power/" + m.group(1)))
            self.assertAlmostEqual(float(p["tags"][D.TAG_PROC_COEFFICIENT]), float(m.group(2)), msg=r["source"])
            checked += 1
        self.assertGreater(checked, 20)

    def test_item_attribute_reaches_its_power(self):
        sno_map = D.power_by_sno()
        attrs = D.items()["Unique_Polearm_001_x1"]
        a = next(a for a in attrs if a[0] == D.ATTR_ITEM_POWER_PASSIVE)
        self.assertAlmostEqual(D.evaluate(a[2])[0], 0.05, places=6)
        rep = D.power_report(sno_map, a[1])
        self.assertEqual(rep["file"], "ItemPassive_Unique_Polearm_001_x1.pow")
        self.assertIn(("sanctuary duration", "5"), [(l, t) for _, l, t in rep["sf"]])

    def test_rows_cover_the_46_and_the_csv_is_current(self):
        out = io.StringIO()
        with redirect_stdout(out):
            D.cmd_rows()
        rows = list(csv.DictReader(io.StringIO(out.getvalue())))
        self.assertEqual(len(rows), 46)
        self.assertEqual(sum(1 for r in rows if not r["power_file"]), 0)
        committed = (REPO / "docs/research/legendary-pow-data.csv").read_text(encoding="utf-8")
        self.assertEqual(committed, out.getvalue())


if __name__ == "__main__":
    unittest.main()
