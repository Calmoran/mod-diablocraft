// The real dc_necromancer_bone_armor_math.h. The rune names and numbers come from argv (read from the sheets by test_necromancer_bone_armor.py);
// nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_bone_armor_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::BoneArmor;

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
    // argv: the five runes A to E; the damage reduction a percent per enemy and the most enemies; the regeneration a percent per enemy;
    // the movement speed a percent per enemy
    if (argc < 10)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    double const reduction = std::atof(argv[6]), regen = std::atof(argv[8]), speed = std::atof(argv[9]);
    unsigned const most = unsigned(std::atoi(argv[7]));

    expect(RuneOf(names[0]) == Rune::VengefulArmaments && RuneOf(names[1]) == Rune::LimitedImmunity && RuneOf(names[2]) == Rune::Dislocation &&
               RuneOf(names[3]) == Rune::ThyFleshSustained && RuneOf(names[4]) == Rune::HarvestOfAnguish,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Bone Armor") == Rune::None && RuneOf("dislocation") == Rune::None,
           "the skill itself and a misspelling are no rune");

    // What the enemies hit give, up to the most.
    expect(PerEnemy(0, reduction, most) == 0.0, "no enemy hit, nothing");
    expect(near(PerEnemy(4, reduction, most), 4 * reduction), "each enemy hit gives its share");
    expect(near(PerEnemy(most, reduction, most), most * reduction) && near(PerEnemy(most + 40, reduction, most), most * reduction),
           "none past the most enemies", PerEnemy(most + 40, reduction, most), most * reduction);
    expect(near(PerEnemy(most + 3, regen, most), most * regen) && near(PerEnemy(2, speed, most), 2 * speed),
           "the regeneration and the speed likewise");
    expect(PerEnemy(5, -3, most) == 0.0, "a negative share gives nothing");

    // What the armor lets through.
    expect(near(TakenFactor(0), 1.0) && near(TakenFactor(30), 0.7), "a hit is cut by the percent");
    expect(near(TakenFactor(PerEnemy(most, reduction, most)), 1.0 - most * reduction / 100.0), "the full armor takes the most off");
    expect(TakenFactor(100) == 0.0 && TakenFactor(250) == 0.0, "never below nothing");
    expect(near(TakenFactor(-20), 1.0), "a negative cut takes nothing off");

    // Limited Immunity alone absorbs every hit.
    expect(AbsorbsAll(Rune::LimitedImmunity), "Limited Immunity absorbs everything");
    expect(!AbsorbsAll(Rune::None) && !AbsorbsAll(Rune::VengefulArmaments) && !AbsorbsAll(Rune::Dislocation) &&
               !AbsorbsAll(Rune::ThyFleshSustained) && !AbsorbsAll(Rune::HarvestOfAnguish),
           "no other rune does");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
