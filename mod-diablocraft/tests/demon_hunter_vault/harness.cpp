// The real dc_demon_hunter_vault.h. The rune names and numbers come from argv (read from the sheets and the tunables by
// test_demon_hunter_vault.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_vault.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::Vault;

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
    // argv: the five runes A to E, then the trail's damage, seconds and tick, the box's length and width, the trail's
    // width and the arrows.
    if (argc < 13)
        return 2;
    std::string const trail = argv[1], acrobatics = argv[2], shot = argv[3], tumble = argv[4], roll = argv[5];
    double const damage = std::atof(argv[6]), seconds = std::atof(argv[7]), tick = std::atof(argv[8]),
                 length = std::atof(argv[9]), width = std::atof(argv[10]), trailWidth = std::atof(argv[11]);
    unsigned const arrows = unsigned(std::atoi(argv[12]));
    double const north = std::acos(-1.0) / 2;

    expect(RuneOf(trail) == Rune::TrailOfCinders && RuneOf(acrobatics) == Rune::Acrobatics &&
               RuneOf(shot) == Rune::ActionShot && RuneOf(tumble) == Rune::Tumble && RuneOf(roll) == Rune::RattlingRoll,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {trail, acrobatics, shot, tumble, roll})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // Where an enemy stands against a path: along it and to its side, for a path east and one north.
    Place east = PlaceOn(10, 10, 0, 13, 12);
    expect(std::fabs(east.along - 3) < 1e-9 && std::fabs(east.across - 2) < 1e-9, "east: three along, two to the side",
           east.along, east.across);
    Place up = PlaceOn(10, 10, north, 8, 14);
    expect(std::fabs(up.along - 4) < 1e-9 && std::fabs(up.across - 2) < 1e-9, "north: four along, two to the side",
           up.along, up.across);
    Place behind = PlaceOn(0, 0, 0, -3, 0);
    expect(behind.along < 0, "behind the start is a negative distance along", behind.along, 0);

    // Rattling Roll: the box that travels with the Demon Hunter, its length along the path and its width across.
    expect(InBox({length / 2, width / 2}, length, width), "the corner of the box is in it");
    expect(!InBox({length / 2 + 0.1, 0}, length, width), "past its length is out of it", length / 2 + 0.1, length);
    expect(!InBox({0, width / 2 + 0.1}, length, width), "past its width is out of it", width / 2 + 0.1, width);
    expect(InBox({-length / 2, 0}, length, width), "the back of the box is in it");
    expect(!InBox({0, 0}, 0, width) && !InBox({0, 0}, length, 0), "a box with no size holds nothing");

    // Trail of Cinders: the band left behind, from the start to the end of the path, its width across.
    expect(InBand({10, trailWidth / 2}, 35, trailWidth) && InBand({0, 0}, 35, trailWidth) &&
               InBand({35, 0}, 35, trailWidth),
           "the trail holds the path from start to end");
    expect(!InBand({10, trailWidth / 2 + 0.1}, 35, trailWidth), "wider than the trail is out of it");
    expect(!InBand({-0.1, 0}, 35, trailWidth) && !InBand({35.1, 0}, 35, trailWidth),
           "before the start and past the end are out of it");
    expect(!InBand({10, 0}, 35, 0), "a trail with no width holds nothing");

    // The fire's ticks together deal the sheet's damage.
    unsigned const ticks = Dot::Ticks(seconds, tick);
    expect(ticks > 1, "the trail ticks more than once", ticks, 2);
    expect(std::fabs(TrailTickPct(damage, seconds, tick) * ticks - damage) < 1e-9, "the ticks make the damage",
           TrailTickPct(damage, seconds, tick) * ticks, damage);
    expect(TrailTickPct(damage, seconds, 0) == 0, "no tick length, no damage");
    double clock = 0;
    unsigned struck = 0;
    int const updates = int(seconds * 1000.0 / 67.0);
    for (int update = 0; update < updates; ++update)
        struck += Due(clock, 67, tick * 1000.0);
    expect(std::fabs(double(struck) - updates * 0.067 / tick) < 1.0, "a tick every interval in server updates of 67 ms",
           double(struck), updates * 0.067 / tick);

    // Action Shot: the arrows go to the enemies nearest first, shared round them, and every one of a few enemies is
    // shot at.
    expect(arrows > 1, "more than one arrow", arrows, 2);
    expect(ShotAt(0, 0) == 0, "no enemy, none chosen");
    for (unsigned enemies = 1; enemies <= arrows; ++enemies)
    {
        std::set<std::size_t> shotAt;
        for (unsigned arrow = 0; arrow < arrows; ++arrow)
        {
            std::size_t const chosen = ShotAt(arrow, enemies);
            expect(chosen < enemies, "an arrow flies at an enemy there is", double(chosen), enemies);
            shotAt.insert(chosen);
        }
        expect(shotAt.size() == enemies, "every enemy of a few is shot at", double(shotAt.size()), enemies);
    }
    expect(ShotAt(0, 3) == 0 && ShotAt(1, 3) == 1 && ShotAt(3, 3) == 0,
           "the first arrow flies at the nearest and they go round");
    expect(CritBonus(Rune::ActionShot) >= 100 && CritBonus(Rune::Tumble) == 0 && CritBonus(Rune::TrailOfCinders) == 0 &&
               CritBonus(Rune::RattlingRoll) == 0 && CritBonus(Rune::Acrobatics) == 0 && CritBonus(Rune::None) == 0,
           "only Action Shot's arrows are sure to crit");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
