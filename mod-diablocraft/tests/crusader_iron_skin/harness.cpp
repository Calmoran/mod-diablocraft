// The real dc_crusader_iron_skin.h. The rune names and numbers come from argv (read from the sheets by
// test_crusader_iron_skin.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case
// and exits 1.
#include "classes/crusader/dc_crusader_iron_skin.h"

#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::Crusader::IronSkin;

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
    // argv: the skin's seconds, Steel Skin's seconds, Charged Up's chance, then the five runes A to E
    if (argc < 9)
        return 2;
    double const skin = std::atof(argv[1]), steel = std::atof(argv[2]), chance = std::atof(argv[3]);
    std::string const charged = argv[4], steelRune = argv[5], explosive = argv[6], reflective = argv[7],
                      flash = argv[8];

    expect(RuneOf(charged) == Rune::ChargedUp && RuneOf(steelRune) == Rune::SteelSkin &&
               RuneOf(explosive) == Rune::ExplosiveSkin && RuneOf(reflective) == Rune::ReflectiveSkin &&
               RuneOf(flash) == Rune::Flash,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {charged, steelRune, explosive, reflective, flash})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Rust") == Rune::None, "the base skill and a stranger are no rune");

    // The skin's time: Steel Skin's longer number, the skill's for every other rune.
    expect(Seconds(Rune::SteelSkin, skin, steel) == steel, "Steel Skin lasts its own seconds",
           Seconds(Rune::SteelSkin, skin, steel), steel);
    expect(steel > skin, "Steel Skin's skin is the longer", steel, skin);
    for (Rune rune : {Rune::None, Rune::ChargedUp, Rune::ExplosiveSkin, Rune::ReflectiveSkin, Rune::Flash})
        expect(Seconds(rune, skin, steel) == skin, "every other rune lasts the skill's seconds",
               Seconds(rune, skin, steel), skin);

    // Explosive Skin: only a skin nothing holds has expired.
    expect(Expired(0) && !Expired(1), "a held skin has not expired");

    // Charged Up's roll: a roll under the chance procs, at or over does not.
    expect(Procs(chance - 0.01, chance) && !Procs(chance, chance) && !Procs(99.9, chance),
           "a roll under the chance stuns", chance, 0);
    expect(!Procs(0, 0), "no chance never stuns");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
