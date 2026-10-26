"""GitHub #66: the class-spell sweep's own-shell guard covers every shell.

`IsClassSpell` (dc_classes.cpp) decides which spells the K3 sweep strips from
a Torment character's book. It used to exempt our shells with a hand-kept
range, 81000-81156, which went stale when later blocks were appended: 455 of
the 612 shells in data/generated/spell_shells.csv sit above it. Today no shell
carries a stock class's SpellFamilyName, so nothing was stripped in game
(docs/test-pre-beta-bugs-b.md, #66 analysis), but the exemption held only by
that accident.

The guard now reads `DC::Combat::Shells::IsShell`, which generate_spells.py
writes into dc_spell_shells.h from the shell catalogue. This suite checks both
halves:

- the header's id list is exactly spell_shells.csv's ids, so it cannot go
  stale the way the constant did;
- the module's own `IsClassSpell`, cut out of dc_classes.cpp and compiled
  against the real generated header, keeps every catalogue shell even when
  that shell carries the player's class family - the worst case the old guard
  only survived by accident - and still strips a stock spell of that family.

Each half is also run with the old bug put back, and must fail.

Not covered: the core's spell map, `removeSpell`, and the live family data in
Spell.dbc/spell_dbc. The GM check in docs/test-pre-beta-bugs-b.md covers those.
"""
import csv
import re
import shutil
import subprocess
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE = REPO_ROOT / "mod-diablocraft"
SCRATCH = REPO_ROOT / "azerothcore-wotlk" / "build" / "_agent-scratch" / "class_spell_guard"
CLASSES = (MODULE / "src" / "classes" / "dc_classes.cpp").read_text(encoding="utf-8")
SHELLS_H = (MODULE / "src" / "combat" / "dc_spell_shells.h").read_text(encoding="utf-8")
CATALOGUE = MODULE / "data" / "generated" / "spell_shells.csv"

# A stock spell to prove the sweep still strips: Mortal Strike, a Warrior
# spell at the pin, and outside every block the catalogue reserves.
STOCK_SPELL = 12294
# Any non-zero family works: the harness gives every spell the player's own.
CLASS_FAMILY = 4


def catalogue_ids():
    with CATALOGUE.open(encoding="utf-8", newline="") as stream:
        return [int(row["spell_id"]) for row in csv.DictReader(stream)]


def header_ids(header):
    body = re.search(r"inline constexpr uint32_t ShellIds\[\] = \{\n(.*?)\n\};", header, re.S)
    assert body, "dc_spell_shells.h has no ShellIds table"
    return [int(n) for n in re.findall(r"\d+", body.group(1))]


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


SHIM = """#pragma once
#include <cstdint>
#include <unordered_map>
using uint32 = std::uint32_t;
struct Player { uint32 cls = 0; uint32 getClass() const { return cls; } };
struct ChrClassesEntry { uint32 spellfamily; };
struct ChrClassesStore
{
    std::unordered_map<uint32, ChrClassesEntry> rows;
    ChrClassesEntry const* LookupEntry(uint32 id) const
    {
        auto found = rows.find(id);
        return found == rows.end() ? nullptr : &found->second;
    }
};
inline ChrClassesStore sChrClassesStore;
struct SpellInfo { uint32 SpellFamilyName = 0; };
struct SpellMgr
{
    SpellInfo info;                     // every spell carries this family
    SpellInfo const* GetSpellInfo(uint32) const { return &info; }
};
inline SpellMgr spellMgr;
inline SpellMgr* sSpellMgr = &spellMgr;
namespace DC::Potion
{
constexpr std::uint32_t BaseSpell = %d;
constexpr std::uint32_t BottomlessSpell = %d;
inline bool IsPotionShell(std::uint32_t spellId) { return spellId == BaseSpell || spellId == BottomlessSpell; }
}
"""

HARNESS = """#include "shim.h"
#include "dc_spell_shells.h"
namespace DC::Classes
{
%s
%s
}
#include <cstdlib>
#include <iostream>
int main(int argc, char** argv)
{
    unsigned failures = 0;
    sChrClassesStore.rows[1] = {%d};
    Player player; player.cls = 1;
    sSpellMgr->info.SpellFamilyName = %d;
    for (int i = 1; i < argc; ++i)
    {
        uint32 const id = uint32(std::strtoul(argv[i], nullptr, 10));
        if (DC::Classes::IsClassSpell(&player, id))
        {
            std::cerr << "FAIL: shell " << id << " is swept as a class spell\\n";
            ++failures;
        }
    }
    if (!DC::Classes::IsClassSpell(&player, %d))
    {
        std::cerr << "FAIL: the stock class spell is no longer swept\\n";
        ++failures;
    }
    if (failures)
        return 1;
    std::cout << "ok\\n";
    return 0;
}
"""


