"""B1 loot eligibility, executed - not restated.

The first version of this task "proved" Barbarian behaviour unchanged by
writing the predicate again in Python and handing it a literal lower-case
`"barbarian"`. It passed while the shipped code was broken: the generated class
map published the display label `Barbarian`, `dc_loot.cpp` compared it
case-sensitively against lower-case sheet tokens, and **202 of 1114** base
items changed pool (own 588 -> 386, other 1024 -> 1114).

A test that supplies the boundary value by hand cannot see a boundary bug. So
this suite:

  * cuts `Lists`, `ListsAnyOtherThan`, `OwnClassItem` and `OtherClassItem` out
    of `dc_loot.cpp` and compiles them,
  * reads the class key out of the **generated** SQL, never a literal,
  * runs every one of the 1114 base items through them, and
  * fails if any verdict differs from the pre-change predicate's.

The casing mutation below is the regression: put the display label back in the
generated map and this suite must go red.

diablocraft-class-roll-rules (decisions.md 2026-09-23) replaced the "other
class" pool with a roll class: an off-class drop rolls another class's OWN pool.
The predicate is now `DC::RollClass::Eligible` in src/items/dc_roll_class.h,
which dc_loot.cpp's PickBaseItem calls; it is compiled from that header, and it
must still give the pre-change own-class verdict for every item.
"""
import csv
import pathlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

MODULE = pathlib.Path(__file__).resolve().parents[3]
LOOT = (MODULE / "src" / "loot" / "dc_loot.cpp").read_text(encoding="utf-8")
ROLL_CLASS = MODULE / "src" / "items" / "dc_roll_class.h"
HARNESS = MODULE / "tests" / "class_eligibility"
GENERATED = MODULE / "data" / "generated" / "class_catalogue.sql"
BASE_ITEMS = MODULE / "data" / "d3" / "base_items.csv"
SCRATCH = MODULE.parent / "azerothcore-wotlk" / "build" / "_agent-scratch" / "class_eligibility"


def definition(marker, source):
    """One function, braces balanced, exactly as the module has it."""
    assert source.count(marker) == 1, "%r is not unique" % marker
    start = source.index(marker)
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


def published_class_key():
    """The key the generated migration actually publishes. Never a literal."""
    # The first row: the class the old predicate was written for.
    insert = re.search(r"INSERT INTO `dc_class_map` \(([^)]*)\) VALUES\s*\((.*?)\)[,;]",
                       GENERATED.read_text(encoding="utf-8"), re.S)
    columns = [c.strip().strip("`") for c in insert.group(1).split(",")]
    values = next(csv.reader([insert.group(2)], quotechar="'", skipinitialspace=True))
    return dict(zip(columns, values))


def base_items():
    with BASE_ITEMS.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, strict=True))


def old_verdicts(item):
    """The pre-change predicate, with the lower-case literal it had."""
    usable, designation = item["usable_by"], item["designated_class"]
    tokens = usable.split(";")
    own = (not usable or "barbarian" in tokens) and \
          (not designation or designation == "barbarian")
    other = designation != "barbarian" and \
            (not usable or any(t and t != "barbarian" for t in tokens))
    return own, other


class Eligibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("c++") or shutil.which("g++")
        if not cls.compiler:
            raise unittest.SkipTest("no C++ compiler")
        SCRATCH.mkdir(parents=True, exist_ok=True)

        # The real thing: the production header, included as it is.
        extract = (
            "#pragma once\n#include \"%s\"\n\n"
            "struct BaseItem { std::string usable, designation; };\n\n"
            "inline bool OwnClassItem(BaseItem const& item, std::string const& key)\n"
            "{ return DC::RollClass::Eligible(item.usable, item.designation, key); }\n"
            % ROLL_CLASS.as_posix())
        (SCRATCH / "dc_loot_extract.h").write_text(extract, encoding="utf-8")

        cls.items_path = SCRATCH / "items.tsv"
        rows = []
        for item in base_items():
            own, _other = old_verdicts(item)
            rows.append("%s\t%s\t%d" % (item["usable_by"], item["designated_class"], own))
        cls.items_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
        cls.item_count = len(rows)

        cls.binary = SCRATCH / "eligibility_harness"
        built = subprocess.run(
            [cls.compiler, "-std=c++17", "-O0", "-UNDEBUG", "-I", str(SCRATCH),
             str(HARNESS / "eligibility_harness.cpp"), "-o", str(cls.binary)],
            capture_output=True, text=True)
        if built.returncode:
            raise AssertionError("the harness did not compile:\n" + built.stderr[-6000:])

    def run_with(self, key):
        path = SCRATCH / "key.txt"
        path.write_text(key + "\n", encoding="utf-8")
        return harness_env.run([str(self.binary), str(self.items_path), str(path)],
                              capture_output=True, text=True)

    # --- the published key, through the production predicates ---------------

    def test_the_published_key_reproduces_the_old_verdicts_for_every_item(self):
        run = self.run_with(published_class_key()["class_key"])
        self.assertEqual(run.returncode, 0,
                         "the generated key disagrees with the old predicate:\n" + run.stderr)
        self.assertIn("items=%d" % self.item_count, run.stdout)
        self.assertIn("own=588", run.stdout)
        self.assertIn("mismatches=0", run.stdout)

    def test_the_generated_map_publishes_a_canonical_key_beside_its_label(self):
        published = published_class_key()
        self.assertEqual(published["class_key"], "barbarian")
        self.assertEqual(published["d3_class"], "Barbarian")
        self.assertEqual(published["class_key"], published["d3_class"].lower())

    # --- the regression that was shipped ------------------------------------

    def test_publishing_the_display_label_as_the_key_fails(self):
        """The exact defect: 202 items change pool, and this must go red."""
        run = self.run_with(published_class_key()["d3_class"])
        self.assertEqual(run.returncode, 1, "a capitalised key must not pass")
        self.assertIn("own=386", run.stdout)
        self.assertIn("mismatches=202", run.stdout)

    def test_any_casing_change_at_the_boundary_fails(self):
        for key in ("Barbarian", "BARBARIAN", "BarBarian", "barbariaN"):
            with self.subTest(key=key):
                self.assertEqual(self.run_with(key).returncode, 1, key)

    def test_a_key_that_is_not_the_class_at_all_fails(self):
        self.assertEqual(self.run_with("wizard").returncode, 1)

    # --- the generator will not publish a non-canonical key -----------------

    def test_the_generator_rejects_a_non_canonical_class_key(self):
        import generate_class_catalogue as gcc
        rows, passives, labels, passive_labels, class_map, _, _, _ = gcc.catalogue()
        self.assertTrue(all(row[1] == row[1].lower() for row in class_map))
        source = (MODULE / "scripts" / "generate/classes/generate_class_catalogue.py").read_text(encoding="utf-8")
        self.assertIn("is not the canonical lower-case form", source)

    def test_the_loot_roller_calls_the_tested_predicate(self):
        # A set piece takes its set's class for the drop (DropEligible, which calls Eligible).
        self.assertIn("DC::RollClass::DropEligible(item.usable, item.designation, item.setClass, rollClass)", LOOT)
        self.assertNotIn("OtherClassItem", LOOT)

    def test_no_production_code_compares_against_the_display_label(self):
        code = "\n".join(line.split("//")[0] for line in LOOT.splitlines()
                         if not line.strip().startswith("//"))
        self.assertNotIn("d3_class", code)
        self.assertIn("class_key FROM dc_class_map", code)


if __name__ == "__main__":
    unittest.main(verbosity=2)
