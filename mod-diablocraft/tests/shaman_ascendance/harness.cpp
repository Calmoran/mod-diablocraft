// The real dc_shaman_ascendance.h. The rune names and numbers come from argv (read from the sheets by
// test_shaman_ascendance.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/shaman/dc_shaman_ascendance.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <string>

using namespace DC::Combat::Shaman::Ascendance;

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
    // argv: the five runes A to E, the skill's damage bonus, a rune's damage bonus, the bolt's share, Eternal
    // Ascendance's Maelstrom per step, its step and cap in seconds, Storm Ascendance's target count, and a Primary's
    // hit percent.
    if (argc < 14)
        return 2;
    std::string const flame = argv[1], storm = argv[2], water = argv[3], earth = argv[4], eternal = argv[5];
    double const base = std::atof(argv[6]), own = std::atof(argv[7]), share = std::atof(argv[8]),
                 per = std::atof(argv[9]), step = std::atof(argv[10]), cap = std::atof(argv[11]),
                 jumps = std::atof(argv[12]), hit = std::atof(argv[13]);

    expect(RuneOf(flame) == Rune::FlameAscendance && RuneOf(storm) == Rune::StormAscendance &&
               RuneOf(water) == Rune::WaterAscendance && RuneOf(earth) == Rune::EarthAscendance &&
               RuneOf(eternal) == Rune::EternalAscendance,
           "each rune name is its rune");
    expect(RuneOf("") == Rune::None && RuneOf("Ascendance") == Rune::None && RuneOf("Epiphany") == Rune::None,
           "and nothing else is");

    // The element a rune empowers.
    expect(ElementOfRune(Rune::FlameAscendance) == "fire" && ElementOfRune(Rune::StormAscendance) == "lightning" &&
               ElementOfRune(Rune::WaterAscendance) == "cold" && ElementOfRune(Rune::EarthAscendance) == "physical" &&
               ElementOfRune(Rune::EternalAscendance).empty() && ElementOfRune(Rune::None).empty(),
           "each rune picks its element");

    // The damage bonus: the rune's number for its element, the skill's for the rest.
    expect(Bonus(Rune::FlameAscendance, "fire", base, own) == own &&
               Bonus(Rune::FlameAscendance, "cold", base, own) == base &&
               Bonus(Rune::EarthAscendance, "physical", base, own) == own &&
               Bonus(Rune::EarthAscendance, "lightning", base, own) == base,
           "the empowered element takes the rune's bonus and every other element the skill's");
    expect(Bonus(Rune::None, "fire", base, 0) == base && Bonus(Rune::EternalAscendance, "fire", base, 0) == base &&
               Bonus(Rune::EternalAscendance, "", base, 0) == base && Bonus(Rune::None, "fire", 0, 0) == 0 &&
               Bonus(Rune::None, "fire", -5, 0) == 0,
           "the base and Eternal Ascendance give the skill's bonus to every hit");
    expect(own > base, "a rune empowers its element above the skill's");

    // The bolt of a Primary cast.
    expect(std::fabs(BoltPct(hit, share) - hit * share / 100.0) < 1e-9 && BoltPct(hit, share) < hit &&
               BoltPct(0, share) == 0 && BoltPct(hit, 0) == 0,
           "a bolt is its share of the Primary's damage");
    expect(Fires("Primary", true) && !Fires("Primary", false) && !Fires("Secondary", true) && !Fires("Primal", true),
           "only a Primary cast fires bolts, while the buff stands");

    // Eternal Ascendance: a step for each `per` Maelstrom spent, the remainder carried, never past the cap.
    auto const stepMs = std::uint64_t(step * 1000.0), capMs = std::uint64_t(cap * 1000.0);
    Extension one = Extend(Rune::EternalAscendance, 0, per, 0, per, step, cap);
    expect(one.addMs == stepMs && one.remainder == 0, "a step of Maelstrom extends the buff by a step",
           double(one.addMs), double(stepMs));
    Extension part = Extend(Rune::EternalAscendance, 0, per - 1, 0, per, step, cap);
    expect(part.addMs == 0 && part.remainder == per - 1, "less than a step carries");
    Extension joined = Extend(Rune::EternalAscendance, per - 1, 1, 0, per, step, cap);
    expect(joined.addMs == stepMs && joined.remainder == 0, "and the carried joins the next spending");
    Extension many = Extend(Rune::EternalAscendance, 0, per * 3 + 7, 0, per, step, cap);
    expect(many.addMs == 3 * stepMs && many.remainder == 7, "many steps at once keep the remainder");
    Extension capped = Extend(Rune::EternalAscendance, 0, per * 1000, 0, per, step, cap);
    expect(capped.addMs == capMs, "the extension stops at the cap", double(capped.addMs), double(capMs));
    Extension full = Extend(Rune::EternalAscendance, 0, per, capMs, per, step, cap);
    expect(full.addMs == 0, "and adds nothing past it");
    expect(Extend(Rune::None, 0, per, 0, per, step, cap).addMs == 0 &&
               Extend(Rune::StormAscendance, 0, per, 0, per, step, cap).addMs == 0 &&
               Extend(Rune::EternalAscendance, 0, 0, 0, per, step, cap).addMs == 0,
           "no other rune extends it, and nothing spent extends nothing");

    // Storm Ascendance's jumps.
    expect(ExtraJumps(Rune::StormAscendance, jumps) == unsigned(jumps) && ExtraJumps(Rune::None, jumps) == 0 &&
               ExtraJumps(Rune::FlameAscendance, jumps) == 0 && ExtraJumps(Rune::StormAscendance, 0) == 0,
           "only Storm Ascendance gives Chain Lightning extra jumps");

    std::uint64_t const start = 8000, ends = start + 15000;
    expect(Holds(ends - 1, ends) && !Holds(ends, ends) && !Holds(start, 0), "the buff holds until it ends");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
