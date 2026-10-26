// Drives the N-PREVENT rules of dc_item_power_math.h (Countess Julia's Cameo, diablocraft-sjdct) with the rows the
// generator emitted: PreventFor, which the reader calls under its lock, and the roll of the heal's range. Input, tab
// separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax>
//   <fireOn> <fireSkills;..> <chance> <icd> wears <owner> | value <owner> <skill> <stat> <v> | clear prevent <element>
//   <damage>        -> PreventFor: "<damage still taken> <Life healed>" share <damage> <preventedPct> <healPct> ->
//   PreventDamage on its own: "<taken> <healed>" roll <owner> <top 0|1>            -> RollPowers with a draw of the
//   range's middle, "key=value;"
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
            Row row{c[1],
                    static_cast<unsigned>(std::stoul(c[2])),
                    c[3],
                    c[4],
                    c[5],
                    std::stod(c[6]),
                    std::stod(c[7]),
                    c[8],
                    std::stod(c[9]),
                    Split(c[10], ';'),
                    std::stod(c[11]),
                    static_cast<unsigned>(std::stoul(c[12]))};
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
        else if (c[0] == "prevent")
        {
            Prevented const result = PreventFor(rows, none, c[1], static_cast<std::uint32_t>(std::stoul(c[2])), sit);
            std::printf("%u %u\n", result.taken, result.healed);
        }
        else if (c[0] == "share")
        {
            Prevented const result =
                PreventDamage(static_cast<std::uint32_t>(std::stoul(c[1])), std::stod(c[2]), std::stod(c[3]));
            std::printf("%u %u\n", result.taken, result.healed);
        }
        else if (c[0] == "roll")
        {
            std::string out;
            char text[160];
            for (Rolled const &r :
                 RollPowers(rows, c[1], c[2] == "1", [](double low, double high) { return (low + high) / 2; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", r.key.c_str(), r.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
    }
    return 0;
}
