// The real dc_necromancer_grim_scythe_math.h and dc_necromancer_buffs.h. The rune names and numbers come from argv
// (read from the sheets by test_necromancer_grim_scythe.py); nothing is typed in here. Prints "cases=N" and exits 0, or
// names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_buffs.h"
#include "classes/necromancer/dc_necromancer_grim_scythe_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::GrimScythe;
namespace Buffs = DC::Combat::Necromancer::Buffs;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what, double a = 0, double b = 0)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s (%g vs %g)\n", what, a, b);
        ++failures;
    }
}

static bool near(double a, double b)
{
    return std::fabs(a - b) < 1e-9;
}

int main(int argc, char** argv)
{
    // argv: the Essence an enemy pays, Blood Scythe's heal, Execution's threshold and chance, Frost Scythe's attack
    // speed, seconds and stacks, then the five runes A to E
    if (argc < 13)
        return 2;
    double const essence = std::atof(argv[1]), healPct = std::atof(argv[2]), threshold = std::atof(argv[3]),
                 chance = std::atof(argv[4]), speed = std::atof(argv[5]), seconds = std::atof(argv[6]);
    unsigned const maxStacks = unsigned(std::atoi(argv[7]));
    std::string const blood = argv[8], execution = argv[9], frost = argv[10], dual = argv[11],
                      cursed = argv[12];

    expect(RuneOf(blood) == Rune::BloodScythe && RuneOf(execution) == Rune::Execution &&
               RuneOf(frost) == Rune::FrostScythe && RuneOf(dual) == Rune::DualScythes,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {blood, execution, frost, dual, cursed})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Grim Scythe") == Rune::None,
           "the base skill and a stranger are no rune");
    expect(RuneOf(cursed) == Rune::CursedScythe, "Cursed Scythe is its rune");

    // The Essence: for each enemy hit.
    expect(near(EssenceOfHits(essence, 1), essence), "one enemy pays once", EssenceOfHits(essence, 1), essence);
    expect(near(EssenceOfHits(essence, 5), essence * 5), "five enemies pay five times", EssenceOfHits(essence, 5),
           essence * 5);
    expect(near(EssenceOfHits(essence, 0), 0), "no enemy pays nothing");
    expect(near(EssenceOfHits(0, 5), 0) && near(EssenceOfHits(-3, 5), 0), "no Essence stated pays nothing");

    // Blood Scythe: a share of maximum Life for each enemy.
    expect(near(HealOfHits(10000, healPct, 1), 10000 * healPct / 100), "one enemy heals the share",
           HealOfHits(10000, healPct, 1), 10000 * healPct / 100);
    expect(near(HealOfHits(10000, healPct, 4), 10000 * healPct / 100 * 4), "four enemies heal four shares");
    expect(near(HealOfHits(10000, healPct, 0), 0) && near(HealOfHits(0, healPct, 4), 0) &&
               near(HealOfHits(10000, 0, 4), 0),
           "no enemy, no Life or no percent heals nothing");

    // Execution: below the threshold only, and only for a roll under the chance.
    expect(Decapitated(threshold - 1, threshold, chance - 0.01, chance), "a weak enemy and a good roll is decapitated");
    expect(!Decapitated(threshold - 1, threshold, chance, chance), "a roll at the chance is not under it");
    expect(!Decapitated(threshold - 1, threshold, 99.9, chance), "a bad roll spares it");
    expect(!Decapitated(threshold, threshold, 0, chance), "an enemy at the threshold is not below it");
    expect(!Decapitated(threshold + 30, threshold, 0, chance), "a healthy enemy is spared");
    expect(!Decapitated(5, 0, 0, chance) && !Decapitated(5, threshold, 0, 0), "no threshold or no chance, no kill");
    expect(Decapitated(0.5, threshold, 0, chance), "an enemy nearly dead is decapitated");

    // Frost Scythe: a stack for each enemy, up to the cap, the whole time restarted, none once it ran out.
    Buffs::Held held;
    std::uint64_t const ms = std::uint64_t(seconds * 1000);
    expect(Buffs::Add(held, 1000, ms, maxStacks, 1) == 1, "the first enemy is one stack");
    expect(Buffs::Add(held, 1500, ms, maxStacks, 3) == 4, "three more enemies are three more stacks");
    expect(held.until == 1500 + ms, "a cast restarts the whole time", double(held.until), double(1500 + ms));
    expect(Buffs::Add(held, 2000, ms, maxStacks, maxStacks * 2) == maxStacks, "stacks stop at the cap", held.stacks,
           maxStacks);
    expect(near(Buffs::Worth(held, 2000, speed), speed * maxStacks), "the sheet number is the speed for each stack",
           Buffs::Worth(held, 2000, speed), speed * maxStacks);
    expect(!Buffs::Over(held, 2000 + ms - 1) && Buffs::Over(held, 2000 + ms), "the time ends on the moment");
    expect(near(Buffs::Worth(held, 2000 + ms, speed), 0), "nothing on the sheet once it is over");
    expect(Buffs::Add(held, 2000 + ms + 1, ms, maxStacks, 1) == 1, "a buff that ran out starts again from one stack");

    // Dual Scythes: the enemy is drawn to the line the Necromancer faces, level with it, never behind.
    expect(near(LevelWith(0, 0, 1, 0, 6, 3), 6), "level with an enemy ahead and to the side",
           LevelWith(0, 0, 1, 0, 6, 3), 6);
    expect(near(LevelWith(0, 0, 0, 1, -4, 9), 9), "facing along y", LevelWith(0, 0, 0, 1, -4, 9), 9);
    expect(near(LevelWith(0, 0, 1, 0, -6, 3), 0), "never behind the Necromancer");
    expect(near(LevelWith(10, 10, 1, 0, 16, 13), 6), "from where the Necromancer stands",
           LevelWith(10, 10, 1, 0, 16, 13), 6);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
