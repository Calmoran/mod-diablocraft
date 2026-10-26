// Drives Kekegi's Unbreakable Spirit's rules of src/combat/dc_item_power_math.h (diablocraft-hk2xg, N-COST): Fire with the generated row, and the
// window's CostFreeEnd and CostFreeAt. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   now <ms>                         -> the clock (no output)
//   wears <owner> <since>            -> an item (d3_id) put on (no output)
//   value <owner> <skill> <stat> <v> -> a worn item's stored number for a ranged row (no output)
//   clear                            -> an empty situation, nothing fired
//   fire <event> <skill> <scale> <draw> -> "stat=value;" of the effect rows that fired; a chance falls when <draw> < percent
//   end <until> <now> <seconds>      -> CostFreeEnd
//   at <until> <now>                 -> CostFreeAt, 0 or 1
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
    Situation sit;
    std::map<std::string, unsigned> const counts;
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
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = static_cast<std::uint32_t>(std::stoul(c[2]));
        else if (c[0] == "value")
            sit.itemValues[c[1]].push_back({c[2], c[3], std::stod(c[4]), c[1]});
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "fire")
        {
            double const draw = std::stod(c[4]);
            std::string out;
            char text[96];
            for (Fired const& f : Fire(rows, counts, sit, c[1], c.size() > 2 ? c[2] : "", std::stod(c[3]), [&](double pct) { return draw < pct; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", f.stat.c_str(), f.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "end")
            std::printf("%u\n", CostFreeEnd(static_cast<std::uint32_t>(std::stoul(c[1])), static_cast<std::uint32_t>(std::stoul(c[2])), std::stod(c[3])));
        else if (c[0] == "at")
            std::printf("%d\n", CostFreeAt(static_cast<std::uint32_t>(std::stoul(c[1])), static_cast<std::uint32_t>(std::stoul(c[2]))) ? 1 : 0);
    }
    return 0;
}
