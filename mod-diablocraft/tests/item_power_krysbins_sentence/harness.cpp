// Drives the target-control bonus of dc_item_power_math.h (N-TCTRL ImpairedFactor, with the readers PlayerSum, PlayerFactor,
// ReductionFactor and SkillFactor) with the rows the generator emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | value <owner> <skill> <stat> <v> | life <percent of maximum Life> | clear
//   reduction -> ReductionFactor      factor <stat> -> PlayerFactor      sum <stat> -> PlayerSum      skill <skill> <stat> -> SkillFactor
//   missing -> LifeMissing            impaired <slowed 0|1> <other control 0|1> -> ImpairedFactor      roll <owner> <top 0|1> -> RollPowers with a draw of the range's middle, "key=value;"
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
        else if (c[0] == "life")
            sit.lifePct = std::stod(c[1]);
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "reduction")
            std::printf("%.10g\n", ReductionFactor(rows, none, sit));
        else if (c[0] == "factor")
            std::printf("%.10g\n", PlayerFactor(rows, none, c[1], sit));
        else if (c[0] == "sum")
            std::printf("%.10g\n", PlayerSum(rows, none, c[1], sit));
        else if (c[0] == "skill")
            std::printf("%.10g\n", SkillFactor(rows, none, c[1], c[2], sit));
        else if (c[0] == "impaired")
        {
            sit.targetControl = (c[1] == "1" ? TargetSlowed : 0u) | (c[2] == "1" ? TargetControlled : 0u);
            std::printf("%.10g\n", ImpairedFactor(rows, none, sit));
        }
        else if (c[0] == "missing")
            std::printf("%.10g\n", LifeMissing(sit));
        else if (c[0] == "roll")
        {
            std::string out;
            char text[160];
            for (Rolled const& r : RollPowers(rows, c[1], c[2] == "1", [](double low, double high) { return (low + high) / 2; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", r.key.c_str(), r.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
    }
    return 0;
}
