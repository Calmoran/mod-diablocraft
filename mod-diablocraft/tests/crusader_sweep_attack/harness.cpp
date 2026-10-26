// The real dc_crusader_sweep_attack.h and dc_crusader_dot.h. The rune names and numbers come from argv (read from the
// sheets and the tunables by test_crusader_sweep_attack.py); nothing is typed in here. Prints "cases=N" and exits 0, or
// names the first failing case and exits 1.
#include "classes/crusader/dc_crusader_dot.h"
#include "classes/crusader/dc_crusader_sweep_attack.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader;
using namespace DC::Combat::Crusader::SweepAttack;

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

int main(int argc, char** argv)
{
    // argv: the reach, the heal for each enemy hit, the fire's total damage, its seconds, then the five runes A to E
    if (argc < 10)
        return 2;
    double const reach = std::atof(argv[1]), heal = std::atof(argv[2]), total = std::atof(argv[3]),
                 seconds = std::atof(argv[4]);
    std::string const gathering = argv[5], blazing = argv[6], shock = argv[7], trip = argv[8], inspiring = argv[9];

    expect(RuneOf(gathering) == Rune::GatheringSweep && RuneOf(blazing) == Rune::BlazingSweep &&
               RuneOf(shock) == Rune::HolyShock && RuneOf(trip) == Rune::TripAttack &&
               RuneOf(inspiring) == Rune::InspiringSweep,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {gathering, blazing, shock, trip, inspiring})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Carve") == Rune::None, "the base skill and a stranger are no rune");

    // The half circle: an enemy the cone did not take, inside the reach and the arc.
    expect(Swept(reach, reach, true, false), "the edge of the reach is swept", reach, reach);
    expect(!Swept(reach + 0.01, reach, true, false), "past the reach is not swept");
    expect(!Swept(5, reach, false, false), "outside the half circle is not swept");
    expect(!Swept(5, reach, true, true), "an enemy the cone struck is not struck twice");
    expect(!Swept(5, 0, true, false), "no reach, no sweep");
    expect(std::fabs(ArcRadians(180.0) - 3.14159265358979323846) < 1e-9, "a half circle is pi");
    expect(std::fabs(ArcRadians(90.0) * 2 - ArcRadians(180.0)) < 1e-9, "degrees to radians scale");

    // Holy Shock: the Life of each enemy hit.
    expect(HealFor(heal, 0) == 0 && HealFor(heal, 1) == heal && HealFor(heal, 4) == 4 * heal,
           "the heal is for each enemy hit", HealFor(heal, 4), 4 * heal);
    expect(HealFor(0, 4) == 0, "a rune that states no Life heals nothing");

    // Blazing Sweep's fire: the ticks that fit, each one's share, nothing without a tick length.
    expect(Dot::Ticks(seconds, 0.5) == 4, "the designer's half second gives four ticks", Dot::Ticks(seconds, 0.5), 4);
    expect(std::fabs(Dot::TickPct(total, Dot::Ticks(seconds, 0.5)) - 30) < 1e-9, "each of the four is 30%", Dot::TickPct(total, Dot::Ticks(seconds, 0.5)), 30);
    expect(Dot::Ticks(seconds, 0) == 0, "no tick length, no ticks");
    expect(Dot::Ticks(0, 0.5) == 0, "no seconds, no ticks");
    expect(Dot::Ticks(seconds, seconds) == 1, "one tick as long as the fire");
    expect(Dot::Ticks(seconds, seconds / 4) == 4, "four quarter ticks", Dot::Ticks(seconds, seconds / 4), 4);
    expect(Dot::Ticks(1.0, 0.1) == 10, "ten tenths despite the float", Dot::Ticks(1.0, 0.1), 10);
    expect(Dot::Ticks(seconds, seconds * 3) == 0, "a tick longer than the fire never lands");
    expect(std::fabs(Dot::TickPct(total, 4) * 4 - total) < 1e-9, "the ticks add up to the total",
           Dot::TickPct(total, 4) * 4, total);
    expect(Dot::TickPct(total, 0) == 0, "no ticks, no share");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
