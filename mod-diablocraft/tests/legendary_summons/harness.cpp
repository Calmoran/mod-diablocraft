// Compiles dc_ally.h (the production header) and drives it with the entries and scripts the test read out of
// data/legendary_summons.csv: argv is "entry <n>" and "script <name>" pairs, then "not-entry <n>" and "not-script <name>".
#include "dc_ally.h"

#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <string_view>

using namespace DC::Rifts::Ally;

int main(int argc, char** argv)
{
    int checked = 0;
    for (int i = 1; i + 1 < argc; i += 2)
    {
        std::string_view kind = argv[i];
        std::string_view value = argv[i + 1];
        if (kind == "entry")
            assert(IsAllyEntry(std::uint32_t(std::atol(argv[i + 1]))));
        else if (kind == "not-entry")
            assert(!IsAllyEntry(std::uint32_t(std::atol(argv[i + 1]))));
        else if (kind == "script")
            assert(IsAllyScript(value));
        else if (kind == "not-script")
            assert(!IsAllyScript(value));
        else
            assert(!"unknown argument");
        ++checked;
    }
    assert(checked > 0);
    std::printf("legendary summons harness: ok (%d)\n", checked);
    return 0;
}
