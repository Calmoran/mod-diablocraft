#!/usr/bin/env python3
"""diablocraft-plawd: gear that raises a second resource's maximum (Maximum Discipline) reaches the second slot.

The Demon Hunter keeps Hatred in her first slot (Stat::MaxFury is that slot's maximum for every class) and Discipline in her
second, whose maximum is its pool plus what skills add (Resources::Pool) and now what gear adds (Stat::MaxSecond). What runs:
the pool header's Maximum(), compiled as it is, adds the pool, the skills' bonus and the gear's points, and nothing leaves the
first slot out of it. What is read from source: both places dc_stats.cpp sets the second maximum (the sheet refresh and the
power-update hook) take it from that one function with the sheet's MaxSecond, and the first slot is still the sheet's MaxFury
alone. The item side (maxdisc moves MaxSecond and not MaxFury) is items/test_preset_stat_mappings.py.
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import scripts_path  # noqa: E402,F401  (R5: every scripts/ folder on sys.path)
import harness_env  # noqa: E402

MODULE = Path(__file__).resolve().parents[3]
POOL = MODULE / "src/classes/dc_resource_pool.h"
STATS = (MODULE / "src/stats/dc_stats.cpp").read_text(encoding="utf-8")
PROGRAM = r"""
#include "classes/dc_resource_pool.h"
#include <cmath>
#include <cstdio>
using namespace DC::Resources;
int failures = 0;
void Check(bool ok, char const* what) { if (!ok) { std::printf("FAIL: %s\n", what); ++failures; } }
int main()
{
    std::uint64_t const player = 41, other = 42;
    Check(std::fabs(Pool::Maximum(30, player, 0) - 30) < 1e-9, "the pool alone");
    Check(std::fabs(Pool::Maximum(30, player, 12) - 42) < 1e-9, "gear adds to the pool");
    Pool::Set(player, 7, 5);
    Check(std::fabs(Pool::Maximum(30, player, 12) - 47) < 1e-9, "the skills' bonus and the gear's points both count");
    Check(std::fabs(Pool::Maximum(30, other, 12) - 42) < 1e-9, "another player's bonus is not this one's");
    Pool::Set(player, 7, 0);
    Check(std::fabs(Pool::Maximum(30, player, 12) - 42) < 1e-9, "a removed bonus leaves the gear's");
    Pool::Clear(player);
    return failures;
}
"""


def run(header_text):
    binary = harness_env.build_text(PROGRAM, flags=["-std=c++17"], files={"classes/dc_resource_pool.h": header_text})
    return harness_env.run([str(binary)], capture_output=True, text=True)


class Maximum(unittest.TestCase):
    def test_pool_bonus_and_gear_add(self):
        done = run(POOL.read_text(encoding="utf-8"))
        self.assertEqual(done.returncode, 0, done.stdout)

    def test_mutants_are_caught(self):
        text = POOL.read_text(encoding="utf-8")
        body = re.search(r"inline double Maximum\(([^)]*)\)\s*\{\s*return ([^;]*);", text)
        self.assertIsNotNone(body, "Pool::Maximum is not in the header")
        for name, new in (("gear is dropped", "return pool + Bonus(guid);"), ("skills are dropped", "return pool + gear;"),
                          ("the pool is dropped", "return Bonus(guid) + gear;"), ("gear counts twice", "return pool + Bonus(guid) + 2 * gear;")):
            with self.subTest(name):
                mutant = text.replace("return " + body.group(2) + ";", new)
                self.assertNotEqual(mutant, text)
                self.assertNotEqual(run(mutant).returncode, 0, f"survived: {name}")


class Wiring(unittest.TestCase):
    def test_both_second_maximum_writes_take_the_one_function(self):
        calls = re.findall(r"Resources::Pool::Maximum\(([^;]*?)\)\)", STATS)
        self.assertEqual(len(calls), 2, calls)
        for call in calls:
            self.assertIn("cls.second->pool", call)
            self.assertIn("Stat::MaxSecond", call)
        self.assertNotIn("Resources::Pool::Bonus(", STATS)   # no write of the second maximum bypasses it

    def test_the_first_slot_is_still_the_sheets_max_fury_alone(self):
        self.assertIn("Resources::SetMax(player, *cls.resource, sheet[Stat::MaxFury]);", STATS)
        self.assertIn("Resources::ToUnits(*cls.resource, (*sheet)[Stat::MaxFury])", STATS)


if __name__ == "__main__":
    unittest.main()
