// The real dc_necromancer_leech_math.h. The rune names and numbers come from argv (read from the sheets by test_necromancer_leech.py);
// nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/necromancer/dc_necromancer_leech_math.h"
#include "combat/dc_healing_table.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Necromancer::Leech;

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
    // argv: the five runes A to E; the heal when struck, Osmosis' regeneration per enemy and its most enemies, Cursed Ground's heal,
    // Sanguine End's share
    if (argc < 16)
        return 2;
    std::string const names[5] = {argv[1], argv[2], argv[3], argv[4], argv[5]};
    double const heal = std::atof(argv[6]), perEnemy = std::atof(argv[7]), groundPct = std::atof(argv[9]), share = std::atof(argv[10]);
    unsigned const most = unsigned(std::atoi(argv[8]));
    // then Osmosis' share of the Healing table, and the table's values (sheet) at levels 10, 35 and 70, and the sheet's level-70 Life per second
    double const osmosisShare = std::atof(argv[11]), table10 = std::atof(argv[12]), table35 = std::atof(argv[13]),
                 table70 = std::atof(argv[14]), tooltip = std::atof(argv[15]);

    expect(RuneOf(names[0]) == Rune::Osmosis && RuneOf(names[1]) == Rune::Transmittable && RuneOf(names[2]) == Rune::SanguineEnd &&
               RuneOf(names[3]) == Rune::CursedGround && RuneOf(names[4]) == Rune::BloodFlask,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& name : names)
        seen.insert(int(RuneOf(name)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "no two runes share a name, and none is None");
    expect(RuneOf("") == Rune::None && RuneOf("Leech") == Rune::None && RuneOf("osmosis") == Rune::None,
           "the skill itself and a misspelling are no rune");

    // Every rune curses the enemies and heals when struck but Cursed Ground, which curses the ground.
    expect(HealsWhenStruck(Rune::None) && HealsWhenStruck(Rune::Osmosis) && HealsWhenStruck(Rune::Transmittable) &&
               HealsWhenStruck(Rune::SanguineEnd) && HealsWhenStruck(Rune::BloodFlask),
           "the skill and the other runes heal when struck");
    expect(!HealsWhenStruck(Rune::CursedGround) && !CursesEnemies(Rune::CursedGround) && CursesEnemies(Rune::None) &&
               CursesEnemies(Rune::BloodFlask),
           "Cursed Ground curses the ground, not the enemies");

    // The heal of a struck hit.
    expect(near(StruckHeal(100000, heal), 100000 * heal / 100.0), "a struck hit heals its share of the Life", StruckHeal(100000, heal),
           100000 * heal / 100.0);
    expect(StruckHeal(0, heal) == 0.0 && StruckHeal(-1, heal) == 0.0 && StruckHeal(100000, 0) == 0.0 && StruckHeal(100000, -2) == 0.0,
           "no Life or no percent: no heal");

    // Osmosis: per enemy, up to the most.
    expect(OsmosisRegen(0, perEnemy, most) == 0.0, "no enemy cursed, no regeneration");
    expect(near(OsmosisRegen(5, perEnemy, most), 5 * perEnemy), "each enemy cursed gives its share");
    expect(near(OsmosisRegen(most, perEnemy, most), most * perEnemy) && near(OsmosisRegen(most + 30, perEnemy, most), most * perEnemy),
           "none past the most enemies", OsmosisRegen(most + 30, perEnemy, most), most * perEnemy);
    expect(OsmosisRegen(5, -3, most) == 0.0, "a negative regeneration gives nothing");

    // Osmosis grows with the level along D3's Healing table: a low level, a middle one and 70.
    expect(near(DC::Combat::Healing::At(10), table10) && near(DC::Combat::Healing::At(35), table35) && near(DC::Combat::Healing::At(70), table70),
           "the table reads the sheet at levels 10, 35 and 70");
    expect(near(OsmosisPerEnemy(osmosisShare, DC::Combat::Healing::At(10)), osmosisShare * table10), "level 10: the share of the table",
           OsmosisPerEnemy(osmosisShare, DC::Combat::Healing::At(10)), osmosisShare * table10);
    expect(near(OsmosisPerEnemy(osmosisShare, DC::Combat::Healing::At(35)), osmosisShare * table35), "level 35: the share of the table");
    expect(near(std::round(OsmosisPerEnemy(osmosisShare, DC::Combat::Healing::At(70))), tooltip),
           "level 70 reaches the tooltip's number", OsmosisPerEnemy(osmosisShare, DC::Combat::Healing::At(70)), tooltip);
    expect(OsmosisPerEnemy(osmosisShare, DC::Combat::Healing::At(10)) < OsmosisPerEnemy(osmosisShare, DC::Combat::Healing::At(35)) &&
               OsmosisPerEnemy(osmosisShare, DC::Combat::Healing::At(35)) < OsmosisPerEnemy(osmosisShare, DC::Combat::Healing::At(70)),
           "a higher level gives more");
    expect(near(DC::Combat::Healing::At(9999), table70), "a level past the table reads the last row");
    expect(OsmosisPerEnemy(-1, 500) == 0.0 && OsmosisPerEnemy(0.0014, -5) == 0.0, "a negative share or table gives nothing");

    // Cursed Ground: the heal of one second for each enemy in the patch.
    expect(near(GroundHeal(100000, groundPct, 4), 4 * 100000 * groundPct / 100.0), "each enemy in the patch heals its share",
           GroundHeal(100000, groundPct, 4), 4 * 100000 * groundPct / 100.0);
    expect(GroundHeal(100000, groundPct, 0) == 0.0, "an empty patch heals nothing");

    // Sanguine End: a share of the Life per Kill.
    expect(near(KillHeal(50, share), 50 * share / 100.0) && near(KillHeal(50, share), 100.0 * (share / 200.0)), "the share of the Life per Kill",
           KillHeal(50, share), 50 * share / 100.0);
    expect(KillHeal(0, share) == 0.0 && KillHeal(-4, share) == 0.0 && KillHeal(50, 0) == 0.0 && KillHeal(50, -3) == 0.0,
           "no Life per Kill or no share: no heal");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
