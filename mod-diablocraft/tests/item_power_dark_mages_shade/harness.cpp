// Drives the Life-falls event of src/combat/dc_item_power_math.h (Fire on `life_below`, LifeFell, the item's `life_threshold_pct`, the internal
// cooldown that is the `cast_skill` row's rolled number; Dark Mage's Shade, diablocraft-ohipa) with the rows the generator emitted. Input, tab
// separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   now <ms> | clear | stored <key> <v>   -> the clock; an empty situation; one stored roll of an item (no output)
//   wears <owner>                         -> the item put on, its numbers as WornValues gives them (fixed rows at the table's, ranged at the stored roll)
//   bag <owner>                           -> the same numbers for an item in the bag: known, but not worn
//   life <before percent> <after percent> -> the player's Life before and after the damage now (no output)
//   fire <event>                          -> "stat=value@skill;..." of the effect rows that fired
//   roll <owner> <top 0|1>                -> RollPowers with a draw of the range's middle, "key=value;"
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
    std::vector<Stored> stored;
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
        else if (c[0] == "stored")
            stored.push_back({c[1], std::stod(c[2])});
        else if (c[0] == "wears")
        {
            sit.wornSince[c[1]] = 0;
            sit.itemValues[c[1]] = WornValues(rows, c[1], stored);
        }
        else if (c[0] == "bag")
            sit.itemValues[c[1]] = WornValues(rows, c[1], stored);
        else if (c[0] == "clear")
        {
            sit = Situation{};
            stored.clear();
        }
        else if (c[0] == "life")
        {
            sit.lifeBeforePct = std::stod(c[1]);
            sit.lifeAfterPct = std::stod(c[2]);
        }
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
