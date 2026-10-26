// The real dc_witch_doctor_hex_math.h. The rune names and numbers come from argv (read from the sheets by test_witch_doctor_hex.py);
// nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_hex_math.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::WitchDoctor::Hex;

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
    // argv: the five runes A to E, then the Shaman's seconds, the cycle seconds, the group radius, the Hedge Magic heal at the
    // sheet's level, the Healing table at a lower level and at the sheet's, the Toad's poison percent, seconds and tick
    if (argc < 16)
        return 2;
    std::string const toad = argv[1], chicken = argv[2], unstable = argv[3], hedge = argv[4], jinx = argv[5];
    double const life = std::atof(argv[6]), cycle = std::atof(argv[7]), radius = std::atof(argv[8]), heal = std::atof(argv[9]),
                 tableLow = std::atof(argv[10]), tableSheet = std::atof(argv[11]), poison = std::atof(argv[12]),
                 poisonSeconds = std::atof(argv[13]), tick = std::atof(argv[14]), chickenSeconds = std::atof(argv[15]);

    expect(RuneOf(toad) == Rune::ToadOfHugeness && RuneOf(chicken) == Rune::AngryChicken && RuneOf(unstable) == Rune::UnstableForm &&
               RuneOf(hedge) == Rune::HedgeMagic && RuneOf(jinx) == Rune::Jinx,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {toad, chicken, unstable, hedge, jinx})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Hex") == Rune::None, "the base skill and a stranger are no rune");

    // The Shaman and what it does.
    expect(RaisesShaman(Rune::None) && RaisesShaman(Rune::ToadOfHugeness) && RaisesShaman(Rune::UnstableForm) &&
               RaisesShaman(Rune::HedgeMagic) && RaisesShaman(Rune::Jinx),
           "every rune but the chicken has the Shaman");
    expect(!RaisesShaman(Rune::AngryChicken), "the Angry Chicken has no Shaman");
    expect(Hexes(Rune::None) && Hexes(Rune::UnstableForm) && Hexes(Rune::HedgeMagic) && Hexes(Rune::Jinx),
           "the skill and the other runes hex the group");
    expect(!Hexes(Rune::ToadOfHugeness) && !Hexes(Rune::AngryChicken), "the toad's cycle and the chicken hex nobody");

    // The chain of cycles: the first at once, the next every cycle while the Shaman's time holds. Following NextCycle from 0 is
    // the whole cast: one chain, so the runs are the cycles that begin before the Shaman is gone and no more.
    auto runs = [](double lifeSeconds, double cycleSeconds, std::uint64_t* last = nullptr)
    {
        std::uint64_t const lifeMs = std::uint64_t(std::llround(lifeSeconds * 1000)), cycleMs = std::uint64_t(std::llround(cycleSeconds * 1000));
        unsigned n = 1;
        std::uint64_t at = 0;
        while (n < 1000)
        {
            auto const next = NextCycle(at, cycleMs, lifeMs);
            if (!next)
                break;
            expect(*next == at + cycleMs, "each cycle follows the last by one cycle", double(*next), double(at + cycleMs));
            at = *next;
            ++n;
        }
        if (last)
            *last = at;
        return n;
    };
    std::uint64_t lastAt = 0;
    expect(runs(life, cycle, &lastAt) == unsigned(std::ceil(life / cycle - 1e-9)), "a cast runs the cycles the Shaman's time holds", runs(life, cycle),
           std::ceil(life / cycle));
    expect(lastAt < std::uint64_t(std::llround(life * 1000)), "the last cycle begins before the Shaman is gone", double(lastAt), life * 1000);
    expect(runs(cycle, cycle) == 1 && runs(cycle + 0.01, cycle) == 2, "a cycle that begins as the Shaman goes does not run", runs(cycle, cycle), 1);
    expect(!NextCycle(0, 0, 12000) && !NextCycle(0, 4000, 0) && !NextCycle(8000, 4000, 12000), "no cycle length, no time or the end gives no next cycle");

    // A chain ends with its Shaman.
    expect(ChainStands(77, 77), "a chain stands while its own Shaman does");
    expect(!ChainStands(77, 78) && !ChainStands(77, 0) && !ChainStands(0, 0), "a chain of an earlier Shaman, of none, or with none standing ends");

    // The group.
    expect(InGroup(radius, radius) && !InGroup(radius + 0.01, radius) && !InGroup(0, 0), "the group ends at its radius");

    // Hedge Magic.
    expect(std::fabs(HedgeHeal(heal, tableSheet, tableSheet) - heal) < 1e-9, "the sheet's level heals the sheet's number");
    expect(std::fabs(HedgeHeal(heal, tableLow, tableSheet) - heal * tableLow / tableSheet) < 1e-9, "a lower level heals its share of it");
    expect(HedgeHeal(0, tableLow, tableSheet) == 0 && HedgeHeal(heal, 0, tableSheet) == 0 && HedgeHeal(heal, tableLow, 0) == 0,
           "no number, no level or no table heals nothing");

    // The Toad's poison.
    unsigned const ticks = PoisonTicks(poisonSeconds, tick);
    expect(ticks == unsigned(std::floor(poisonSeconds / tick + 1e-9)) && ticks > 0, "the ticks in the poison's seconds", ticks);
    expect(std::fabs(PoisonTickPct(poison, ticks) * ticks - poison) < 1e-9, "the ticks add up to the poison's percent");
    expect(PoisonTicks(0, tick) == 0 && PoisonTicks(poisonSeconds, 0) == 0 && PoisonTickPct(poison, 0) == 0 && PoisonTickPct(-1, 4) == 0,
           "no time, no tick or no percent gives nothing");

    // The Angry Chicken explodes once, on the next press or when its time is over.
    std::uint64_t const ms = std::uint64_t(chickenSeconds * 1000);
    Chicken c;
    c.Start(1000, ms);
    expect(!c.Expired(1000 + ms - 1), "not before its time is over");
    expect(c.Press(1000 + 10) && !c.Press(1000 + 20) && !c.Expired(1000 + ms + 5), "a press explodes it once and the time then explodes nothing");
    Chicken d;
    d.Start(1000, ms);
    expect(d.Expired(1000 + ms) && !d.Expired(1000 + ms + 1) && !d.Press(1000 + ms + 2), "the time's end explodes it once and a press then explodes nothing");
    Chicken e;
    e.Start(1000, ms);
    expect(!e.Press(1000 + ms), "a press at the end moment is too late");
    Chicken f;
    expect(!f.Press(5) && !f.Expired(5), "a chicken that never started explodes nothing");
    Chicken g;
    g.Start(1000, 0);
    expect(!g.Press(1000) && !g.Expired(1000), "a chicken of no time explodes nothing");

    // Unstable Form's list of the hexed.
    Hexed h;
    h.Mark(7, 1000, 4000);
    expect(h.Died(7, 4999) && !h.Died(7, 4999), "an enemy that dies hexed explodes once");
    h.Mark(8, 1000, 4000);
    expect(!h.Died(8, 5000), "an enemy that dies as its hex ends does not");
    expect(!h.Died(9, 2000), "an enemy never hexed does not");
    h.Mark(10, 1000, 4000);
    h.Mark(10, 2000, 4000);
    expect(h.Died(10, 5500), "a second hex renews the first");
    h.Mark(11, 1000, 1000);
    h.Mark(12, 9000, 1000);
    expect(h.until.count(11) == 0 && h.until.count(12) == 1, "an enemy whose hex ran out is forgotten at the next mark");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
