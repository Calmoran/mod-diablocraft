// The real dc_crusader_shield_bash.h and dc_crusader_block_share.h. The rune names, the sheets' numbers and the power
// file's reaches come from argv (read by test_crusader_shield_bash.py); nothing is typed in here. Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/crusader/dc_crusader_block_share.h"
#include "classes/crusader/dc_crusader_shield_bash.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader;
using namespace DC::Combat::Crusader::ShieldBash;

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
    // argv: damage, share, stop, area, arc degrees, pound radius, pound arc degrees, extra yards, extra degrees, then
    // the five runes A to E
    if (argc < 17)
        return 2;
    double const damage = std::atof(argv[1]), share = std::atof(argv[2]), stop = std::atof(argv[3]),
                 area = std::atof(argv[4]), arc = ArcRadians(std::atof(argv[5])), poundArea = std::atof(argv[6]),
                 poundArc = ArcRadians(std::atof(argv[7])), extraYards = std::atof(argv[8]),
                 extraArc = ArcRadians(std::atof(argv[9]));
    std::string const crumble = argv[10], shattered = argv[11], cross = argv[12], pound = argv[13], oneOnOne = argv[14];
    double const armLength = std::atof(argv[15]), armWidth = std::atof(argv[16]);

    expect(RuneOf(crumble) == Rune::Crumble && RuneOf(shattered) == Rune::ShatteredShield &&
               RuneOf(cross) == Rune::ShieldCross && RuneOf(pound) == Rune::Pound && RuneOf(oneOnOne) == Rune::OneOnOne,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {crumble, shattered, cross, pound, oneOnOne})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");
    expect(ReplacesHit(Rune::Crumble) && ReplacesHit(Rune::Pound), "Crumble and Pound are the bash's own hit");
    expect(!ReplacesHit(Rune::ShatteredShield) && !ReplacesHit(Rune::ShieldCross) && !ReplacesHit(Rune::OneOnOne) &&
               !ReplacesHit(Rune::None),
           "no other rune's numbers are the bash's hit");

    // The share of the Block Chance: 300% of a 30% Block Chance is 90 points on 700.
    expect(BlockShare::Pct(damage, share, 30) == damage + share * 30 / 100, "the share adds points of weapon damage",
           BlockShare::Pct(damage, share, 30), damage + share * 30 / 100);
    expect(BlockShare::Pct(damage, share, 0) == damage, "no Block Chance, no share");
    expect(std::fabs(BlockShare::Factor(damage, share, 30) * damage - BlockShare::Pct(damage, share, 30)) < 1e-9,
           "the multiplier of the plain hit gives the same total");
    expect(BlockShare::Factor(0, share, 30) == 1.0, "no damage to multiply, no factor");
    expect(BlockShare::Pct(damage, share, 60) > BlockShare::Pct(damage, share, 30), "more Block Chance, more damage");

    // The charge stops `stop` yards short on the line to the enemy, and not at all when it is that near.
    Point const from{0, 0};
    Point const landed = Landing(from, {20, 0}, stop);
    expect(std::fabs(landed.x - (20 - stop)) < 1e-9 && landed.y == 0, "the charge stops short of the enemy", landed.x,
           20 - stop);
    Point const diagonal = Landing(from, {30, 40}, stop);
    expect(std::fabs(std::hypot(30 - diagonal.x, 40 - diagonal.y) - stop) < 1e-9,
           "on the diagonal too, stop yards short");
    Point const near = Landing(from, {stop - 1, 0}, stop);
    expect(near.x == 0 && near.y == 0, "an enemy already near is not charged at");
    expect(Landing(from, from, stop).x == 0, "an enemy on top of you is not charged at");

    // The cone: inside the reach and the half angle.
    expect(InCone(area, arc / 2, area, arc), "the edge of the cone is inside", area, arc / 2);
    expect(!InCone(area + 0.01, 0, area, arc), "past the reach is outside");
    expect(!InCone(5, arc / 2 + 0.01, area, arc), "past the half angle is outside");
    expect(!InCone(5, 0, 0, arc), "no reach, no cone");
    expect(InCone(poundArea, poundArc / 2, poundArea, poundArc) && !InCone(poundArea + 1, 0, poundArea, poundArc),
           "Pound's short narrow cone");
    expect(poundArea < area && poundArc < arc, "Pound reaches less and narrower", poundArea, area);

    // The fragments hit more enemies: in the wider cone and not in the bash's own.
    expect(Fragment(area + 1, 0, area, arc, extraYards, extraArc), "an enemy just past the reach is a fragment's");
    expect(Fragment(5, arc / 2 + 0.05, area, arc, extraYards, extraArc),
           "an enemy just outside the angle is a fragment's");
    expect(!Fragment(5, 0, area, arc, extraYards, extraArc), "an enemy the bash hits is not a fragment's");
    expect(!Fragment(area + extraYards + 1, 0, area, arc, extraYards, extraArc), "past the wider reach is nobody's");
    expect(!Fragment(5, arc / 2 + extraArc / 2 + 0.05, area, arc, extraYards, extraArc),
           "past the wider angle is nobody's");

    // The cross: four arms from the Crusader, the first along the facing.
    expect(OnCross(5, 0, 0, 10, 2), "the arm ahead");
    expect(OnCross(0, 5, 0, 10, 2) && OnCross(-5, 0, 0, 10, 2) && OnCross(0, -5, 0, 10, 2), "the other three arms");
    expect(!OnCross(5, 5, 0, 10, 2), "between two arms is on none");
    expect(!OnCross(11, 0, 0, 10, 2), "past the arm's length is on none");
    expect(OnCross(5, 0.99, 0, 10, 2) && !OnCross(5, 1.01, 0, 10, 2), "the arm's width is across it, half each way");
    expect(OnCross(0, 5, 3.14159265358979323846 / 2, 10, 2), "the arms turn with the facing");
    expect(!OnCross(5, 0, 0, 0, 2) && !OnCross(5, 0, 0, 10, 0), "no length or no width, no arm");
    // The arms at the sheet's length and width: 20 yards long, 5 across.
    expect(OnCross(armLength - 1, 0, 0, armLength, armWidth) && OnCross(armLength, 0, 0, armLength, armWidth),
           "the far end of the arm is on it", armLength, 0);
    expect(!OnCross(armLength + 0.1, 0, 0, armLength, armWidth), "past the arm's length is on none", armLength + 0.1, armLength);
    expect(OnCross(5, armWidth / 2 - 0.01, 0, armLength, armWidth) && !OnCross(5, armWidth / 2 + 0.01, 0, armLength, armWidth),
           "the arm is half its width each side", armWidth / 2, 0);
    expect(OnCross(-armLength + 1, 0.5, 0, armLength, armWidth) && OnCross(0.5, armLength - 1, 0, armLength, armWidth),
           "behind and to the side on the other arms", armLength, armWidth);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
