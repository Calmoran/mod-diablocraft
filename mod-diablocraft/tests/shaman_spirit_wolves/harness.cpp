// The real dc_shaman_spirit_wolves.h, no core. Every number comes from argv (test_shaman_spirit_wolves.py reads the
// sheet and combat.csv): the skill's wolves and Spirit Pack's, the cone, the range, the lane's width, the speed, the
// trail's spacing, its damage a second and its tick, the Pack's Maelstrom per enemy and its cap, and Lightning Wolves'
// arc count. Prints "cases=N failures=M" and exits 0, or names each failing case and exits 1.
#include "classes/shaman/dc_shaman_spirit_wolves.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Shaman::SpiritWolves;

static int failures = 0;
static int cases = 0;

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
    if (argc < 13)
        return 2;
    unsigned const wolves = unsigned(std::atof(argv[1])), packWolves = unsigned(std::atof(argv[2])),
                   arcs = unsigned(std::atof(argv[12]));
    double const cone = std::atof(argv[3]), range = std::atof(argv[4]), width = std::atof(argv[5]),
                 speed = std::atof(argv[6]), spacing = std::atof(argv[7]), perSecond = std::atof(argv[8]),
                 tick = std::atof(argv[9]), perHit = std::atof(argv[10]), cap = std::atof(argv[11]);
    double const half = width / 2.0;
    double const pi = 3.14159265358979323846;

    expect(RuneOf("Spirit Pack") == Rune::SpiritPack && RuneOf("Lightning Wolves") == Rune::LightningWolves &&
               RuneOf("Fiery Wolves") == Rune::FieryWolves && RuneOf("Frost Wolves") == Rune::FrostWolves &&
               RuneOf("Spirit of the Pack") == Rune::SpiritOfThePack,
           "each rune by its name");
    expect(RuneOf("") == Rune::None && RuneOf("Chain Frost") == Rune::None, "the skill and a stranger are no rune");

    // What each rune adds, and nothing else does.
    Rune const all[] = {Rune::None,        Rune::SpiritPack,  Rune::LightningWolves,
                        Rune::FieryWolves, Rune::FrostWolves, Rune::SpiritOfThePack};
    for (Rune rune : all)
    {
        expect(Arcs(rune) == (rune == Rune::LightningWolves), "only Lightning Wolves arc");
        expect(LeavesTrail(rune) == (rune == Rune::FieryWolves), "only Fiery Wolves leave a trail");
        expect(Freezes(rune) == (rune == Rune::FrostWolves), "only Frost Wolves freeze");
        expect(Pays(rune) == (rune == Rune::SpiritOfThePack), "only the Spirit of the Pack pays");
    }

    // The fan: the skill's wolves down one line, the Pack's spread evenly across its cone, ends at the cone's edges.
    auto line = Fan(wolves, 0);
    expect(line.size() == wolves, "the skill sends its wolves", double(line.size()), wolves);
    bool straight = true;
    for (double angle : line)
        straight = straight && angle == 0;
    expect(straight, "all down the same line");
    auto fan = Fan(packWolves, cone);
    expect(fan.size() == packWolves, "the Pack sends its wolves", double(fan.size()), packWolves);
    expect(std::abs(fan.front() + cone * pi / 360.0) < 1e-9 && std::abs(fan.back() - cone * pi / 360.0) < 1e-9,
           "from one edge of the cone to the other", fan.front(), -cone * pi / 360.0);
    bool even = true;
    for (std::size_t i = 2; i < fan.size(); ++i)
        even = even && std::abs((fan[i] - fan[i - 1]) - (fan[1] - fan[0])) < 1e-9;
    expect(even, "evenly");
    expect(std::abs(fan[fan.size() / 2]) < 1e-9, "one wolf straight ahead (an odd pack)");
    expect(Fan(1, cone).size() == 1 && Fan(1, cone)[0] == 0, "a single wolf runs straight");
    expect(Fan(0, cone).empty(), "no wolves, no lanes");

    // A lane: ahead of the caster, up to the range, within half the width.
    expect(Touch(0, range / 2, 0, range, half).touched, "an enemy on the line is touched");
    expect(Touch(0, range / 2, half, range, half).touched && Touch(0, range / 2, -half, range, half).touched,
           "and on the edge of the lane");
    expect(!Touch(0, range / 2, half + 0.01, range, half).touched &&
               !Touch(0, range / 2, -half - 0.01, range, half).touched,
           "not beside it");
    expect(!Touch(0, -0.5, 0, range, half).touched, "not behind the caster");
    expect(Touch(0, range, 0, range, half).touched && !Touch(0, range + 0.01, 0, range, half).touched,
           "and not beyond the range");
    expect(std::abs(Touch(0, 12.5, 1, range, half).ahead - 12.5) < 1e-9, "how far along it stands",
           Touch(0, 12.5, 1, range, half).ahead, 12.5);
    // A turned lane: the same enemy is on it when the lane turns to it.
    expect(Touch(pi / 2, 0, 20, range, half).touched && !Touch(0, 0, 20, range, half).touched,
           "a lane turns to its bearing");
    expect(Touch(pi / 6, 20 * std::cos(pi / 6), 20 * std::sin(pi / 6), range, half).touched, "and to any other");
    // In the Pack, an enemy straight ahead is touched by the middle wolf only; far to the side by none.
    unsigned touching = 0;
    for (double angle : fan)
        touching += Touch(angle, 30, 0, range, half).touched;
    expect(touching == 1, "an enemy ahead in the Pack is touched by one wolf", touching, 1);
    touching = 0;
    for (double angle : line)
        touching += Touch(angle, 30, 0, range, half).touched;
    expect(touching == wolves, "an enemy on the skill's line is touched by every wolf", touching, wolves);
    touching = 0;
    for (double angle : fan)
        touching += Touch(angle, 30 * std::cos(pi / 3), 30 * std::sin(pi / 3), range, half).touched;
    expect(touching == 0, "an enemy outside the cone is touched by none", touching, 0);

    // The wave's time.
    expect(std::abs(Seconds(range, speed) - range / speed) < 1e-9 && Seconds(0, speed) == 0 && Seconds(range, 0) == 0,
           "the wave runs at its speed", Seconds(range, speed), range / speed);

    // The arc: the nearest, nearest first, no more than the sheet's count.
    std::vector<double> distances = {7, 2, 9, 4, 1, 8};
    auto near = Nearest(distances, arcs);
    expect(near.size() == arcs, "an arc reaches the sheet's count", double(near.size()), arcs);
    bool ordered = true;
    for (std::size_t i = 1; i < near.size(); ++i)
        ordered = ordered && distances[near[i - 1]] <= distances[near[i]];
    expect(ordered && distances[near[0]] == 1, "nearest first");
    expect(Nearest({3}, arcs).size() == 1 && Nearest({}, arcs).empty(), "fewer enemies than arcs");

    // The trail: a patch every spacing along the line; a pulse's share of the second.
    expect(Patches(range, spacing) == unsigned(std::floor(range / spacing + 1e-9)) && Patches(range, spacing) > 0,
           "a patch every spacing", Patches(range, spacing), std::floor(range / spacing));
    expect(Patches(range, 0) == 0 && Patches(0, spacing) == 0, "no spacing or no range, no patches");
    expect(std::abs(PulsePct(perSecond, tick) - perSecond * tick) < 1e-9,
           "a pulse is the second's percent of its seconds");
    expect(std::abs(PulsePct(perSecond, 0.5) - perSecond / 2) < 1e-9, "and half of it in half a second");

    // The Maelstrom: each enemy pays its share, never past the cap in all.
    double gained = 0;
    unsigned paid = 0;
    for (int enemy = 0; enemy < 100; ++enemy)
    {
        double const pay = Pay(gained, perHit, cap);
        expect(pay >= 0 && pay <= perHit, "an enemy pays no more than its share", pay, perHit);
        gained += pay;
        paid += pay > 0;
    }
    expect(gained == cap, "the cast stops at the cap", gained, cap);
    expect(Pay(0, perHit, cap) == perHit && Pay(cap, perHit, cap) == 0 && Pay(cap - 1, perHit, cap) == 1,
           "the first pays in full, the last only what is left");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
