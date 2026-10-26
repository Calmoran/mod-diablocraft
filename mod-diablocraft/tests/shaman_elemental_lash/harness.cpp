// The real dc_shaman_elemental_lash.h. The rune names and numbers come from argv (read from the sheets by
// test_shaman_elemental_lash.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/shaman/dc_shaman_elemental_lash.h"

#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::ElementalLash;

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
    // argv: the five runes A to E, Lava Surge's chance percent, Stonewhip's extra Maelstrom and the enemies it needs.
    if (argc < 10)
        return 2;
    std::string const searing = argv[1], surge = argv[2], whip = argv[3], frost = argv[4], thunder = argv[5];
    double const chance = std::atof(argv[6]), gain = std::atof(argv[7]), needed = std::atof(argv[8]);

    expect(RuneOf(searing) == Rune::SearingLash && RuneOf(surge) == Rune::LavaSurge &&
               RuneOf(whip) == Rune::Stonewhip && RuneOf(frost) == Rune::FrostLash &&
               RuneOf(thunder) == Rune::ThunderLash,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Elemental Lash") == Rune::None && RuneOf("Flame Shock") == Rune::None,
           "and nothing else is");

    // Only Searing Lash states its hit beside a burn.
    expect(HitIsTagged(Rune::SearingLash) && !HitIsTagged(Rune::None) && !HitIsTagged(Rune::LavaSurge) &&
               !HitIsTagged(Rune::Stonewhip) && !HitIsTagged(Rune::FrostLash) && !HitIsTagged(Rune::ThunderLash),
           "only Searing Lash states its hit apart");

    // A Lava Surge comes up below its percent.
    expect(Procs(0.0, chance) && Procs(chance / 100.0 - 0.001, chance) && !Procs(chance / 100.0, chance) &&
               !Procs(0.99, chance) && !Procs(0.0, 0) && !Procs(0.0, -5),
           "a Lava Surge comes up below its chance");

    // Stonewhip's crowd.
    unsigned const n = unsigned(needed);
    expect(CrowdGain(n, needed, gain) == gain && CrowdGain(n + 4, needed, gain) == gain,
           "Stonewhip adds Maelstrom for its crowd and more");
    expect(CrowdGain(n - 1, needed, gain) == 0 && CrowdGain(0, needed, gain) == 0, "and nothing for fewer");
    expect(CrowdGain(n, 0, gain) == 0 && CrowdGain(n, needed, 0) == 0 && CrowdGain(n, needed, -1) == 0,
           "and nothing when a number is missing");

    // The push spares elites and bosses.
    expect(Pushes(false) && !Pushes(true), "Stonewhip pushes back an ordinary enemy and not an elite");

    // Every record the loader would give no hit of its own (it states a duration) is left to the rule above.
    std::string waiting = argv[9];
    int claimed = 0;
    for (std::size_t from = 0; from <= waiting.size();)
    {
        std::size_t to = waiting.find(',', from);
        if (to == std::string::npos)
            to = waiting.size();
        std::string const name = waiting.substr(from, to - from);
        expect(HitIsTagged(RuneOf(name)), name.c_str());
        ++claimed;
        from = to + 1;
    }
    expect(claimed >= 1, "at least one record waits");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
