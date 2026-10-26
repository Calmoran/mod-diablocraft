// Drives N-SETSTAT (diablocraft-wn9q7) of dc_item_power_math.h, SetStats and SetStatContributionId, with the rows the generator emitted.
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> ...   (the generated row's 16 cells; only the first seven are read here)
//   set <owner> <pieces worn> | clear
//   stats -> one line "index:owner:stat=value;" per row that is on (blank: none)      id <index> -> SetStatContributionId
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
    std::map<std::string, unsigned> counts;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            Row row;
            row.owner = c[1];
            row.pieces = static_cast<unsigned>(std::stoul(c[2]));
            row.kind = c[3];
            row.skill = c[4];
            row.stat = c[5];
            row.min = std::stod(c[6]);
            row.max = std::stod(c[7]);
            rows.push_back(row);
        }
        else if (c[0] == "set")
            counts[c[1]] = static_cast<unsigned>(std::stoul(c[2]));
        else if (c[0] == "clear")
            counts.clear();
        else if (c[0] == "stats")
        {
            std::string out;
            char text[200];
            for (auto const& [index, row] : SetStats(rows, counts))
            {
                std::snprintf(text, sizeof text, "%u:%s:%s=%g;", index, row.owner.c_str(), row.stat.c_str(), row.min);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "id")
            std::printf("%u\n", SetStatContributionId(static_cast<unsigned>(std::stoul(c[1]))));
    }
    return 0;
}
