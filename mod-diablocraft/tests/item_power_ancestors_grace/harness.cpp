// Drives the fatal-hit rule and the `fatal` event of src/combat/dc_item_power_math.h (IsFatal, and Fire on `fatal`; Ancestors' Grace, N-FATAL)
// with the rows the generator emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   now <ms> | clear                      -> the clock; an empty situation (no output)
//   wears <owner> | bag <owner>           -> the item put on, or only known (in the bag) (no output)
//   fire <event>                          -> "stat=value@skill;..." of the effect rows that fired
//   fatal <damage> <health>               -> 1 when the hit takes all the Life left, else 0
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
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "wears")
        {
            sit.wornSince[c[1]] = 0;
            sit.itemValues[c[1]] = WornValues(rows, c[1], {});
        }
        else if (c[0] == "bag")
            sit.itemValues[c[1]] = WornValues(rows, c[1], {});
        else if (c[0] == "fire")
        {
            std::string out;
            char text[96];
            for (Fired const& f : Fire(rows, std::map<std::string, unsigned>{}, sit, c[1], "", 1.0, [](double) { return true; }))
            {
                std::snprintf(text, sizeof text, "%s=%g@%s;", f.stat.c_str(), f.value, f.skill.c_str());
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "fatal")
            std::printf("%d\n", IsFatal(static_cast<std::uint32_t>(std::stoul(c[1])), static_cast<std::uint32_t>(std::stoul(c[2]))) ? 1 : 0);
    }
    return 0;
}
