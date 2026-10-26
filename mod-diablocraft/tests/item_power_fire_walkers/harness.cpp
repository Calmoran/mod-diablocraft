// Drives the Fire Walkers rules (diablocraft-4na3e, N-AREA) of src/combat/dc_item_power_math.h (the `tick` clock that fires the row, its period the
// row's icd_seconds) and src/combat/dc_item_trail_math.h (the patches of fire and what they burn) with the row the generator emitted. Input, tab
// separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   now <ms> | clear                               -> the clock; an empty situation (no output)
//   wears <owner> [<roll>]                         -> the item put on, its ranged rows at the stored roll when given (no roll: none stored) (no output)
//   bag <owner>                                    -> the item only known, not worn (no output)
//   fire <event>                                   -> "stat=value;..." of the effect rows ItemPower::Fire fires
//   drop <patchMs> <moving 0|1> <map> <x> <y> <z>  -> ItemTrail::Drop at the clock's `now`: "dropped|patches left"
//   forget                                         -> the patches gone (no output)
//   burns <map> <x> <y> <z> <radius>               -> 1 when ItemTrail::Burns, else 0, at `now`
//   reach <map> <x> <y> <z> <radius>               -> ItemTrail::Reach at `now`
//   pulse <last> <now> <period>                    -> ItemTrail::PulseSeconds
//   pct <perSecond> <seconds>                      -> ItemTrail::PulsePct
#include "combat/dc_item_power_math.h"
#include "combat/dc_item_trail_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat;

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
    std::vector<ItemPower::Row> rows;
    ItemPower::Situation sit;
    std::vector<ItemTrail::Patch> patches;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line, '\t');
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            ItemPower::Row row{c[1],
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
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "wears")
        {
            std::vector<ItemPower::Stored> stored;
            if (c.size() > 2)
                for (ItemPower::Row const& row : rows)
                    if (row.owner == c[1] && ItemPower::Rolls(row))
                        stored.push_back({ItemPower::RollKey(row), std::stod(c[2])});
            sit.wornSince[c[1]] = 0;
            sit.itemValues[c[1]] = ItemPower::WornValues(rows, c[1], stored);
        }
        else if (c[0] == "bag")
            sit.itemValues[c[1]] = ItemPower::WornValues(rows, c[1], {});
        else if (c[0] == "clear")
            sit = ItemPower::Situation{};
        else if (c[0] == "fire")
        {
            std::string out;
            char text[96];
            for (ItemPower::Fired const& f : ItemPower::Fire(rows, std::map<std::string, unsigned>{}, sit, c[1], "", 1.0, [](double) { return true; }))
            {
                std::snprintf(text, sizeof text, "%s=%g;", f.stat.c_str(), f.value);
                out += text;
            }
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "drop")
        {
            bool const dropped = ItemTrail::Drop(patches, sit.now, static_cast<std::uint32_t>(std::stoul(c[1])), c[2] == "1",
                                                 static_cast<std::uint32_t>(std::stoul(c[3])), std::stof(c[4]), std::stof(c[5]), std::stof(c[6]));
            std::printf("%d|%zu\n", dropped ? 1 : 0, patches.size());
        }
        else if (c[0] == "forget")
            patches.clear();
        else if (c[0] == "burns")
            std::printf("%d\n", ItemTrail::Burns(patches, sit.now, static_cast<std::uint32_t>(std::stoul(c[1])), std::stof(c[2]), std::stof(c[3]),
                                                 std::stof(c[4]), std::stod(c[5])) ? 1 : 0);
        else if (c[0] == "reach")
            std::printf("%.10g\n", ItemTrail::Reach(patches, sit.now, static_cast<std::uint32_t>(std::stoul(c[1])), std::stof(c[2]), std::stof(c[3]),
                                                    std::stof(c[4]), std::stod(c[5])));
        else if (c[0] == "pulse")
            std::printf("%.10g\n", ItemTrail::PulseSeconds(static_cast<std::uint32_t>(std::stoul(c[1])), static_cast<std::uint32_t>(std::stoul(c[2])),
                                                           std::stod(c[3])));
        else if (c[0] == "pct")
            std::printf("%.10g\n", ItemTrail::PulsePct(std::stod(c[1]), std::stod(c[2])));
    }
    return 0;
}
