// Drives Kyoshiro's Soul (N-SWSTACK, diablocraft-tvv2b): the `idle_stacks_per_second` row through dc_item_power_math.h's SkillSetTo (what the vortex's
// tick asks), and the real Wind::IdleGain of dc_monk_sweeping_wind.h over a run of ticks. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | value <owner> <skill> <stat> <roll> | clear
//   setto <skill> <stat> <base>                              -> SkillSetTo
//   ticks <tickMs> <perSecond> <max> <stacks> <q/d pattern>  -> the stacks after each tick (q: damaged no enemy, d: damaged one), as the tick applies them
#include "combat/dc_item_power_math.h"
#include "classes/monk/dc_monk_sweeping_wind.h"

#include <algorithm>
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
        else if (c[0] == "value")
            sit.itemValues[c[1]].push_back({c[2], c[3], std::stod(c[4]), c[1]});
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "setto")
            std::printf("%.10g\n", SkillSetTo(rows, none, c[1], c[2], std::stod(c[3]), sit));
        else if (c[0] == "ticks")
        {
            std::uint64_t const tickMs = std::stoull(c[1]);
            unsigned const perSecond = static_cast<unsigned>(std::stoul(c[2])), most = static_cast<unsigned>(std::stoul(c[3]));
            unsigned stacks = static_cast<unsigned>(std::stoul(c[4]));
            std::uint64_t quietMs = 0;
            std::string out;
            for (char t : c.size() > 5 ? c[5] : std::string())
            {
                stacks = std::min(stacks + DC::Combat::Monk::Wind::IdleGain(quietMs, t == 'd', tickMs, perSecond), most);
                out += std::to_string(stacks) + ",";
            }
            std::printf("%s\n", out.c_str());
        }
    }
    return 0;
}
