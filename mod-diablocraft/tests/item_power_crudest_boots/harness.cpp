// Drives The Crudest Boots' rules with the rows the generator emitted: the item's extra Mystic Allies (SkillSetTo in
// dc_item_power_math.h, `summon_count_add`, base 0) and what the Monk does with it (dc_monk_mystic_ally.h: AllyCount, FormSeconds).
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   wears <owner> | clear | setto <skill> <stat> <base> -> SkillSetTo
//   allies -> the allies a Monk keeps with what is worn: AllyCount(SkillSetTo(Mystic Ally, summon_count_add, 0))
//   count <extra> -> AllyCount(extra)
//   form <seconds> <pct> -> an active form's seconds: FormSeconds(seconds, the Boots worn, pct)
#include "combat/dc_item_power_math.h"
#include "classes/monk/dc_monk_mystic_ally.h"

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
        else if (c[0] == "allies")
            std::printf("%u\n", DC::Combat::Monk::MysticAlly::AllyCount(SkillSetTo(rows, none, "Mystic Ally", "summon_count_add", 0, sit)));
        else if (c[0] == "count")
            std::printf("%u\n", DC::Combat::Monk::MysticAlly::AllyCount(std::stod(c[1])));
        else if (c[0] == "form")
        {
            double const pct = std::stod(c[2]);
            bool const worn = SkillSetTo(rows, none, "Mystic Ally", "summon_count_add", 0, sit) > 0;
            std::printf("%.10g\n", DC::Combat::Monk::MysticAlly::FormSeconds(std::stod(c[1]), worn, pct));
        }
    }
    return 0;
}
