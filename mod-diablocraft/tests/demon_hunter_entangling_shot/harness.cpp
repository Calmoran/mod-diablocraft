// The real dc_demon_hunter_entangling_shot.h and dc_demon_hunter_dot.h. The rune names and numbers come from argv (read from
// the sheets and the tunables by test_demon_hunter_entangling_shot.py); nothing is typed in here. Prints "cases=N" and exits
// 0, or names the first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_dot.h"
#include "classes/demon_hunter/dc_demon_hunter_entangling_shot.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::EntanglingShot;

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

using Ids = std::vector<std::uint64_t>;

int main(int argc, char** argv)
{
    // argv: the five runes A to E, the enemies entangled, Chain Gang's, Shock Collar's damage percent and seconds, its tick
    // length.
    if (argc < 11)
        return 2;
    std::string const burden = argv[1], chain = argv[2], shock = argv[3], justice = argv[4], bounty = argv[5];
    std::size_t const base = std::size_t(std::atoi(argv[6])), chained = std::size_t(std::atoi(argv[7]));
    double const damage = std::atof(argv[8]), seconds = std::atof(argv[9]), tick = std::atof(argv[10]);

    expect(RuneOf(burden) == Rune::HeavyBurden && RuneOf(chain) == Rune::ChainGang && RuneOf(shock) == Rune::ShockCollar &&
               RuneOf(justice) == Rune::JusticeIsServed && RuneOf(bounty) == Rune::BountyHunter,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {burden, chain, shock, justice, bounty})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // A first shot: the enemy hit and the nearest others, as many as the sheet's count.
    Ids const around{12, 13, 14, 15, 16};
    auto group = Entangled({}, 1000, 11, around, base);
    expect(group.size() == base && group[0] == 11, "the enemy hit is entangled first", double(group.size()), double(base));
    expect(group.size() < 2 || group[1] == 12, "the nearest other follows it");
    group = Entangled({}, 1000, 11, around, chained);
    expect(group.size() == chained && group[chained - 1] == 11 + chained - 1, "Chain Gang entangles its larger count, nearest first",
           double(group.size()), double(chained));
    expect(Entangled({}, 1000, 11, {}, base).size() == 1, "nobody around, the enemy hit alone");
    expect(Entangled({}, 1000, 11, {12}, 5).size() == 2, "fewer enemies than the count, fewer entangled");
    expect(Entangled({}, 1000, 11, around, 0).empty(), "a count of nothing entangles nothing");

    // The core chains the shot to as many enemies as the entangle count: they are entangled, and the engine does not hit them.
    auto first = Entangled({}, 1000, 11, around, base);
    expect(LeftToEngine(true), "the enemy shot at takes the engine's hit");
    expect(!LeftToEngine(false), "an enemy the core chained the shot to does not");
    expect(first.size() == base && first[1] == 12 && !LeftToEngine(false),
           "a chained enemy is entangled and takes no hit", double(first.size()), double(base));

    // A shot at an enemy still entangled refreshes everyone entangled.
    std::vector<Tie> held{{11, 5000}, {20, 5000}, {21, 5000}};
    group = Entangled(held, 3000, 11, around, 3);
    expect(group == Ids({11, 20, 21}), "the enemies still entangled stay and are refreshed");
    group = Entangled(held, 3000, 11, around, 4);
    expect(group == Ids({11, 20, 21, 12}), "room left is filled from the nearest");
    group = Entangled(held, 3000, 11, around, 2);
    expect(group == Ids({11, 20}), "the count is the most, the enemies already entangled included");
    group = Entangled(held, 3000, 11, {20, 12}, 4);
    expect(group == Ids({11, 20, 21, 12}), "an enemy is entangled once");
    // A shot at an enemy that is not one of them starts afresh.
    group = Entangled(held, 3000, 30, around, base);
    expect(group[0] == 30 && std::find(group.begin(), group.end(), 20) == group.end(), "a shot at another enemy keeps the old ties out");
    // The ties that ran out are gone.
    std::vector<Tie> lapsed{{11, 5000}, {20, 2999}, {21, 3000}};
    group = Entangled(lapsed, 3000, 11, around, 3);
    expect(group == Ids({11, 12, 13}), "a tie that ran out is not refreshed, the moment it runs out included");
    std::vector<Tie> primaryLapsed{{11, 3000}, {20, 5000}};
    group = Entangled(primaryLapsed, 3000, 11, around, 3);
    expect(group == Ids({11, 12, 13}), "an enemy whose own tie ran out is a fresh shot");

    // Shock Collar: the damage spread over its seconds in ticks of the tunable length.
    unsigned const ticks = Dot::Ticks(seconds, tick);
    expect(ticks == unsigned(seconds / tick + 0.5), "the ticks that fit the rune's seconds", ticks, seconds / tick);
    expect(Dot::TickPct(damage, ticks) * ticks > damage - 1e-9 && Dot::TickPct(damage, ticks) * ticks < damage + 1e-9,
           "the ticks together deal the rune's damage", Dot::TickPct(damage, ticks) * ticks, damage);
    expect(Dot::Ticks(seconds, 0) == 0 && Dot::Ticks(0, tick) == 0, "no tick length or no seconds, no ticks");
    expect(Dot::TickPct(damage, 0) == 0, "no ticks, no share");
    expect(Dot::Ticks(2, 0.5) == 4 && Dot::Ticks(2.2, 0.5) == 4, "a tick that does not fit whole is not dealt");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
