// Drives the Immortal King's Call 2- and 4-piece rules of dc_item_power_math.h (SpentFires: N-SPENT, and SkillSetTo for `lasts_until_death`, N-DUR kind) with the rows
// the generator emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   set <owner> <pieces worn> | wears <item d3_id> | clear (worn, sets and the carried points)
//   spent <points> -> SpentFires, one line "stat=value:skill;..." (blank: nothing fired)     until <skill> -> SkillSetTo(..., "lasts_until_death", 0)
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
    std::map<std::string, double> carry;
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
        else if (c[0] == "set")
            counts[c[1]] = static_cast<unsigned>(std::stoul(c[2]));
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = 0;
        else if (c[0] == "clear")
        {
            counts.clear();
            carry.clear();
            sit = Situation{};
        }
        else if (c[0] == "spent")
        {
            std::string out;
            char text[160];
            for (Fired const& f : SpentFires(rows, counts, sit, std::stod(c[1]), carry))
            {
                std::snprintf(text, sizeof text, "%s=%g:%s;", f.stat.c_str(), f.value, f.skill.c_str());
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "until")
            std::printf("%.10g\n", SkillSetTo(rows, counts, c.size() > 1 ? c[1] : std::string(), "lasts_until_death", 0.0, sit));
    }
    return 0;
}
