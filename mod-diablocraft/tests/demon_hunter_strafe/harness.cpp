// The real dc_demon_hunter_strafe.h (and Rapid Fire's shot arithmetic it uses). The rune names and numbers come from argv (read from
// the sheets and the tunables by test_demon_hunter_strafe.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_strafe.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::DemonHunter;
using namespace DC::Combat::DemonHunter::Strafe;

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
    // argv: the five runes A to E, then the shots a second of attack speed holds, Demolition's fraction of them, the skill's damage and
    // cost for that second, Demolition's damage, Icy Trail's damage, seconds and tick, the yards between patches, the speed while
    // strafing and Drifting Shadow's, Stinging Steel's bonus, the rockets a second and their damage, the slow's refresh.
    if (argc < 20)
        return 2;
    std::string const demolition = argv[1], icy = argv[2], rocket = argv[3], drifting = argv[4], steel = argv[5];
    double const shots = std::atof(argv[6]), fraction = std::atof(argv[7]), damage = std::atof(argv[8]), cost = std::atof(argv[9]),
                 grenadeDamage = std::atof(argv[10]), trailDamage = std::atof(argv[11]), trailSeconds = std::atof(argv[12]),
                 trailTick = std::atof(argv[13]), drop = std::atof(argv[14]), speed = std::atof(argv[15]), driftSpeed = std::atof(argv[16]),
                 bonus = std::atof(argv[17]), rockets = std::atof(argv[18]), rocketDamage = std::atof(argv[19]);
    double const refresh = argc > 20 ? std::atof(argv[20]) : 0.25;

    expect(RuneOf(demolition) == Rune::Demolition && RuneOf(icy) == Rune::IcyTrail && RuneOf(rocket) == Rune::RocketStorm &&
               RuneOf(drifting) == Rune::DriftingShadow && RuneOf(steel) == Rune::StingingSteel,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {demolition, icy, rocket, drifting, steel})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // The shots a second of attack speed holds; the grenades come slower, and a second still deals the sheet's damage and costs its cost.
    double const arrows = ShotsPerAttack(Rune::None, shots, fraction), grenades = ShotsPerAttack(Rune::Demolition, shots, fraction);
    expect(arrows == shots && near(grenades, shots * fraction) && grenades < arrows, "Demolition's grenades come at their fraction", grenades, shots * fraction);
    for (Rune other : {Rune::IcyTrail, Rune::RocketStorm, Rune::DriftingShadow, Rune::StingingSteel})
        expect(ShotsPerAttack(other, shots, fraction) == shots, "the other runes shoot at the skill's rate", ShotsPerAttack(other, shots, fraction), shots);
    expect(near(RapidFire::ShotPct(damage, arrows) * arrows, damage) && near(RapidFire::ShotPct(grenadeDamage, grenades) * grenades, grenadeDamage),
           "the shots of a second deal the sheet's damage, arrows and grenades");
    expect(near(RapidFire::ShotCost(cost, arrows) * arrows, cost) && near(RapidFire::ShotCost(cost, grenades) * grenades, cost),
           "and cost the sheet's cost", RapidFire::ShotCost(cost, grenades) * grenades, cost);
    unsigned fired = 0;
    double clock = 0;
    for (int update = 0; update < 1000; ++update)
        fired += Due(clock, 1, RapidFire::ShotSeconds(arrows, 1.0) * 1000.0);
    expect(std::fabs(double(fired) - arrows) <= 1.0, "a second of attack speed fires its shots", double(fired), arrows);

    // The slowed run: the share of normal speed taken away, and the slow held for two refreshes.
    expect(near(SlowPct(speed), 100.0 - speed) && speed < 100, "strafing at 75% takes a quarter off", SlowPct(speed), 100.0 - speed);
    expect(SlowPct(driftSpeed) == 0 && SlowPct(150) == 0 && SlowPct(-20) == 100, "Drifting Shadow's full speed takes none; the share stays between none and all");
    expect(near(HoldSeconds(refresh), 2 * refresh) && HoldSeconds(0) == 0 && HoldSeconds(-1) == 0, "the slow holds two refreshes", HoldSeconds(refresh), 2 * refresh);

    // A random enemy: a roll picks among the enemies there are, evenly, and never beyond them.
    expect(PickAt(0.0, 4) == 0 && PickAt(0.999, 4) == 3 && PickAt(1.0, 4) == 3 && PickAt(5.0, 4) == 3 && PickAt(-1.0, 4) == 0,
           "the ends of the roll pick the first and the last enemy");
    expect(PickAt(0.5, 0) == 0 && PickAt(0.5, 1) == 0, "none to pick, or one, the first");
    std::size_t picked[4] = {0, 0, 0, 0};
    for (int roll = 0; roll < 1000; ++roll)
        ++picked[PickAt(roll / 1000.0, 4)];
    expect(picked[0] == 250 && picked[1] == 250 && picked[2] == 250 && picked[3] == 250, "the rolls are shared evenly", double(picked[0]), 250);

    // Icy Trail: a patch where the Demon Hunter has moved far enough from the last, and its ticks making the damage.
    expect(!DropsPatch(drop - 0.01, drop) && DropsPatch(drop, drop) && DropsPatch(drop + 5, drop), "a patch at the distance, not before");
    expect(!DropsPatch(1000, 0), "no distance, never");
    unsigned const ticks = Dot::Ticks(trailSeconds, trailTick);
    expect(ticks > 1 && near(PatchTickPct(trailDamage, trailSeconds, trailTick) * ticks, trailDamage), "a patch's ticks make the damage",
           PatchTickPct(trailDamage, trailSeconds, trailTick) * ticks, trailDamage);
    expect(PatchTickPct(trailDamage, trailSeconds, 0) == 0, "no tick length, no damage");

    // Rocket Storm: a second's rockets share its damage.
    expect(near(RapidFire::ShotPct(rocketDamage, rockets) * rockets, rocketDamage) && near(RapidFire::RocketSeconds(rockets), 1.0 / rockets),
           "the rockets of a second deal the sheet's damage and are spaced across it");

    // Stinging Steel: the extra strike of a critical hit is the bonus's share of the shot.
    double const shot = RapidFire::ShotPct(damage, arrows);
    expect(near(CritExtraPct(shot, bonus), shot * bonus / 100.0), "a critical hit adds the bonus's share of the shot", CritExtraPct(shot, bonus), shot * bonus / 100.0);
    expect(CritExtraPct(0, bonus) == 0 && CritExtraPct(shot, 0) == 0 && CritExtraPct(-3, bonus) == 0 && CritExtraPct(shot, -9) == 0, "no shot, no bonus, no extra");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
