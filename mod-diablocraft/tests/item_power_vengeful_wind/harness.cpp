// Drives Vengeful Wind's rules (diablocraft-8iwwg) with the rows the generator emitted: the item's raise of the vortex's maximum
// (SkillSetTo in dc_item_power_math.h, `max_stacks_add`, base 0) and what Sweeping Wind does with it (dc_monk_sweeping_wind.h: MaxStacks,
// StacksAfter, SpawnsTornado). Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | clear | setto <skill> <stat> <base> -> SkillSetTo
//   attacks <sheetMax> <n> -> the stacks after a cast's 1 and n attacks of a Spirit Generator, then whether the next attack spawns Cyclone's
//                            tornado, with the maximum MaxStacks(sheetMax, the worn raise): "<stacks> <tornado>"
#include "combat/dc_item_power_math.h"
#include "classes/monk/dc_monk_sweeping_wind.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::ItemPower;

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
    std::vector<Row> rows;
    std::map<std::string, unsigned> const none;
    Situation sit;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            Row row{c[1], static_cast<unsigned>(std::stoul(c[2])), c[3], c[4], c[5], std::stod(c[6]), std::stod(c[7]), c[8], std::stod(c[9]),
                    Split(c[10], ';'), std::stod(c[11]), static_cast<unsigned>(std::stoul(c[12]))};
            row.fireOn = c[13];
            row.fireSkills = Split(c[14], ';');
            row.chancePct = std::stod(c[15]);
            row.icdSeconds = std::stod(c[16]);
            rows.push_back(row);
        }
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = 0;
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "setto")
            std::printf("%.10g\n", SkillSetTo(rows, none, c[1], c[2], std::stod(c[3]), sit));
        else if (c[0] == "attacks")
        {
            unsigned const most = DC::Combat::Monk::Wind::MaxStacks(std::stod(c[1]), SkillSetTo(rows, none, "Sweeping Wind", "max_stacks_add", 0, sit));
            unsigned stacks = 1;
            for (unsigned i = 0, n = static_cast<unsigned>(std::stoul(c[2])); i < n; ++i)
                stacks = DC::Combat::Monk::Wind::StacksAfter(stacks, most, true);
            std::printf("%u %d\n", stacks, DC::Combat::Monk::Wind::SpawnsTornado(stacks, most, true) ? 1 : 0);
        }
    }
    return 0;
}
