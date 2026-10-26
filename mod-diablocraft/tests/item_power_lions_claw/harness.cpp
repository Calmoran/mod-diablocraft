// Drives Lion's Claw's rules (diablocraft-xureo) with the rows the generator emitted: the item's extra strikes (SkillSetTo in
// dc_item_power_math.h, `extra_strikes`, base 0) and what Seven-Sided Strike does with them (dc_monk_seven_sided_strike.h: Strikes, StrikePct).
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | clear | setto <skill> <stat> <base> -> SkillSetTo
//   strikes <sheetCount> <totalPct> -> the strikes of a cast with the worn extra, then one strike's percentage: "<strikes> <pct>"
#include "combat/dc_item_power_math.h"
#include "classes/monk/dc_monk_seven_sided_strike.h"

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
        else if (c[0] == "strikes")
        {
            double const sheet = std::stod(c[1]);
            unsigned const strikes = DC::Combat::Monk::SevenSided::Strikes(
                sheet, SkillSetTo(rows, none, "Seven-Sided Strike", "extra_strikes", 0, sit));
            std::printf("%u %.10g\n", strikes, DC::Combat::Monk::SevenSided::StrikePct(std::stod(c[2]), sheet));
        }
    }
    return 0;
}
