// The real dc_crusader_steed_charge.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_steed_charge.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/crusader/dc_crusader_steed_charge.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::SteedCharge;

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
    // argv: the thorns share per second, the heal percentage, the tick, the speed bonus, the drag distance, the five
    // runes A to E, then the ride's seconds and Endurance's seconds
    if (argc < 13)
        return 2;
    double const share = std::atof(argv[1]), heal = std::atof(argv[2]), tick = std::atof(argv[3]),
                 bonus = std::atof(argv[4]), keep = std::atof(argv[5]), ride = std::atof(argv[11]),
                 longRide = std::atof(argv[12]);
    std::string const barding = argv[6], endurance = argv[7], rejuvenation = argv[8], nightmare = argv[9],
                      draw = argv[10];

    expect(RuneOf(barding) == Rune::SpikedBarding && RuneOf(endurance) == Rune::Endurance &&
               RuneOf(rejuvenation) == Rune::Rejuvenation && RuneOf(nightmare) == Rune::Nightmare &&
               RuneOf(draw) == Rune::DrawAndQuarter,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {barding, endurance, rejuvenation, nightmare, draw})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Steed Charge") == Rune::None,
           "the base skill and a stranger are no rune");

    // A per-second number is paid in ticks: four of them make the second.
    expect(PerTick(share, tick) == share * tick, "a tick is its share of the second", PerTick(share, tick),
           share * tick);
    expect(PerTick(share, tick) * (1.0 / tick) > share - 1e-9 && PerTick(share, tick) * (1.0 / tick) < share + 1e-9,
           "the ticks of a second add up to the second");
    expect(PerTick(0, tick) == 0 && PerTick(share, 0) == 0 && PerTick(-share, tick) == 0,
           "no number, no tick or a negative one pays nothing");

    // Rejuvenation: the percentage of the maximum Life in total over the ride, whatever its length, not a second's.
    for (double seconds : {ride, longRide})
    {
        unsigned const ticks = unsigned(seconds / tick + 1e-9);
        double const whole = HealPerTick(10000, heal, ticks) * ticks;
        expect(whole > 10000 * heal / 100.0 - 1e-6 && whole < 10000 * heal / 100.0 + 1e-6,
               "the ticks of the ride add up to the percentage of the maximum Life", whole, 10000 * heal / 100.0);
    }
    expect(HealPerTick(10000, heal, 1) == 10000 * heal / 100.0, "a ride of one tick heals it all in that tick");
    expect(HealPerTick(0, heal, 8) == 0 && HealPerTick(-5, heal, 8) == 0, "no maximum Life heals nothing");
    expect(HealPerTick(10000, heal, 0) == 0 && HealPerTick(10000, 0, 8) == 0, "no tick or no percentage heals nothing");

    // The speed: the power file's multiplier as a percentage.
    expect(SpeedPct(bonus) == bonus * 100.0, "the bonus is a percentage", SpeedPct(bonus), bonus * 100.0);
    expect(SpeedPct(0) == 0 && SpeedPct(-1) == 0, "no bonus adds no speed");

    // Nightmare: the first pool always, then one only after the spacing.
    expect(DropsPool(false, 0, 3), "the first pool is dropped");
    expect(!DropsPool(true, 2.9, 3) && DropsPool(true, 3, 3) && DropsPool(true, 5, 3),
           "the next pool waits for the spacing");

    // Draw and Quarter: only an enemy farther than the distance is drawn, and it is set down at that distance.
    expect(Dragged(keep + 1, keep) && !Dragged(keep, keep) && !Dragged(keep - 1, keep),
           "only a farther enemy is drawn");
    expect(!Dragged(keep + 1, 0), "no distance draws none");
    expect(DragFraction(keep * 2, keep) == 0.5, "an enemy twice as far is drawn half the way",
           DragFraction(keep * 2, keep), 0.5);
    expect(DragFraction(keep / 2, keep) == 1.0, "a near enemy stays", DragFraction(keep / 2, keep), 1.0);

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
