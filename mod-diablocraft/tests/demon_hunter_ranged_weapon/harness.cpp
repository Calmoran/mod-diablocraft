// The real dc_demon_hunter_ranged_weapon.h. The cases come from the file named in argv[1], one a line: whether the skill
// requires a ranged weapon, the item subclass in the main hand and in the off hand (4294967295 for nothing), and whether the
// cast is allowed. test_demon_hunter_ranged_weapon.py writes them from the sheets and the item generator's weapon
// subclasses; nothing is typed in here. Prints "cases=N" and exits 0, or names the first failing case and exits 1.
#include "classes/demon_hunter/dc_demon_hunter_ranged_weapon.h"

#include <cstdio>
#include <cstdlib>
#include <fstream>

using namespace DC::Combat::DemonHunter::RangedWeapon;

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream cases(argv[1]);
    unsigned requires_, main_, off, expected;
    int count = 0, failures = 0;
    while (cases >> requires_ >> main_ >> off >> expected)
    {
        ++count;
        if (Allowed(requires_ != 0, main_, off) != (expected != 0))
        {
            std::printf("FAIL requires %u main %u off %u expected %u\n", requires_, main_, off, expected);
            ++failures;
        }
    }
    if (!count)
        return 2;
    std::printf("cases=%d\n", count);
    return failures ? 1 : 0;
}
