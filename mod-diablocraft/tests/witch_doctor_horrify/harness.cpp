// The real dc_witch_doctor_horrify.h. The rune names come from argv (read from the sheet by
// test_witch_doctor_horrify.py); nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing
// case and exits 1.
#include "classes/witch_doctor/dc_witch_doctor_buffs.h"
#include "classes/witch_doctor/dc_witch_doctor_horrify.h"

#include <cstdio>
#include <set>
#include <string>

using namespace DC::Combat::WitchDoctor::Horrify;
using namespace DC::Combat::WitchDoctor::Buffs;

static int failures = 0, cases = 0;

static void expect(bool ok, char const* what)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s\n", what);
        ++failures;
    }
}

int main(int argc, char** argv)
{
    // argv: the five runes A to E
    if (argc < 6)
        return 2;
    std::string const aspect = argv[1], face = argv[2], phobia = argv[3], terror = argv[4], stalker = argv[5];

    expect(RuneOf(aspect) == Rune::FrighteningAspect && RuneOf(face) == Rune::FaceOfDeath &&
               RuneOf(phobia) == Rune::Phobia && RuneOf(terror) == Rune::RuthlessTerror &&
               RuneOf(stalker) == Rune::Stalker,
           "each rune name is its rune");
    std::set<int> seen;
    for (auto const& rune : {aspect, face, phobia, terror, stalker})
        seen.insert(int(RuneOf(rune)));
    expect(seen.size() == 5 && !seen.count(int(Rune::None)), "the five runes are five");
    expect(RuneOf("") == Rune::None && RuneOf("Horrify") == Rune::None, "the base skill and a stranger are no rune");

    // The skill and every rune but Phobia hold the frightened enemy still.
    expect(Immobilizes(Rune::None), "the skill immobilizes");
    for (Rune rune : {Rune::FrighteningAspect, Rune::FaceOfDeath, Rune::RuthlessTerror, Rune::Stalker})
        expect(Immobilizes(rune), "a rune other than Phobia immobilizes");
    expect(!Immobilizes(Rune::Phobia), "Phobia does not immobilize");

    // The timed numbers a rune puts on the sheet: the cap holds, a second cast restarts the time, a buff that ran out starts
    // again from one stack and is worth nothing from its end moment on.
    Held held;
    expect(Add(held, 1000, 8000, 1, 1) == 1 && held.until == 9000, "the first cast gives one stack until its end");
    expect(Add(held, 4000, 8000, 1, 1) == 1 && held.until == 12000, "a second cast restarts the time and does not pass the cap");
    expect(Add(held, 5000, 8000, 3, 1) == 2 && Add(held, 6000, 8000, 3, 1) == 3 && Add(held, 7000, 8000, 3, 1) == 3,
           "stacks rise to the cap and stay");
    expect(Add(held, 20000, 8000, 3, 1) == 1, "a buff that ran out starts again from one stack");
    expect(Add(held, 20000, 8000, 0, 1) == 1, "a cap of none still allows the one stack");
    Held once;
    Add(once, 1000, 4000, 1, 1);
    expect(!Over(once, 4999) && Over(once, 5000) && Over(once, 5001), "the buff is over from its end moment on");
    expect(Worth(once, 4999, 20) == 20 && Worth(once, 5000, 20) == 0, "worth is the number for every stack, nothing once over");
    Held twice;
    Add(twice, 1000, 4000, 2, 1);
    Add(twice, 2000, 4000, 2, 1);
    expect(Worth(twice, 3000, 20) == 40, "two stacks are worth twice");

    std::printf("cases=%d\n", cases);
    return failures ? 1 : 0;
}
