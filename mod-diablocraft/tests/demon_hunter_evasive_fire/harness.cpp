// The real dc_demon_hunter_evasive_fire.h and dc_demon_hunter_buffs.h. The rune names and numbers come from argv (read
// from the sheets and the tunables by test_demon_hunter_evasive_fire.py); nothing is typed in here. Prints "cases=N"
// and exits 0, or names the first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_buffs.h"
#include "classes/demon_hunter/dc_demon_hunter_evasive_fire.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::EvasiveFire;

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
    // argv: the five runes A to E, the search radius, the search cone, the enemies hit in all, the spread cone,
    // Hardened's armor and its seconds.
    if (argc < 12)
        return 2;
    std::string const hardened = argv[1], covering = argv[2], parting = argv[3], surge = argv[4], focus = argv[5];
    double const radius = std::atof(argv[6]), search = std::atof(argv[7]), spread = std::atof(argv[9]),
                 armor = std::atof(argv[10]), seconds = std::atof(argv[11]);
    std::size_t const hit = std::size_t(std::atoi(argv[8]));
    constexpr double Pi = 3.14159265358979323846;

    expect(RuneOf(hardened) == Rune::Hardened && RuneOf(covering) == Rune::CoveringFire &&
               RuneOf(parting) == Rune::PartingGift && RuneOf(surge) == Rune::Surge && RuneOf(focus) == Rune::Focus,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {hardened, covering, parting, surge, focus})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Hardened and Focus give something else instead of the backflip; every other rune flips.
    expect(!Backflips(Rune::Hardened) && !Backflips(Rune::Focus), "Hardened and Focus do not backflip");
    expect(Backflips(Rune::None) && Backflips(Rune::CoveringFire) && Backflips(Rune::PartingGift) &&
               Backflips(Rune::Surge),
           "the skill and the other runes backflip");

    // The trigger: an enemy near enough, inside the cone in front.
    expect(EnemyInFront({radius}, {0.0}, 0.0, radius, search),
           "an enemy at the edge of the radius, dead ahead, triggers it");
    expect(!EnemyInFront({radius + 0.1}, {0.0}, 0.0, radius, search), "an enemy past the radius does not");
    expect(!EnemyInFront({3.0}, {Pi}, 0.0, radius, search), "an enemy behind does not");
    expect(EnemyInFront({3.0}, {search * Pi / 360 - 0.01}, 0.0, radius, search) &&
               !EnemyInFront({3.0}, {search * Pi / 360 + 0.01}, 0.0, radius, search),
           "the cone is half the search angle to either side");
    expect(EnemyInFront({50.0, 4.0}, {Pi, 0.0}, 0.0, radius, search), "one enemy that qualifies is enough");
    expect(!EnemyInFront({}, {}, 0.0, radius, search), "nobody around, no flip");

    // The bolts: the enemy aimed at and the nearest ones beside it, inside the spread.
    std::vector<double> distances{20, 12, 30, 8, 16};
    std::vector<double> bearings{0.0, 0.1, -0.1, spread * Pi / 360 + 0.2, 0.05};
    std::vector<bool> aimedAt{true, false, false, false, false};
    auto beside = Seek(distances, bearings, aimedAt, 80, 0.0, spread, hit - 1);
    expect(beside.size() == hit - 1 && beside[0] == 1 && beside[1] == 4, "the nearest two beside the enemy aimed at",
           double(beside.size()), double(hit - 1));
    expect(Seek(distances, bearings, aimedAt, 80, 0.0, 360, hit - 1)[0] == 3,
           "without the spread the nearest is the one off to the side");

    // Hardened's armor lasts its seconds and ends.
    Buffs::Held held;
    auto const ms = std::uint64_t(seconds * 1000);
    expect(Buffs::Add(held, 1000, ms, 1) == 1, "the armor is one stack");
    expect(Buffs::Worth(held, 1000 + ms - 1, armor) == armor, "the armor is on until its time is up",
           Buffs::Worth(held, 1000 + ms - 1, armor), armor);
    expect(Buffs::Worth(held, 1000 + ms, armor) == 0, "and off from that moment");
    expect(Buffs::Add(held, 1000 + ms / 2, ms, 1) == 1 && held.until == 1000 + ms / 2 + ms,
           "a second one restarts the time without a second stack");
    expect(Buffs::Add(held, 1000 + 10 * ms, ms, 1) == 1, "one that ran out starts again from one stack");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
