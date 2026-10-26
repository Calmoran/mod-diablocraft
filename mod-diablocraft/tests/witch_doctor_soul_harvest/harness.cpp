// The real dc_witch_doctor_soul_harvest.h and dc_witch_doctor_buffs.h. The rune names and numbers come from argv (read
// from the sheets and the tunables by test_witch_doctor_soul_harvest.py); nothing is typed in here. Prints "cases=N"
// and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_soul_harvest.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::WitchDoctor;
using namespace DC::Combat::WitchDoctor::SoulHarvest;

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
    // argv: the five runes A to E, then the most stacks, the seconds a stack lasts, the healing share, the Healing
    // table at level 70, the Life the sheet says, Vengeful Spirit's damage, the Mana pool's rise a stack and the pool
    // it rises from.
    if (argc < 13)
        return 2;
    std::string const siphon = argv[1], waste = argv[2], languish = argv[3], swallow = argv[4], vengeful = argv[5];
    double const most = std::atof(argv[6]), seconds = std::atof(argv[7]), share = std::atof(argv[8]),
                 table = std::atof(argv[9]), sheetLife = std::atof(argv[10]), hit = std::atof(argv[11]),
                 poolPct = std::atof(argv[12]);

    expect(RuneOf(siphon) == Rune::Siphon && RuneOf(waste) == Rune::SoulToWaste && RuneOf(languish) == Rune::Languish &&
               RuneOf(swallow) == Rune::SwallowYourSoul && RuneOf(vengeful) == Rune::VengefulSpirit,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {siphon, waste, languish, swallow, vengeful})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // A cast adds a stack for each enemy harvested, never past the most.
    expect(StacksAdded(2, unsigned(most)) == 2 && StacksAdded(unsigned(most) + 4, unsigned(most)) == unsigned(most) &&
               StacksAdded(0, unsigned(most)) == 0,
           "a stack for each enemy up to the most", StacksAdded(unsigned(most) + 4, unsigned(most)), most);

    // Siphon: the share of the table is the sheet's Life for one enemy, and each enemy returns it.
    expect(std::fabs(SiphonHeal(share, table, 1) - sheetLife) < 1.0, "one enemy returns the sheet's Life",
           SiphonHeal(share, table, 1), sheetLife);
    expect(near(SiphonHeal(share, table, 3), 3 * SiphonHeal(share, table, 1)) && SiphonHeal(0, table, 3) == 0 &&
               SiphonHeal(share, 0, 3) == 0,
           "each enemy returns it, no share or table none");

    // Vengeful Spirit alone hits.
    expect(HitPct(Rune::VengefulSpirit, hit) == hit && HitPct(Rune::Siphon, hit) == 0 && HitPct(Rune::None, hit) == 0 &&
               HitPct(Rune::Languish, hit) == 0,
           "only Vengeful Spirit hits", HitPct(Rune::VengefulSpirit, hit), hit);

    // The buff: stacks add to the most and restart the time; one that ran out starts again; its worth is the stacks'
    // and none when over.
    std::uint64_t const ms = std::uint64_t(seconds * 1000.0);
    Buffs::Held held;
    expect(Buffs::Add(held, 1000, ms, unsigned(most), 2) == 2 && held.until == 1000 + ms,
           "a cast adds stacks and sets the time", held.stacks, 2);
    expect(Buffs::Add(held, 2000, ms, unsigned(most), 2) == 4 && held.until == 2000 + ms,
           "a second cast adds more and restarts the time", held.stacks, 4);
    expect(Buffs::Add(held, 3000, ms, unsigned(most), 3) == unsigned(most), "the stacks stop at the most", held.stacks,
           most);
    expect(near(Buffs::Worth(held, 4000, 3.0), 3.0 * most), "the worth is the stacks'", Buffs::Worth(held, 4000, 3.0),
           3.0 * most);
    expect(Buffs::Worth(held, 3000 + ms, 3.0) == 0 && Buffs::Over(held, 3000 + ms) && !Buffs::Over(held, 3000 + ms - 1),
           "the buff is over at its end");
    expect(Buffs::Add(held, 3000 + ms + 5, ms, unsigned(most), 1) == 1, "a buff that ran out starts again from one",
           held.stacks, 1);
    Buffs::Held none;
    expect(Buffs::Add(none, 0, ms, 0, 1) == 1, "a cap of nothing still holds one");

    // Swallow Your Soul: a stack adds the pool's share, none for no pool.
    expect(near(Buffs::PoolPerStack(750, poolPct), 750 * poolPct / 100.0) && Buffs::PoolPerStack(0, poolPct) == 0 &&
               Buffs::PoolPerStack(750, 0) == 0,
           "a stack adds the pool's share", Buffs::PoolPerStack(750, poolPct), 750 * poolPct / 100.0);
    expect(near(Buffs::PerEnemy(4, 2.5), 10.0) && Buffs::PerEnemy(4, 0) == 0, "each enemy gives its number");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
