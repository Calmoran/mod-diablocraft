// diablocraft-geyf (GitHub #58): runs the module's own CountsFor and
// DualWieldIas (cut out of dc_items_roll.cpp / dc_stats.cpp by
// scripts/tests/monsters/test_affix_budget_tunables.py) over a Tunables::Get that answers from
// the table the generator emitted. Prints one line per probe.
#include <cstdio>
#include <map>
#include <string>

namespace DC::Tunables
{
double Get(std::string const& category, std::string const& name);
}

#include "dc_items_extract.h"
#include "dc_stats_extract.h"

#include "generated_table.h" // kTable[] = {category, name, value}

namespace DC::Tunables
{
double Get(std::string const& category, std::string const& name)
{
    for (auto const& row : kTable)
        if (category == row.category && name == row.name)
            return row.value;
    return 0.0; // the real Get's answer for a missing row
}
}

int main()
{
    for (char const* rarity : {"magic", "rare", "legendary", "set", "ethereal", "normal", ""})
    {
        auto const counts = DC::Items::CountsFor(rarity);
        std::printf("counts %s %u %u\n", *rarity ? rarity : "empty", counts.primary, counts.secondary);
    }
    std::printf("dual %g\n", DC::Stats::DualWieldIas());
    return 0;
}
