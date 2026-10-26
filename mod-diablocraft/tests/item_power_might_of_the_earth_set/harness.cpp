// Drives the Might of the Earth 4-piece rules of src/combat/dc_item_power_math.h (diablocraft-tydva: Fire on `land`, GrantsRune, SkillFactor) with
// the rows the generator emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   count <set> <pieces> | now <ms>  -> the worn pieces of a set; the clock (no output)
//   fire <event> <skill>             -> "stat=value@skill;..." of the effect rows that fired
//   grants <skill> <rune>            -> 1 or 0
//   factor <skill> <stat>            -> the multiplier
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
        else if (c[0] == "count")
            counts[c[1]] = static_cast<unsigned>(std::stoul(c[2]));
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "fire")
        {
            std::string out;
            char text[96];
            for (Fired const& f : Fire(rows, counts, sit, c[1], c[2], 1.0, [](double) { return true; }))
            {
                std::snprintf(text, sizeof text, "%s=%g@%s;", f.stat.c_str(), f.value, f.skill.c_str());
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "grants")
            std::printf("%d\n", GrantsRune(rows, counts, c[1], c[2], sit) ? 1 : 0);
        else if (c[0] == "factor")
            std::printf("%g\n", SkillFactor(rows, counts, c[1], c[2], sit));
    }
    return 0;
}