def potion_spells():
    header = (MODULE / "src" / "classes" / "dc_potion.h").read_text(encoding="utf-8")
    return tuple(int(re.search(r"constexpr std::uint32_t %s = (\d+);" % name, header).group(1))
                 for name in ("BaseSpell", "BottomlessSpell"))


class ClassSpellGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = shutil.which("c++") or shutil.which("g++")
        cls.ids = catalogue_ids()

    def run_guard(self, name, classes=CLASSES, shells_h=SHELLS_H):
        if not self.compiler:
            self.skipTest("no C++ compiler")
        folder = SCRATCH / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "shim.h").write_text(SHIM % potion_spells(), encoding="utf-8")
        (folder / "dc_spell_shells.h").write_text(shells_h, encoding="utf-8")
        source = HARNESS % (
            definition("std::uint32_t ClassSpellFamily(Player const* player)", classes),
            definition("bool IsClassSpell(Player const* player, std::uint32_t spellId)", classes),
            CLASS_FAMILY, CLASS_FAMILY, STOCK_SPELL)
        (folder / "harness.cpp").write_text(source, encoding="utf-8")
        binary = folder / "harness"
        built = subprocess.run([self.compiler, "-std=c++17", "-Wall", "-I", str(folder),
                                str(folder / "harness.cpp"), "-o", str(binary)],
                               capture_output=True, text=True)
        self.assertEqual(built.returncode, 0, "%s did not compile:\n%s" % (name, built.stderr[-6000:]))
        return harness_env.run([str(binary)] + [str(i) for i in self.ids], capture_output=True, text=True)

    def test_the_catalogue_reaches_past_the_old_constant(self):
        """The fixture is only meaningful while shells exist above 81156."""
        self.assertGreater(sum(1 for i in self.ids if i > 81156), 0)
        self.assertNotIn(STOCK_SPELL, self.ids)

    def test_header_lists_exactly_the_catalogue(self):
        self.assertEqual(header_ids(SHELLS_H), sorted(set(self.ids)))
        self.assertEqual(len(self.ids), len(set(self.ids)))

    def test_every_shell_survives_the_sweep(self):
        run = self.run_guard("production")
        self.assertEqual(run.returncode, 0, run.stderr[-4000:])
        self.assertEqual(run.stdout.strip(), "ok")

    def test_the_old_range_guard_fails(self):
        old = CLASSES.replace(
            "if (Combat::Shells::IsShell(spellId))",
            "if (spellId >= 81000 && spellId <= 81156)")
        self.assertNotEqual(old, CLASSES, "mutation target is gone")
        run = self.run_guard("mutation_range", classes=old)
        self.assertNotEqual(run.returncode, 0, "the harness passed with the old range restored")
        self.assertIn("FAIL: shell 81157", run.stderr)

    def test_a_stale_header_fails(self):
        """A header cut at the old last shell fails both halves."""
        block = re.search(r"inline constexpr uint32_t ShellIds\[\] = \{\n.*?\n\};", SHELLS_H, re.S).group(0)
        kept = [i for i in header_ids(SHELLS_H) if i <= 81156]
        stale = SHELLS_H.replace(block, "inline constexpr uint32_t ShellIds[] = {\n    "
                                 + ", ".join(map(str, kept)) + ",\n};")
        self.assertNotEqual(stale, SHELLS_H, "mutation target is gone")
        self.assertNotEqual(header_ids(stale), sorted(set(self.ids)))
        run = self.run_guard("mutation_stale_header", shells_h=stale)
        self.assertNotEqual(run.returncode, 0, "the harness passed with a stale header")
        self.assertIn("FAIL: shell", run.stderr)

    def test_a_guard_that_keeps_nothing_fails(self):
        """The control: dropping the exemption strips our shells."""
        gone = CLASSES.replace("if (Combat::Shells::IsShell(spellId))", "if (false)")
        run = self.run_guard("mutation_no_guard", classes=gone)
        self.assertNotEqual(run.returncode, 0)


if __name__ == "__main__":
    unittest.main()
