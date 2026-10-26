// The real dc_necromancer_death_nova_math.h. The rune names and numbers come from argv (read from the sheets by
// test_necromancer_death_nova.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/necromancer/dc_necromancer_death_nova_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::DeathNova;

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
    // argv: the nova's radius, Unstable Compound's growth and stacks, Tendril Nova's heal, then the five runes A to E
    if (argc < 10)
        return 2;
    double const radius = std::atof(argv[1]), growth = std::atof(argv[2]), heal = std::atof(argv[4]);
    unsigned const most = unsigned(std::atoi(argv[3]));
    std::string const tendril = argv[5], bone = argv[6], blood = argv[7], blight = argv[8], unstable = argv[9];

    expect(RuneOf(tendril) == Rune::TendrilNova && RuneOf(bone) == Rune::BoneNova && RuneOf(blood) == Rune::BloodNova &&
               RuneOf(blight) == Rune::Blight && RuneOf(unstable) == Rune::UnstableCompound,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {tendril, bone, blood, blight, unstable})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Death Nova") == Rune::None, "the base skill and a stranger are no rune");

    // Which runes strike for themselves.
    expect(StrikesForItself(Rune::BoneNova) && StrikesForItself(Rune::UnstableCompound),
           "Bone Nova and Unstable Compound strike for themselves");
    expect(!StrikesForItself(Rune::None) && !StrikesForItself(Rune::TendrilNova) &&
               !StrikesForItself(Rune::BloodNova) && !StrikesForItself(Rune::Blight),
           "the others leave the engine's nova");

    // Unstable Compound: the radius grows with each cast in a row, to the cap.
    expect(near(GrownRadius(radius, growth, 0, most), radius), "the first nova has the skill's radius",
           GrownRadius(radius, growth, 0, most), radius);
    expect(near(GrownRadius(radius, growth, 1, most), radius + growth), "after one cast, one growth",
           GrownRadius(radius, growth, 1, most), radius + growth);
    expect(near(GrownRadius(radius, growth, most, most), radius + growth * most),
           "after the most casts, the most growth");
    expect(near(GrownRadius(radius, growth, most + 5, most), radius + growth * most), "never more than the cap",
           GrownRadius(radius, growth, most + 5, most), radius + growth * most);
    expect(near(GrownRadius(radius, -4, 2, most), radius), "a negative growth is none");

    // Tendril Nova: a share of maximum Life for each enemy hit.
    expect(near(HealOfEnemies(10000, heal, 3), 10000 * heal / 100 * 3), "three enemies heal three shares",
           HealOfEnemies(10000, heal, 3), 10000 * heal / 100 * 3);
    expect(near(HealOfEnemies(10000, heal, 0), 0) && near(HealOfEnemies(0, heal, 3), 0) &&
               near(HealOfEnemies(10000, 0, 3), 0),
           "no enemy, no Life or no percent heals nothing");

    // Blight's patch: whole pulses of the time, none for no time or no length.
    expect(PatchPulses(4.0, 0.5) == 8, "eight pulses in four seconds", PatchPulses(4.0, 0.5), 8);
    expect(PatchPulses(0.3, 0.5) == 0, "a time shorter than a pulse has none");
    expect(PatchPulses(0.3, 0.1) == 3, "a pulse is not lost to rounding", PatchPulses(0.3, 0.1), 3);
    expect(PatchPulses(0, 0.5) == 0 && PatchPulses(-2, 0.5) == 0 && PatchPulses(4.0, 0) == 0,
           "no time or no pulse length, none");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
