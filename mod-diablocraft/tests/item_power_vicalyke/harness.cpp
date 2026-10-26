// Drives the Mirror Image rules of src/combat/dc_item_power_math.h (Archmage's Vicalyke, diablocraft-6cw6f) with the rows the generator
// emitted. Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   now <ms> | wears <owner> <since> | clear
//   fire <event> <draw>            -> "stat=value;..." of the effect rows ItemPower::Fire fires (a chance falls when <draw> < percent)
//   killed <known 0|1> <hostile 0|1> -> ImageDeathCounts: 1 when an enemy of the owner killed the Image
//   multiplies <chance> <draw>      -> ImageMultiplies: 1 when the Image multiplies, the chance a tunable's number
//   copy <own 0|1> <remaining ms>   -> ImageCopyMs: the milliseconds of the Image that replaces the dead one (0: none)
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
        else if (c[0] == "wears")
            sit.wornSince[c[1]] = static_cast<std::uint32_t>(std::stoul(c[2]));
        else if (c[0] == "clear")
            sit = Situation{};
        else if (c[0] == "fire")
        {
            double const draw = std::stod(c[2]);
            std::string out;
            char text[96];
            for (Fired const& f : Fire(rows, {}, sit, c[1], "", 1.0, [&](double pct) { return draw < pct; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", f.stat.c_str(), f.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "killed")
            std::printf("%d\n", ImageDeathCounts(c[1] == "1", c[2] == "1") ? 1 : 0);
        else if (c[0] == "multiplies")
        {
            double const draw = std::stod(c[2]);
            std::printf("%d\n", ImageMultiplies(std::stod(c[1]), [&](double pct) { return draw < pct; }) ? 1 : 0);
        }
        else if (c[0] == "copy")
            std::printf("%u\n", ImageCopyMs(c[1] == "1", static_cast<std::uint32_t>(std::stoul(c[2]))));
    }
    return 0;
}
