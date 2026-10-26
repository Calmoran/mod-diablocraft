// The real dc_witch_doctor_grasp_of_the_dead.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_witch_doctor_grasp_of_the_dead.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_grasp_of_the_dead.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat;
using namespace DC::Combat::WitchDoctor;
using namespace DC::Combat::WitchDoctor::GraspOfTheDead;

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
    // argv: the five runes A to E, then the hands' damage and seconds, the pulse, the slow's extra seconds, the corpses' damage and seconds
    // and the seconds between them, Death Is Life's chance and the hands' radius.
    if (argc < 15)
        return 2;
    std::string const eels = argv[1], corpses = argv[2], grasp = argv[3], desperate = argv[4], life = argv[5];
    double const total = std::atof(argv[6]), seconds = std::atof(argv[7]), pulse = std::atof(argv[8]), extra = std::atof(argv[9]),
                 corpseTotal = std::atof(argv[10]), corpseSeconds = std::atof(argv[11]), corpseTick = std::atof(argv[12]),
                 chance = std::atof(argv[13]), radius = std::atof(argv[14]);

    expect(RuneOf(eels) == Rune::GropingEels && RuneOf(corpses) == Rune::RainOfCorpses && RuneOf(grasp) == Rune::UnbreakableGrasp &&
               RuneOf(desperate) == Rune::DesperateGrasp && RuneOf(life) == Rune::DeathIsLife,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {eels, corpses, grasp, desperate, life})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // A pulse's slow outlasts the pulse, so it holds between two.
    expect(near(SlowSeconds(pulse, extra), pulse + extra) && SlowSeconds(pulse, extra) > pulse, "the slow outlasts the pulse", SlowSeconds(pulse, extra), pulse + extra);
    expect(SlowSeconds(pulse, -1) == pulse && SlowSeconds(-1, extra) == extra && SlowSeconds(0, 0) == 0, "no negative seconds");

    // The hands' pulses make the total, the first a pulse after the hands rise and the last at the end.
    unsigned const pulses = PeriodicStrike::Ticks(seconds, pulse);
    expect(pulses > 1 && near(PeriodicStrike::TickPct(total, pulses) * pulses, total), "the pulses make the sheet's total", PeriodicStrike::TickPct(total, pulses) * pulses, total);
    expect(PulseMs(0, pulse) == std::uint32_t(pulse * 1000.0 + 0.5) && PulseMs(pulses - 1, pulse) == std::uint32_t(seconds * 1000.0 + 0.5),
           "the first pulse after a pulse, the last at the end", PulseMs(pulses - 1, pulse), seconds * 1000.0);
    expect(PulseMs(3, 0) == 0, "no interval, at once");

    // Rain of Corpses: its corpses make its total.
    unsigned const falls = PeriodicStrike::Ticks(corpseSeconds, corpseTick);
    expect(falls >= 1 && near(PeriodicStrike::TickPct(corpseTotal, falls) * falls, corpseTotal), "the corpses make the rune's total", PeriodicStrike::TickPct(corpseTotal, falls) * falls, corpseTotal);
    expect(PulseMs(falls - 1, corpseTick) == std::uint32_t(corpseSeconds * 1000.0 + 0.5), "the last corpse falls at the end", PulseMs(falls - 1, corpseTick), corpseSeconds * 1000.0);
    expect(PickAt(0.0, 4) == 0 && PickAt(1.0, 4) == 3, "the pick stays among the enemies");

    // Death Is Life: the area catches a death for the hands' seconds and the slow's extra, inside the radius only.
    std::uint64_t const area = AreaMs(seconds, extra);
    expect(area == std::uint64_t((seconds + extra) * 1000.0 + 0.5) && area > std::uint64_t(seconds * 1000.0), "the area outlasts the last pulse", double(area), (seconds + extra) * 1000.0);
    expect(AreaMs(-1, -1) == 0, "no negative seconds in the area");
    expect(InArea(1000, 1000 + area, radius, radius), "a death on the edge is inside", radius, radius);
    expect(!InArea(1000, 1000 + area, radius + 0.01, radius), "a death past the edge is outside", radius + 0.01, radius);
    expect(InArea(1000 + area - 1, 1000 + area, 0, radius) && !InArea(1000 + area, 1000 + area, 0, radius), "the area ends when its time does", double(area), 0);
    expect(Rises(0.0, chance) && Rises(chance - 0.01, chance) && !Rises(chance, chance) && !Rises(99.99, chance) == (chance < 99.99),
           "a roll below the chance rises", chance, 0);
    expect(!Rises(0.0, 0.0) && !Rises(0.0, -5.0), "no chance, no dog");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
