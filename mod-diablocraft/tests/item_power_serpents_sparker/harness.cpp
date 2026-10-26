// Drives Serpent's Sparker (N-HYDRA, diablocraft-1zocv): the `extra_active_count` row through dc_item_power_math.h's ActiveCount (what the Hydra's
// summon asks), Dismissed over a run of casts, and the `damage_increase_pct` row through SkillFactor (the hit's legendary term). Input, tab
// separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | value <owner> <skill> <stat> <roll> | clear
//   count <skill> <base>          -> ActiveCount
//   factor <skill> <stat>         -> SkillFactor
//   casts <n> <cap>               -> the summons up after each of n casts, each cast dismissing Dismissed(up, cap) of the oldest first
#include "combat/dc_item_power_math.h"

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
        else if (c[0] == "count")
            std::printf("%.10g\n", ActiveCount(rows, none, c[1], std::stod(c[2]), sit));
        else if (c[0] == "factor")
            std::printf("%.10g\n", SkillFactor(rows, none, c[1], c[2], sit));
        else if (c[0] == "casts")
        {
            unsigned const n = static_cast<unsigned>(std::stoul(c[1])), cap = static_cast<unsigned>(std::stoul(c[2]));
            std::size_t up = 0;
            std::string out;
            for (unsigned i = 0; i < n; ++i)
            {
                std::size_t const gone = Dismissed(up, cap);
                up = (gone > up ? 0 : up - gone) + 1;
                out += std::to_string(up) + ",";
            }
            std::printf("%s\n", out.c_str());
        }
    }
    return 0;
}
