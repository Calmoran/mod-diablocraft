// Drives the Bovine Bardiche rules (diablocraft-4p9j9) of src/combat/dc_item_power_math.h (which hit fires the row) and
// src/combat/dc_item_summon_math.h (whether the herd comes, what a swing deals) with the rows the generator emitted.
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax>
//   <fireOn> <fireSkills;..> <chance> <icd> now <ms> | wears <owner> <since> | clear fire <event> <skill> <scale>
//   <draw>          -> "stat=value;..." of the effect rows ItemPower::Fire fires comes <last ms|-> <now ms> <cooldown
//   s> <coefficient> <chance> <draw> -> HerdComes: 1 when the herd comes swing <pct> <delta> <draw> <attacks/s>
//   <interval ms>                -> SwingPct: the percent of weapon damage of one swing
// A chance falls when <draw> < the percent asked.
#include "combat/dc_item_power_math.h"
#include "combat/dc_item_summon_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat;

static std::vector<std::string> Split(std::string const& text, char by)
{
    std::vector<std::string> cells;
    std::stringstream stream(text);
    std::string cell;
    while (std::getline(stream, cell, by))
        cells.push_back(cell);
    return cells;
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::vector<ItemPower::Row> rows;
    ItemPower::Situation sit;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            ItemPower::Row row{c[1],
                               static_cast<unsigned>(std::stoul(c[2])),
                               c[3],
                               c[4],
                               c[5],
                               std::stod(c[6]),
                               std::stod(c[7]),
                               c[8],
                               std::stod(c[9]),
                               Split(c[10], ';'),
                               std::stod(c[11]),
                               static_cast<unsigned>(std::stoul(c[12]))};
            row.fireOn = c[13];
            row.fireSkills = Split(c[14], ';');
            row.chancePct = std::stod(c[15]);
            row.icdSeconds = std::stod(c[16]);
            rows.push_back(row);
        }
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = static_cast<std::uint32_t>(std::stoul(c[2]));
        else if (c[0] == "clear")
            sit = ItemPower::Situation{};
        else if (c[0] == "fire")
        {
            double const draw = std::stod(c[4]);
            std::string out;
            char text[96];
            for (ItemPower::Fired const& f :
                 ItemPower::Fire(rows, {}, sit, c[1], c[2], std::stod(c[3]), [&](double pct) { return draw < pct; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", f.stat.c_str(), f.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "comes")
        {
            std::optional<std::uint32_t> last;
            if (c[1] != "-")
                last = static_cast<std::uint32_t>(std::stoul(c[1]));
            double const draw = std::stod(c[6]);
            std::printf("%d\n",
                        ItemSummon::HerdComes(last, static_cast<std::uint32_t>(std::stoul(c[2])), std::stod(c[3]),
                                              std::stod(c[4]), std::stod(c[5]), [&](double pct) { return draw < pct; })
                            ? 1
                            : 0);
        }
        else if (c[0] == "swing")
            std::printf("%g\n", ItemSummon::SwingPct(std::stod(c[1]), std::stod(c[2]), std::stod(c[3]), std::stod(c[4]),
                                                     static_cast<std::uint32_t>(std::stoul(c[5]))));
    }
    return 0;
}
