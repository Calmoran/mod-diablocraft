// The real dc_shaman_frost_lance.h. The rune names and numbers come from argv (read from the sheets by
// test_shaman_frost_lance.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/shaman/dc_shaman_frost_lance.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::FrostLance;

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
    // argv: the five runes A to E, Icefury's most stacks and percent per stack and seconds, the shards' cone length and
    // degrees, Glacial Boulder's cooldown seconds.
    if (argc < 13)
        return 2;
    std::string const icefury = argv[1], shatter = argv[2], frostfire = argv[3], boulder = argv[4], hail = argv[5];
    unsigned const most = unsigned(std::atoi(argv[6]));
    double const perStack = std::atof(argv[7]), seconds = std::atof(argv[8]), length = std::atof(argv[9]),
                 degrees = std::atof(argv[10]), cooldown = std::atof(argv[11]);

    expect(RuneOf(icefury) == Rune::Icefury && RuneOf(shatter) == Rune::ShatteringLance &&
               RuneOf(frostfire) == Rune::FrostfireBolt && RuneOf(boulder) == Rune::GlacialBoulder &&
               RuneOf(hail) == Rune::Thunderhail,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Frost Lance") == Rune::None && RuneOf("Lightning Bolt") == Rune::None,
           "and nothing else is");

    // The runes whose own damage is not the lance's hit.
    expect(HitIsSkills(Rune::ShatteringLance) && HitIsSkills(Rune::FrostfireBolt) && HitIsSkills(Rune::Thunderhail) &&
               !HitIsSkills(Rune::None) && HitIsSkills(Rune::Icefury) && !HitIsSkills(Rune::GlacialBoulder),
           "the shards, the burn, the arc and Icefury's duration leave the lance's own hit the skill's");

    // Icefury.
    expect(Stacked(0, 1, most) == 1 && Stacked(most - 1, 1, most) == most && Stacked(most, 1, most) == most &&
               Stacked(most, 3, most) == most,
           "Icefury stacks up to its most");
    expect(IcefuryBonus(3, perStack) == 3 * perStack && IcefuryBonus(0, perStack) == 0 && IcefuryBonus(3, 0) == 0,
           "each stack adds its percent");
    std::uint64_t const start = 9000, ends = start + std::uint64_t(seconds * 1000.0);
    expect(Holds(ends - 1, ends) && !Holds(ends, ends) && !Holds(start, 0) && seconds > 0,
           "the stacks hold for their seconds");

    // Shattering Lance's cone: the caster at the origin, the first enemy ten yards out along x.
    double const first = 10.0, half = degrees * 0.5 * 3.14159265358979323846 / 180.0;
    expect(BehindInCone(0, 0, first, 0, first + length * 0.5, 0, length, degrees),
           "an enemy straight behind the first is in the cone");
    expect(!BehindInCone(0, 0, first, 0, first + length + 1, 0, length, degrees), "and one beyond the length is not");
    expect(!BehindInCone(0, 0, first, 0, first - length * 0.5, 0, length, degrees), "and one in front of it is not");
    expect(!BehindInCone(0, 0, first, 0, first, 0, length, degrees), "and the first enemy is not");
    expect(BehindInCone(0, 0, first, 0, first + 5, 5 * std::tan(half) * 0.9, length, degrees) &&
               !BehindInCone(0, 0, first, 0, first + 5, 5 * std::tan(half) * 1.1, length, degrees),
           "and the cone is as wide as its degrees");
    expect(!BehindInCone(0, 0, 0, 0, 5, 0, length, degrees), "and a first enemy on the caster has no cone");

    // Glacial Boulder's cooldown per enemy.
    std::uint64_t const gap = std::uint64_t(cooldown * 1000.0);
    expect(Freezes(5000, 0, cooldown) && !Freezes(5000 + gap - 1, 5000, cooldown) &&
               Freezes(5000 + gap, 5000, cooldown),
           "a freeze waits for its cooldown");

    // Frostfire Bolt burns chilled enemies only.
    expect(Burns(Rune::FrostfireBolt, true) && !Burns(Rune::FrostfireBolt, false) && !Burns(Rune::Icefury, true) &&
               !Burns(Rune::None, true),
           "only Frostfire Bolt burns, and only a chilled enemy");

    // Every record the loader would give no hit of its own (it states a duration) is left the skill's by the rule above.
    std::string waiting = argv[12];
    int claimed = 0;
    for (std::size_t from = 0; from <= waiting.size();)
    {
        std::size_t to = waiting.find(',', from);
        if (to == std::string::npos)
            to = waiting.size();
        std::string const name = waiting.substr(from, to - from);
        expect(HitIsSkills(RuneOf(name)), name.c_str());
        ++claimed;
        from = to + 1;
    }
    expect(claimed >= 1, "at least one record waits");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
