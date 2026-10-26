// diablocraft-eg0m7 (Monk 2.3.14): the real dc_monk_epiphany.h. Every number comes from argv (data/tunables/monk.csv's
// and monk_skill_values.csv's, read by test_monk_epiphany.py); nothing is typed in here but the probe positions.
// Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/monk/dc_monk_epiphany.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

using namespace DC::Combat::Monk::Epiphany;

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
    return std::abs(a - b) < 1e-6;
}

int main(int argc, char** argv)
{
    // argv: dash min, dash max, dash offset, dash icd s, fireball length, fireball radius, duration s, Ascendance yards,
    // then the cone skills' radii (Crippling Wave, Way of the Hundred Fists, Lashing Tail Kick: skill_targeting.csv)
    if (argc < 12)
        return 2;
    double const minYards = std::atof(argv[1]), maxYards = std::atof(argv[2]), offset = std::atof(argv[3]),
                 icd = std::atof(argv[4]), length = std::atof(argv[5]), width = std::atof(argv[6]),
                 seconds = std::atof(argv[7]), stride = std::atof(argv[8]);
    double const cones[3] = {std::atof(argv[9]), std::atof(argv[10]), std::atof(argv[11])};

    // The dash: past the minimum, up to the maximum.
    expect(!Dashes(minYards, minYards, maxYards), "an enemy at the minimum is not dashed to", minYards);
    expect(Dashes(minYards + 0.01, minYards, maxYards), "just past the minimum dashes");
    expect(Dashes(maxYards, minYards, maxYards), "the maximum itself dashes");
    expect(!Dashes(maxYards + 0.01, minYards, maxYards), "past the maximum does not");
    expect(!Dashes(maxYards, 0, maxYards), "an open minimum never dashes");

    // The landing: offset yards short of the enemy, on the line from the Monk.
    Point const land = Landing({0, 0}, {20, 0}, offset);
    expect(near(land.x, 20 - offset) && near(land.y, 0), "lands offset short on a straight line", land.x, 20 - offset);
    Point const diagonal = Landing({1, 1}, {13, 17}, offset); // 20 yards away
    expect(near(std::hypot(13 - diagonal.x, 17 - diagonal.y), offset), "lands offset short on a diagonal",
           std::hypot(13 - diagonal.x, 17 - diagonal.y), offset);
    expect(near(std::hypot(diagonal.x - 1, diagonal.y - 1), 20 - offset), "and on the line from the Monk");
    Point const close = Landing({0, 0}, {offset - 1, 0}, offset);
    expect(near(close.x, 0) && near(close.y, 0), "an enemy inside the offset leaves the Monk where it is");

    // diablocraft-q73to: a cone skill cast at a selected enemy 12 yards away (past every cone, inside Epiphany's reach). It
    // dashes (past the minimum), lands offset short of the enemy on the line, and the cone searched from there holds it;
    // without the dash the enemy is outside the cone.
    double const selected = 12;
    Point const start{0, 0}, enemy{selected, 0};
    expect(Dashes(selected, minYards, maxYards), "an enemy 12 yards away is dashed to");
    Point const arrived = Landing(start, enemy, offset);
    double const left = std::hypot(enemy.x - arrived.x, enemy.y - arrived.y);
    for (double radius : cones)
    {
        expect(selected > radius, "past the cone's radius without the dash", selected, radius);
        expect(left <= radius, "inside the cone's radius after the dash", left, radius);
    }

    // The internal cooldown.
    std::optional<std::uint64_t> last;
    std::uint64_t const ms = std::uint64_t(icd * 1000 + 0.5);
    expect(Ready(1000, last, ms), "the first is ready");
    expect(!Ready(1000 + ms - 1, last, ms), "inside the cooldown it is not", double(ms));
    expect(Ready(1000 + ms, last, ms), "at the cooldown it is again");
    expect(!Ready(1000 + ms + 1, last, ms), "and the new one starts its own");
    std::optional<std::uint64_t> fromZero;
    expect(Ready(0, fromZero, ms) && !Ready(ms - 1, fromZero, ms), "a cast at time 0 still starts the cooldown");

    // Inner Fire's piercing fireball: a line ahead, length long, width either side.
    expect(OnLine({0, 0}, 0, {length / 2, width - 0.1}, length, width), "inside the width is hit");
    expect(!OnLine({0, 0}, 0, {length / 2, width + 0.1}, length, width), "outside the width is not");
    expect(!OnLine({0, 0}, 0, {-1, 0}, length, width), "behind the Monk is not");
    expect(!OnLine({0, 0}, 0, {length + 0.1, 0}, length, width), "past the length is not");
    expect(OnLine({0, 0}, std::acos(-1.0) / 2, {0, length - 1}, length, width), "the line turns with the facing");
    expect(!OnLine({0, 0}, std::acos(-1.0) / 2, {length / 2, 0}, length, width), "and leaves the old direction");

    // The Spirit per second: once a second for the buff's life.
    expect(Payments(seconds) == unsigned(seconds), "one payment a second", Payments(seconds), seconds);
    expect(Payments(0) == 0 && Payments(-1) == 0, "no buff, no payment");

    // Ascendance's stride.
    Stride walk;
    walk.Add(stride / 2);
    walk.Add(-5);
    expect(!walk.Armed(stride), "half the distance does not arm it", walk.moved, stride);
    walk.Add(stride / 2 - 0.01);
    expect(!walk.Armed(stride), "just short does not");
    walk.Add(0.01);
    expect(walk.Armed(stride), "the distance arms it", walk.moved, stride);
    walk.Spend();
    expect(!walk.Armed(stride) && walk.moved == 0, "the stun spends it");
    walk.Add(stride * 3);
    expect(!walk.Armed(0), "an open distance never arms it");

    // Ascendance in the cast path's order: the cast starts (Begin), its dash lands (Dashed), its hits land (Hit).
    double const dash = 18 - offset; // Fists of Thunder aimed 18 yards away dashes 13
    Ascent carried;
    carried.Begin(7, stride);
    expect(carried.cast == 0, "a cast that starts with no stride is not armed yet");
    carried.Dashed(7, dash, stride);
    expect(carried.Hit(7, 5000), "the dash that fills the stride arms the attack it carries", carried.stride.moved, stride);
    expect(carried.stride.moved == 0, "and that attack's first hit spends it");
    expect(carried.Hit(7, 5000), "the attack's other hits in the same moment stun too");
    expect(!carried.Hit(7, 5001), "a later hit of the same spell does not");
    expect(!carried.Hit(7, 5000) && carried.cast == 0, "and it is cleared");
    Ascent shortDash;
    shortDash.Begin(7, stride);
    shortDash.Dashed(7, stride / 2, stride);
    expect(!shortDash.Hit(7, 5000) && shortDash.stride.moved == stride / 2, "a short dash arms nothing and is kept");
    Ascent walked;
    walked.stride.Add(stride);
    walked.Begin(9, stride);
    expect(!walked.Hit(8, 5000), "another spell's hit does not stun");
    expect(walked.Hit(9, 5000), "a cast that starts with the stride full stuns");
    Ascent missed;
    missed.stride.Add(stride);
    missed.Begin(9, stride);
    missed.Begin(10, stride);
    expect(missed.Hit(10, 5000), "a cast that hit nothing spends nothing: the next cast still stuns");
    Ascent open;
    open.Dashed(7, stride * 3, 0);
    expect(!open.Hit(7, 5000), "a dash without Ascendance (an open distance) arms nothing");

    std::printf("cases=%d failures=%d\n", cases, failures);
    return failures ? 1 : 0;
}
