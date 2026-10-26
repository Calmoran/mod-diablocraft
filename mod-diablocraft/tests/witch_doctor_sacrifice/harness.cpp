// The real dc_witch_doctor_sacrifice.h. The rune names and numbers come from argv (read from the sheets and the
// tunables by test_witch_doctor_sacrifice.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the
// first failing case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_sacrifice.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>
#include <string>

using namespace DC::Combat::WitchDoctor::Sacrifice;

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
    // argv: the five runes A to E, then the Mana Pride pays a dog, the chance Next of Kin brings a dog back, the
    // seconds Provoke the Pack lasts.
    if (argc < 9)
        return 2;
    std::string const provoke = argv[1], master = argv[2], blood = argv[3], pride = argv[4], kin = argv[5];
    double const perDog = std::atof(argv[6]), chance = std::atof(argv[7]), seconds = std::atof(argv[8]);

    expect(RuneOf(provoke) == Rune::ProvokeThePack && RuneOf(master) == Rune::ForTheMaster &&
               RuneOf(blood) == Rune::BlackBlood && RuneOf(pride) == Rune::Pride && RuneOf(kin) == Rune::NextOfKin,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {provoke, master, blood, pride, kin})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five", double(seen.size()), 5);
    expect(RuneOf("") == Rune::None && RuneOf("Crack") == Rune::None, "the base skill and a stranger are no rune");

    // One dog is banished, every dog for For the Master; none standing, none banished.
    expect(Sacrificed(Rune::None, 3) == 1 && Sacrificed(Rune::Pride, 3) == 1 &&
               Sacrificed(Rune::ProvokeThePack, 1) == 1,
           "one dog is banished");
    expect(Sacrificed(Rune::ForTheMaster, 3) == 3 && Sacrificed(Rune::ForTheMaster, 1) == 1,
           "For the Master banishes every dog", Sacrificed(Rune::ForTheMaster, 3), 3);
    expect(Sacrificed(Rune::None, 0) == 0 && Sacrificed(Rune::ForTheMaster, 0) == 0, "no dog, none banished");

    // Pride pays for each dog banished.
    expect(std::fabs(PrideMana(perDog, 3) - 3 * perDog) < 1e-9 && PrideMana(perDog, 0) == 0 && PrideMana(0, 3) == 0 &&
               PrideMana(-5, 3) == 0,
           "Pride pays for each dog", PrideMana(perDog, 3), 3 * perDog);

    // Next of Kin: a roll under the chance brings the dog back.
    expect(Resurrects(0.0, chance) && Resurrects(chance - 0.01, chance) && !Resurrects(chance, chance) &&
               !Resurrects(99.0, chance),
           "a dog comes back under the chance", chance, 0);
    expect(!Resurrects(0.0, 0.0) && !Resurrects(0.0, -1.0), "no chance, no dog back");

    // Provoke the Pack: on from the cast for its seconds.
    std::uint64_t const until = BonusUntil(10000, seconds);
    expect(until == 10000 + std::uint64_t(seconds * 1000.0 + 0.5), "the bonus ends its seconds after the cast",
           double(until), 10000 + seconds * 1000.0);
    expect(BonusOn(10000, until) && BonusOn(until - 1, until) && !BonusOn(until, until) && !BonusOn(until + 1, until),
           "it is on until its moment");
    expect(!BonusOn(10000, BonusUntil(10000, 0)) && !BonusOn(10000, BonusUntil(10000, -3)), "no seconds, no bonus");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
