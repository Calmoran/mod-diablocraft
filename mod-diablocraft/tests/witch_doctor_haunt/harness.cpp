// The real dc_witch_doctor_haunt.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_haunt.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_haunt.h"
#include "combat/dc_periodic_strike.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat;
using namespace DC::Combat::WitchDoctor;
using namespace DC::Combat::WitchDoctor::Haunt;

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
    // argv: the five runes A to E, then the spirits Resentful Spirits releases, the most out at once, the haunt's damage and seconds, the tick,
    // the seconds a spirit lingers, the healing share, the Healing table at level 70, the Life a second the sheet says, the Mana over a haunt,
    // the Mana a second the sheet says, the seconds left that make a cast pass over an enemy, the check interval in seconds.
    if (argc < 19)
        return 2;
    std::string const consuming = argv[1], lingering = argv[2], poisoned = argv[3], draining = argv[4], resentful = argv[5];
    double const spirits = std::atof(argv[6]), most = std::atof(argv[7]), damage = std::atof(argv[8]), seconds = std::atof(argv[9]),
                 tick = std::atof(argv[10]), linger = std::atof(argv[11]), share = std::atof(argv[12]), table = std::atof(argv[13]),
                 sheetLife = std::atof(argv[14]), manaTotal = std::atof(argv[15]), sheetMana = std::atof(argv[16]),
                 minLeft = std::atof(argv[17]), check = std::atof(argv[18]);

    expect(RuneOf(consuming) == Rune::ConsumingSpirit && RuneOf(lingering) == Rune::LingeringSpirit && RuneOf(poisoned) == Rune::PoisonedSpirit &&
               RuneOf(draining) == Rune::DrainingSpirit && RuneOf(resentful) == Rune::ResentfulSpirits,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {consuming, lingering, poisoned, draining, resentful})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Resentful Spirits releases two; every other rune and the skill one.
    expect(Spirits(Rune::ResentfulSpirits, spirits) == unsigned(spirits) && Spirits(Rune::None, spirits) == 1 && Spirits(Rune::PoisonedSpirit, spirits) == 1,
           "only Resentful Spirits releases more than one", Spirits(Rune::ResentfulSpirits, spirits), spirits);
    expect(Spirits(Rune::ResentfulSpirits, 0) == 1, "never fewer than one");

    // The haunt's ticks make its damage; each tick is an even share and the last falls when the haunt ends.
    unsigned const ticks = PeriodicStrike::Ticks(seconds, tick);
    expect(ticks > 1 && near(PeriodicStrike::TickPct(damage, ticks) * ticks, damage), "the ticks make the sheet's damage", PeriodicStrike::TickPct(damage, ticks) * ticks, damage);
    double left = seconds;
    unsigned count = 0;
    while (left > 0 && count < 1000)
    {
        left = Left(left, tick);
        ++count;
    }
    expect(count == ticks && left == 0, "the haunt ends on its last tick", count, ticks);
    expect(Left(0.2, 0.5) == 0 && Left(3, -1) == 3, "a haunt does not go below nothing and a negative tick takes nothing");

    // A cast passes over an enemy a spirit holds with more than the power's minimum left, not one it is about to lose.
    expect(PassesOver(minLeft + 0.5, minLeft) && !PassesOver(minLeft, minLeft) && !PassesOver(0, minLeft), "a cast passes over a freshly haunted enemy only", minLeft, 0);

    // Five out at once: the sixth displaces the oldest, whatever its place in the list.
    expect(!Displaced({}, unsigned(most)) && !Displaced({4, 2, 9}, unsigned(most)), "a spirit that fits displaces none");
    std::vector<std::uint64_t> full;
    for (unsigned i = 0; i < unsigned(most); ++i)
        full.push_back(100 - i * 7);
    expect(Displaced(full, unsigned(most)) && *Displaced(full, unsigned(most)) == full.size() - 1, "the oldest gives way", double(*Displaced(full, unsigned(most))), double(full.size() - 1));
    full[0] = 1;
    expect(*Displaced(full, unsigned(most)) == 0, "the oldest gives way wherever it is");

    // Consuming Spirit: its share of the Healing table is the sheet's Life a second at level 70, a tick a share of it.
    expect(std::fabs(LifePerSecond(share, table) - sheetLife) < 1.0, "the share of the table is the sheet's Life a second", LifePerSecond(share, table), sheetLife);
    expect(near(PerTick(LifePerSecond(share, table), tick) / tick, LifePerSecond(share, table)), "the ticks make the second's Life");
    expect(LifePerSecond(0, table) == 0 && LifePerSecond(share, 0) == 0 && PerTick(5, 0) == 0 && PerTick(-1, 0.5) == 0, "no share, no table, no tick, nothing");

    // Draining Spirit: the Mana over a haunt a second, the sheet's rounded down.
    expect(ManaPerSecond(manaTotal, seconds) >= sheetMana && ManaPerSecond(manaTotal, seconds) - sheetMana < 1.0, "the Mana a second is the sheet's", ManaPerSecond(manaTotal, seconds), sheetMana);
    expect(near(PerTick(ManaPerSecond(manaTotal, seconds), tick) * ticks, manaTotal), "the ticks return the haunt's Mana", PerTick(ManaPerSecond(manaTotal, seconds), tick) * ticks, manaTotal);
    expect(ManaPerSecond(manaTotal, 0) == 0 && ManaPerSecond(0, seconds) == 0, "no duration, no Mana");

    // The jump: the nearest enemy, none when there is none.
    expect(!Nearest({}) && *Nearest({9, 3, 7}) == 1 && *Nearest({2}) == 0, "the spirit jumps to the nearest enemy");

    // Lingering Spirit: it looks for the sheet's seconds and then ends.
    expect(StillLooking(0, linger) && StillLooking(linger - tick, linger) && !StillLooking(linger, linger) && !StillLooking(0, 0), "a spirit looks for the linger seconds and no longer", linger, 0);

    // The clock gives the searches: one every check interval.
    double clock = 0;
    unsigned searches = 0;
    for (int i = 0; i < 100; ++i)
        searches += Due(clock, tick * 1000.0, check * 1000.0);
    expect(searches == unsigned(std::floor(100 * tick / check + 1e-9)), "a search falls due every check interval", searches, std::floor(100 * tick / check));

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
