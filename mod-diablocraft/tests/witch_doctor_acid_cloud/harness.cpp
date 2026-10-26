// The real dc_witch_doctor_acid_cloud.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_witch_doctor_acid_cloud.py); nothing is typed in here but distances to try. Prints "cases=N" and
// exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_acid_cloud.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::WitchDoctor::AcidCloud;

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
    // argv: the five runes A to E, the impact's delay, Corpse Bomb's, Kiss of Death's, the impact radius, Acid Rain's
    // radius, the cone's range and angle, the pool's damage, its seconds and its tick.
    if (argc < 16)
        return 2;
    std::string const corpse = argv[1], rain = argv[2], slime = argv[3], burn = argv[4], kiss = argv[5];
    double const base = std::atof(argv[6]), corpseDelay = std::atof(argv[7]), barfDelay = std::atof(argv[8]),
                 inner = std::atof(argv[9]), outer = std::atof(argv[10]), range = std::atof(argv[11]),
                 angle = std::atof(argv[12]), pool = std::atof(argv[13]), seconds = std::atof(argv[14]),
                 tick = std::atof(argv[15]);
    constexpr double Pi = 3.14159265358979323846;

    expect(RuneOf(corpse) == Rune::CorpseBomb && RuneOf(rain) == Rune::AcidRain && RuneOf(slime) == Rune::LobBlobBomb &&
               RuneOf(burn) == Rune::SlowBurn && RuneOf(kiss) == Rune::KissOfDeath,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : {corpse, rain, slime, burn, kiss})
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // What takes the rune's element: Slow Burn's frost is its pools', Corpse Bomb's Fire is its explosion's.
    expect(!ImpactTakesRuneElement(Rune::SlowBurn) && ImpactTakesRuneElement(Rune::CorpseBomb) &&
               ImpactTakesRuneElement(Rune::AcidRain),
           "Slow Burn's impact keeps the skill's element");
    expect(!PoolTakesRuneElement(Rune::CorpseBomb) && PoolTakesRuneElement(Rune::SlowBurn) &&
               PoolTakesRuneElement(Rune::LobBlobBomb),
           "Corpse Bomb's pool keeps the skill's element");

    // The impact's delay: the skill's, Corpse Bomb's later, Kiss of Death's own.
    expect(ImpactDelaySeconds(Rune::None, base, corpseDelay, barfDelay) == base &&
               ImpactDelaySeconds(Rune::SlowBurn, base, corpseDelay, barfDelay) == base,
           "the skill and most runes land after the base delay", base, 0);
    expect(ImpactDelaySeconds(Rune::CorpseBomb, base, corpseDelay, barfDelay) == corpseDelay,
           "Corpse Bomb explodes after its own delay", corpseDelay, 0);
    expect(ImpactDelaySeconds(Rune::KissOfDeath, base, corpseDelay, barfDelay) == barfDelay,
           "Kiss of Death spits after its own delay", barfDelay, 0);
    expect(ImpactDelaySeconds(Rune::KissOfDeath, 1, 2, 3) == 3 && ImpactDelaySeconds(Rune::CorpseBomb, 1, 2, 3) == 2 &&
               ImpactDelaySeconds(Rune::AcidRain, 1, 2, 3) == 1,
           "each delay is its own when they differ");

    // A burst reaches its band: the first from the middle to the inner radius, Acid Rain's second from there to the
    // outer.
    expect(InBand(0, -1, inner) && InBand(inner, -1, inner) && !InBand(inner + 0.01, -1, inner),
           "the first burst reaches the inner radius, ends and all");
    expect(!InBand(inner, inner, outer) && InBand(inner + 0.01, inner, outer) && InBand(outer, inner, outer) &&
               !InBand(outer + 0.01, inner, outer),
           "the outer ring is past the inner radius and within the outer");
    expect(outer > inner, "Acid Rain's area is wider", outer, inner);

    // The cone: in front of the Witch Doctor within the range and half the angle each side.
    double const heading = Pi / 3;
    expect(InCone(std::cos(heading) * 10, std::sin(heading) * 10, heading, range, angle),
           "straight ahead is in the cone");
    expect(!InCone(std::cos(heading) * (range + 0.5), std::sin(heading) * (range + 0.5), heading, range, angle),
           "past the range is out");
    double const edge = angle * Pi / 360.0;
    expect(InCone(std::cos(heading + edge * 0.99) * 10, std::sin(heading + edge * 0.99) * 10, heading, range, angle),
           "just inside the edge is in");
    expect(!InCone(std::cos(heading + edge * 1.1) * 10, std::sin(heading + edge * 1.1) * 10, heading, range, angle),
           "just past the edge is out");
    expect(!InCone(std::cos(heading + Pi) * 10, std::sin(heading + Pi) * 10, heading, range, angle), "behind is out");
    double const west = -Pi + 0.01;
    expect(InCone(std::cos(west - edge * 0.5) * 10, std::sin(west - edge * 0.5) * 10, west, range, angle), "the cone across the half turn");
    expect(InCone(0, 0, heading, range, angle), "the point the cone starts at is in it");

    // The pool's ticks together deal its damage.
    unsigned const ticks = unsigned(std::floor(seconds / tick + 1e-9));
    expect(ticks > 1 && std::fabs(TickPct(pool, seconds, tick) * ticks - pool) < 1e-6, "the ticks make the damage",
           TickPct(pool, seconds, tick) * ticks, pool);
    expect(TickPct(pool, seconds, 0) == 0, "no tick, no damage");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
