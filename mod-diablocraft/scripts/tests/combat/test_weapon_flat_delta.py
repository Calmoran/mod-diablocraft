"""GitHub #109, the Combat half: the sheet's flat weapon damage (jewelry and offhand, D3's "+X-Y Damage") is a minimum and a delta.

D3 adds a ring's minimum to the swing's minimum and its maximum to the swing's maximum
(damage_formula.csv step 1: `[Base_Min Base_Max] ... + [Jewelry_Offhand_Min Jewelry_Offhand_Max]`).
Stat::WeaponFlatDamage is the minimum (both ends, as before) and the appended Stat::WeaponFlatDamageDelta the extra on the
high end, so the maximum is min + delta, as Block Amount is kept.

  * the production arithmetic (src/combat/dc_weapon_flat.h) is compiled and driven with the sourced Ancient ring rolls
    (slots.js damageJewelry: min 88-105, max 168-210): the minimum reaches both ends, the delta the high end, and the
    average adds min + delta / 2. A flat number with no delta (a gem, a set) still lands on both ends alike.
    Mutants of the header (delta dropped, delta on both ends, delta in the average twice) fail the same driver;
  * source-text guards, which prove where the code sits and not that it runs: the hit and the sheet summary read the header's
    functions and no longer add the one number to both ends; the enum appends the new stat after the last one, because a
    saved contribution holds the enum's value.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
SRC = MODULE / "src"
HEADER = SRC / "combat/dc_weapon_flat.h"
COMMON_H = SRC / "common/dc_common.h"
COMBAT = SRC / "combat/dc_combat.cpp"
STATS = SRC / "stats/dc_stats.cpp"

# reference/d3planner/slots.js damageJewelry, ancient and primal: the two rolled ranges.
ANCIENT_RING_MIN = (88, 105)
ANCIENT_RING_MAX = (168, 210)

PROGRAM = r"""
#include "common/dc_common.h"
#include "combat/dc_weapon_flat.h"
#include <cstdio>
#include <cstdlib>
using namespace DC;
int main(int argc, char** argv)
{
    // args: weaponLow weaponHigh flatMinimum flatDelta
    StatSheet sheet;
    sheet.values[Index(Stat::WeaponFlatDamage)] = std::atof(argv[3]);
    sheet.values[Index(Stat::WeaponFlatDamageDelta)] = std::atof(argv[4]);
    auto range = Combat::WithFlatDamage({std::atof(argv[1]), std::atof(argv[2])}, sheet);
    std::printf("%.9g %.9g %.9g\n", range.first, range.second, Combat::FlatDamageAverage(sheet));
    return 0;
}
"""


def build(header_text, common_text, name):
    compiler = shutil.which("c++") or shutil.which("g++")
    if not compiler:
        raise unittest.SkipTest("no C++ compiler")
    work = Path(tempfile.mkdtemp(prefix="weaponflat-%s-" % name))
    (work / "combat").mkdir()
    (work / "common").mkdir()
    (work / "combat/dc_weapon_flat.h").write_text(header_text, encoding="utf-8")
    (work / "common/dc_common.h").write_text(common_text, encoding="utf-8")
    for extra in COMMON_H.parent.glob("*.h"):
        if extra.name != "dc_common.h":
            shutil.copy(extra, work / "common" / extra.name)
    (work / "main.cpp").write_text(PROGRAM, encoding="utf-8")
    built = subprocess.run([compiler, "-std=c++17", "-I", str(work), str(work / "main.cpp"), "-o", str(work / "harness")],
                           capture_output=True, text=True)
    if built.returncode:
        raise AssertionError("harness did not compile:\n" + built.stderr[-3000:])
    return work


def ranges(header_text, name, cases, common_text=None):
    work = build(header_text, common_text or COMMON_H.read_text(encoding="utf-8"), name)
    try:
        out = []
        for case in cases:
            ran = harness_env.run([str(work / "harness")] + [repr(float(x)) for x in case], capture_output=True, text=True)
            out.append([float(x) for x in ran.stdout.split()])
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)


# weapon low, weapon high, ring minimum, ring delta (max - min): the ring rolls the ends of both ranges; a delta of 0 is a
# flat number with no range
CASES = [(w, w + 40, lo, hi - lo) for w in (100, 1000) for lo in ANCIENT_RING_MIN for hi in ANCIENT_RING_MAX] + [
    (50, 70, 0, 0), (50, 70, 270, 0)]


def check(header_text, name, common_text=None):
    for case, got in zip(CASES, ranges(header_text, name, CASES, common_text)):
        weapon_low, weapon_high, flat_min, delta = case
        want = [weapon_low + flat_min, weapon_high + flat_min + delta, flat_min + delta / 2]
        if any(abs(a - b) > 1e-6 for a, b in zip(got, want)):
            raise AssertionError("weapon %s-%s ring %s+%s: %r != %r" % (weapon_low, weapon_high, flat_min, delta, got, want))


class Arithmetic(unittest.TestCase):
    def test_the_minimum_reaches_both_ends_and_the_delta_the_high_end(self):
        check(HEADER.read_text(encoding="utf-8"), "prod")

    def test_mutants_fail(self):
        text = HEADER.read_text(encoding="utf-8")
        delta = "sheet[Stat::WeaponFlatDamageDelta]"
        self.assertEqual(text.count(delta), 2)
        mutants = {
            "delta-dropped-from-the-hit": text.replace("weapon.second + minimum + " + delta, "weapon.second + minimum", 1),
            "delta-on-the-low-end-too": text.replace("weapon.first + minimum", "weapon.first + minimum + " + delta, 1),
            "delta-counted-in-full-in-the-average": text.replace(delta + " / 2", delta, 1),
            "minimum-on-the-high-end-only": text.replace("weapon.first + minimum", "weapon.first", 1),
        }
        for label, mutant in mutants.items():
            self.assertNotEqual(text, mutant, label)
            with self.assertRaises(AssertionError, msg=label):
                check(mutant, label)


class Placement(unittest.TestCase):
    def test_the_enum_appends_the_delta_after_the_last_stat(self):
        text = COMMON_H.read_text(encoding="utf-8")
        enum = text[text.index("enum class Stat"):]
        enum = enum[:enum.index("};")]
        stats = [s.strip() for s in re.sub(r"//[^\n]*", "", enum).split("{", 1)[1].split(",") if s.strip()]
        # Later stats append after the delta (1t1yx: the class-resource and monster-type affixes, save version 10).
        self.assertEqual(stats[stats.index("WeaponFlatDamageDelta"):],
                         ["WeaponFlatDamageDelta", "ResourceOnCrit", "LifePerFury", "SpiritRegen", "ManaRegen",
                          "DamageVsBeast", "DamageVsDemon", "DamageVsUndead", "DamageVsHuman", "MaelstromGeneration",
                          "PrimaryMaelstrom", "MaxSecond", "Count"])
        self.assertLess(stats.index("EliteReduction"), stats.index("WeaponFlatDamageDelta"))
        self.assertEqual(stats.count("WeaponFlatDamage"), 1)

    def test_the_hit_and_the_sheet_summary_read_the_header(self):
        combat = COMBAT.read_text(encoding="utf-8")
        stats = STATS.read_text(encoding="utf-8")
        self.assertIn("WithFlatDamage(WeaponRange(player, hit.offHand), *sheet)", combat)
        # The sheet summary's formula is the shared header's (the player's and a follower's), which dc_stats.cpp calls.
        summary = (STATS.parent / "dc_sheet_summary.h").read_text(encoding="utf-8")
        self.assertIn("FlatDamageAverage(sheet)", summary)
        self.assertIn("SheetSummaryOf(", stats)
        for name, text in (("dc_combat.cpp", combat), ("dc_stats.cpp", stats), ("dc_sheet_summary.h", summary)):
            self.assertNotIn("[Stat::WeaponFlatDamage]", text, name + " still reads the one number directly")


if __name__ == "__main__":
    unittest.main()
