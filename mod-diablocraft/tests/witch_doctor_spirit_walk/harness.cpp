// The real dc_witch_doctor_spirit_walk.h. The rune names and numbers come from argv (read from the sheets by
// test_witch_doctor_spirit_walk.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_spirit_walk.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::WitchDoctor::SpiritWalk;

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
    // argv: the five runes A to E, then the base run speed percent, Severance's additional percent, Honored Guest's
    // percent of maximum Mana, Healing Journey's percent of maximum Life, the walk's seconds and Jaunt's seconds
    if (argc < 12)
        return 2;
    std::string const severance = argv[1], jaunt = argv[2], shock = argv[3], guest = argv[4], journey = argv[5];
    double const base = std::atof(argv[6]), extra = std::atof(argv[7]), manaPct = std::atof(argv[8]),
                 lifePct = std::atof(argv[9]), walk = std::atof(argv[10]), longer = std::atof(argv[11]);

    expect(RuneOf(severance) == Rune::Severance && RuneOf(jaunt) == Rune::Jaunt && RuneOf(shock) == Rune::UmbralShock &&
               RuneOf(guest) == Rune::HonoredGuest && RuneOf(journey) == Rune::HealingJourney,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {severance, jaunt, shock, guest, journey})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Spirit Walk") == Rune::None,
           "the base skill and a stranger are no rune");

    // Run speed: the base for every walk, Severance adds its own on top.
    for (Rune rune : {Rune::None, Rune::Jaunt, Rune::UmbralShock, Rune::HonoredGuest, Rune::HealingJourney})
        expect(RunSpeedPct(rune, base, extra) == base, "a walk without Severance runs at the base speed",
               RunSpeedPct(rune, base, extra), base);
    expect(RunSpeedPct(Rune::Severance, base, extra) == base + extra, "Severance adds to the base",
           RunSpeedPct(Rune::Severance, base, extra), base + extra);
    expect(RunSpeedPct(Rune::Severance, 0, extra) == extra && RunSpeedPct(Rune::None, base, 0) == base,
           "each part stands alone");
    expect(RunSpeedPct(Rune::Severance, -base, -extra) == 0, "a negative number adds nothing");

    // The share of a maximum: Honored Guest's Mana and Healing Journey's Life.
    expect(ShareOf(750, manaPct) == 750 * manaPct / 100, "a share of the Mana maximum", ShareOf(750, manaPct),
           750 * manaPct / 100);
    expect(ShareOf(15016, lifePct) == 15016 * lifePct / 100, "a share of the Life maximum", ShareOf(15016, lifePct),
           15016 * lifePct / 100);
    expect(ShareOf(0, manaPct) == 0 && ShareOf(750, 0) == 0 && ShareOf(-750, manaPct) == 0 &&
               ShareOf(750, -manaPct) == 0,
           "no maximum, no percent or a negative number gives nothing");

    // The cooldown starts after the walk: its seconds in milliseconds.
    expect(CooldownDelayMs(walk) == std::uint64_t(walk * 1000), "the delay is the walk's seconds",
           double(CooldownDelayMs(walk)), walk * 1000);
    expect(CooldownDelayMs(longer) == std::uint64_t(longer * 1000), "Jaunt's longer walk delays longer",
           double(CooldownDelayMs(longer)), longer * 1000);
    expect(CooldownDelayMs(0) == 0 && CooldownDelayMs(-1) == 0, "no walk, no delay");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
