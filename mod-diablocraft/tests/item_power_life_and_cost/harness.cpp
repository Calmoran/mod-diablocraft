// Drives the Life and damage-free rules of dc_item_power_math.h (Holds' `no_damage_for` and `own_life_below`, QuietFor, CostCutPct, RegenByMissing, LifeLookDue, Best, PlayerSum of
// crit_chance_pct; Pride's Fall, Rogar's Huge Stone, Shi Mizu's Haori) with the rows the generator emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> <ms> | stored <owner> <stat> <value> | now <ms> | hurt <0|1> <last ms> | life <percent> | clear
//   cost -> CostCutPct     regen -> RegenByMissing at the situation's Life     crit -> PlayerSum of crit_chance_pct
//   holds <row index> -> Holds     best <row index> -> Best     due <last ms> <now ms> <seconds> -> LifeLookDue
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
            sit.wornSince[c[1]] = static_cast<std::uint32_t>(std::stoul(c[2]));
        else if (c[0] == "stored")
            sit.itemValues[c[1]].push_back({"", c[2], std::stod(c[3]), c[1]});
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "hurt")
        {
            sit.hurt = c[1] == "1";
            sit.lastHurt = static_cast<std::uint32_t>(std::stoul(c[2]));
        }
        else if (c[0] == "life")
            sit.lifePct = std::stod(c[1]);
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "cost")
            std::printf("%.10g\n", CostCutPct(rows, none, sit));
        else if (c[0] == "regen")
            std::printf("%.10g\n", RegenByMissing(rows, none, sit.lifePct, sit));
        else if (c[0] == "crit")
            std::printf("%.10g\n", PlayerSum(rows, none, "crit_chance_pct", sit));
        else if (c[0] == "holds")
            std::printf("%d\n", std::stoul(c[1]) < rows.size() && Holds(rows[std::stoul(c[1])], sit) ? 1 : 0);
        else if (c[0] == "best")
            std::printf("%.10g\n", std::stoul(c[1]) < rows.size() ? Best(rows[std::stoul(c[1])]) : -1.0);
        else if (c[0] == "due")
            std::printf("%d\n", LifeLookDue(static_cast<std::uint32_t>(std::stoul(c[1])), static_cast<std::uint32_t>(std::stoul(c[2])), std::stod(c[3])) ? 1 : 0);
    }
    return 0;
}
