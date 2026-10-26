#!/usr/bin/env python3
"""diablocraft-xnrvn.9: the Shaman's two Maelstrom item lines reach the character sheet.

The Totem's "Primary skills generate +1-3 Maelstrom" (affix `primarymaelstrom`) and the Ritual Mace's "Maelstrom generation
+5-10%" (affix `maelstromgen`) are lines the Shaman 1b pools could not hold until Shaman 2b appended `Stat::PrimaryMaelstrom` and
`Stat::MaelstromGeneration` to the sheet. What runs: Mappings(), Applies() and Apply's own gate and value lines cut out of
dc_items_data.cpp and dc_items_equip.cpp and compiled against the real dc_common.cpp (the harness of test_preset_stat_mappings),
fed every value of the line's rows in class_item_pools.csv: a worn line adds that value to its stat and to no other, for every
class, and the sheet save keeps it. Single-rule mutants of the two rows. Not covered: the Shaman's reader of the two stats
(src/classes/shaman/dc_shaman_maelstrom.cpp, Combat's and the Classes lane's tests) and the roll itself
(test_shaman_class_items.py).
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402
import items_source  # noqa: E402
import test_preset_stat_mappings as base  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
LINES = {"primarymaelstrom": ("PrimaryMaelstrom", "offhand:Totem"), "maelstromgen": ("MaelstromGeneration", "onehand:Ritual Mace")}
MAIN = r"""
int main(int argc, char** argv)
{
    if (argc < 3) return 2;
    std::string const code = argv[1];
    Stat const target = code == "primarymaelstrom" ? Stat::PrimaryMaelstrom : Stat::MaelstromGeneration;
    Player player;
    BaseStats base;
    base.level = 70; base.strength = 100; base.vitality = 100; base.baseArmor = 100;
    base.baseLife = 1000; base.lifePerVitality = 10; base.maxFury = 100;
    std::vector<Contribution> gear{{Source::Items, Stat::AllResistance, 1, 300}};
    StatSheet const bare = Calculate(base, gear);
    std::vector<std::uint32_t> classes{0};
    for (auto const& row : Resources::Data::Rows) classes.push_back(row.classId);
    for (int arg = 2; arg < argc; ++arg)
    {
        double const value = std::atof(argv[arg]);
        for (std::uint32_t cls : classes)
        {
            Classes::worn = cls;
            std::vector<Contribution> worn = gear;
            for (Contribution const& c : Items::Worn(&player, code, value)) worn.push_back(c);
            Check(worn.size() == gear.size() + 1, "the line adds one contribution on every class");
            StatSheet const sheet = Calculate(base, worn);
            Check(Near(sheet[target], bare[target] + value), "the line adds its value to its stat");
            for (unsigned stat = 0; stat < StatCount; ++stat)
                if (stat != Index(target))
                    Check(Near(sheet.values[stat], bare.values[stat]), "and to no other stat");
            Check(Near(DeserializeSheet(Serialize(sheet))[target], bare[target] + value), "the sheet save keeps it");
        }
    }
    return failures;
}
"""


def values(code):
    slot = LINES[code][1]
    with (MODULE / "data/d3/class_item_pools.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = [r for r in csv.DictReader(stream) if r["affix_id"] == code]
    assert rows and {r["slot"] for r in rows} == {slot}, (code, rows)
    return sorted({float(r[key]) for r in rows for key in ("value_min", "value_max")})


def build(items, folder):
    resources = base.RESOURCES.read_text(encoding="utf-8")
    head = base.program(items, resources).split("int main(int argc, char** argv)", 1)[0]
    cpp, binary = Path(folder) / "t.cpp", Path(folder) / "t"
    cpp.write_text(head + MAIN, encoding="utf-8")
    built = base.subprocess.run([base.CXX, "-std=c++17", "-O1", "-UNDEBUG", "-I", str(base.SRC / "common"), "-I", str(base.SRC / "classes"),
                                 "-I", str(base.SRC / "stats"), "-o", str(binary), str(cpp), str(base.COMMON)],
                                capture_output=True, text=True)
    return (None, built.stderr[-3000:]) if built.returncode else (binary, "")


def worn(binary, code):
    done = harness_env.run([str(binary), code] + [repr(v) for v in values(code)], capture_output=True, text=True)
    return done.returncode, done.stdout


class Lines(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not base.CXX:
            raise unittest.SkipTest("no C++ compiler")
        cls.folder = tempfile.TemporaryDirectory(prefix="dc-maelstrom-lines-")
        cls.items = items_source.source()
        cls.binary, cls.error = build(cls.items, cls.folder.name)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_the_draft_ranges_are_what_the_harness_is_fed(self):
        self.assertEqual(values("primarymaelstrom"), [1.0, 3.0])
        self.assertEqual(values("maelstromgen"), [5.0, 10.0])

    def test_the_totems_line_moves_primary_maelstrom(self):
        self.assertIsNotNone(self.binary, self.error)
        code, out = worn(self.binary, "primarymaelstrom")
        self.assertEqual(code, 0, out)

    def test_the_maces_line_moves_maelstrom_generation(self):
        self.assertIsNotNone(self.binary, self.error)
        code, out = worn(self.binary, "maelstromgen")
        self.assertEqual(code, 0, out)

    def test_mutants_are_caught(self):
        mutants = [
            ('{"primarymaelstrom", {Stat::PrimaryMaelstrom}}', '{"primarymaelstrom", {Stat::MaelstromGeneration}}', "primarymaelstrom"),
            ('{"maelstromgen", {Stat::MaelstromGeneration}}', '{"maelstromgen", {Stat::PrimaryMaelstrom}}', "maelstromgen"),
            ('{"primarymaelstrom", {Stat::PrimaryMaelstrom}}', '{"primarymaelstrom", {Stat::MaxFury}}', "primarymaelstrom"),
            ('{"maelstromgen", {Stat::MaelstromGeneration}}', '{"maelstromgen", {Stat::MaelstromGeneration, Bucket::Percent}}', "maelstromgen"),
            ('{"primarymaelstrom", {Stat::PrimaryMaelstrom}},', '', "primarymaelstrom"),
            ('{"maelstromgen", {Stat::MaelstromGeneration}},', '', "maelstromgen"),
        ]
        for old, new, code in mutants:
            with self.subTest(mutation=old + " -> " + new):
                self.assertEqual(self.items.count(old), 1, old)
                with tempfile.TemporaryDirectory(prefix="dc-maelstrom-lines-mutant-") as folder:
                    binary, error = build(self.items.replace(old, new), folder)
                    if binary is None:
                        continue  # a mutant that no longer compiles is caught
                    returned, _ = worn(binary, code)
                    self.assertNotEqual(returned, 0, f"survived: {new!r}")


if __name__ == "__main__":
    unittest.main()
