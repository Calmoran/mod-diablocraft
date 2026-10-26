// The real dc_witch_doctor_plague_of_toads.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_plague_of_toads.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_plague_of_toads.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat;
using namespace DC::Combat::WitchDoctor::PlagueOfToads;

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
    // argv: the five runes A to E, then the rain's damage and seconds and tick, Rain of Toads' speed bonus and Addling Toads' chance,
    // and the line's reach (skill_targeting.csv).
    if (argc < 12)
        return 2;
    std::string const explosive = argv[1], rain = argv[2], piercing = argv[3], affinity = argv[4], addling = argv[5];
    double const total = std::atof(argv[6]), seconds = std::atof(argv[7]), tick = std::atof(argv[8]), bonus = std::atof(argv[9]), chance = std::atof(argv[10]),
                 reach = std::atof(argv[11]);

    expect(RuneOf(explosive) == Rune::ExplosiveToads && RuneOf(rain) == Rune::RainOfToads && RuneOf(piercing) == Rune::PiercingToads &&
               RuneOf(affinity) == Rune::ToadAffinity && RuneOf(addling) == Rune::AddlingToads,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {explosive, rain, piercing, affinity, addling})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The toads reach the nearest enemy of the line, the first on a tie.
    expect(NearestOf({9, 2, 5}) == 1 && NearestOf({4, 4, 9}) == 0 && NearestOf({7}) == 0 && NearestOf({}) == 0, "the nearest enemy, the first on a tie");
    expect(NearestOf({9, 5, 2}) == 2, "the nearest when it is the last");

    // The selected enemy centres the rain only within the line's reach and in sight.
    expect(SelectedHolds(reach / 2, reach, true), "a selected enemy in reach and in sight centres the rain");
    expect(SelectedHolds(reach, reach, true), "a selected enemy at the reach's edge still does");
    expect(!SelectedHolds(reach + 0.01, reach, true) && !SelectedHolds(reach * 2, reach, true), "a selected enemy beyond the reach does not");
    expect(!SelectedHolds(reach / 2, reach, false), "a selected enemy out of sight does not");

    // Rain of Toads casts faster; no other rune does.
    expect(near(SpeedFactor(Rune::RainOfToads, bonus), 1.0 + bonus), "the rain casts faster by the bonus", SpeedFactor(Rune::RainOfToads, bonus), 1.0 + bonus);
    expect(SpeedFactor(Rune::None, bonus) == 1.0 && SpeedFactor(Rune::PiercingToads, bonus) == 1.0 && SpeedFactor(Rune::RainOfToads, -2) == 1.0,
           "no other rune does, and a bonus is never a slowing");

    // The rain's ticks make its total, the first a tick after the cast and the last at its end.
    unsigned const ticks = PeriodicStrike::Ticks(seconds, tick);
    expect(ticks > 1 && near(PeriodicStrike::TickPct(total, ticks) * ticks, total), "the ticks make the sheet's total", PeriodicStrike::TickPct(total, ticks) * ticks, total);
    expect(RainMs(0, tick) == std::uint32_t(tick * 1000.0 + 0.5) && RainMs(ticks - 1, tick) == std::uint32_t(seconds * 1000.0 + 0.5),
           "the first tick after a tick, the last at the end", RainMs(ticks - 1, tick), seconds * 1000.0);
    expect(RainMs(3, 0) == 0, "no tick length, at once");

    // Addling Toads' chance edge to edge, and the shared pick.
    expect(Confuses(0.0, chance) && Confuses(chance - 0.01, chance) && !Confuses(chance, chance) && !Confuses(0.0, 0.0), "a roll under the chance confuses");
    expect(WitchDoctor::PickAt(0.0, 3) == 0 && WitchDoctor::PickAt(1.0, 3) == 2, "the pick stays among the enemies");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
