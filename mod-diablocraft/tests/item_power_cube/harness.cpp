// Drives the Cube source of the legendary powers framework (diablocraft-45rx5.1): the REAL pure helpers of
// src/combat/dc_item_power_math.h fed the generated power rows and the real base item list. No doubles beyond the Situation the
// caller builds; the server half (dc_item_powers.cpp) cannot be compiled here, scripts/tests/legendaries/test_item_power_cube.py pins its lines.
// Input, tab separated, one command a line:
//   row <owner> <pieces> <kind> <skill> <stat> <min> <max> <cond> <arg> <condSkills;..> <stackSeconds> <stackMax> <fireOn> <fireSkills;..> <chance> <icd>
//   base <d3_id> <d3_name> <rarity> <pool 0|1>         -> one base item of the list the twin map is built from
//   powerid <d3_id>                                    -> PowerId
//   built <power id>                                   -> 0 or 1
//   values <worn|cube> <power id> <m> (<key> <value>)xm -> "skill:stat=value;..." of PowerValues given the stored rows
//   rowsof <d3_id> | statsof <d3_id>                   -> "owner:kind:skill:stat;..." the twin-aware rows an item owns
//   active <nworn> (<id> <m> (<key> <value>)xm)xnworn <ncube> <id>xncube -> "id/W|C/nvalues;..." ActivePowers
//   worn <id> <since> <m> (<key> <value>)xm            -> a worn item in the situation (its WornValues)
//   cubed <id> <since>                                 -> a power chosen in the Cube
//   merge                                              -> AddCubed(situation, rows, cubed)
//   now <ms> | resource <pct> | counts <set> <n>       -> the situation's clock, primary resource, a set count
//   since                                              -> "id=since;..." the situation's wornSince
//   sum <kind> <skill> <stat>                          -> sum of ItemPower::ActiveValues
//   clear                                              -> an empty situation, no cubed
//   cubeid <slot> <seq>                                -> CubeContributionId
//   fit <usable_by or -> <designated_class or -> <class key or -> -> 0 or 1 (RollClass::Eligible, the rule `choose` and ClassMayChoose both call)
//   slotok <slot> <slot numbers>...                    -> 0 or 1 (CubeSlotExists)
#include "combat/dc_item_power_math.h"
#include "items/dc_roll_class.h"

#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

using namespace DC::Combat::ItemPower;

static std::vector<std::string> Split(std::string const& line)
{
    std::vector<std::string> cells;
    std::stringstream stream(line);
    std::string cell;
    while (std::getline(stream, cell, '\t'))
        cells.push_back(cell);
    return cells;
}

static std::vector<std::string> List(std::string const& text)
{
    std::vector<std::string> out;
    std::stringstream stream(text);
    std::string one;
    while (std::getline(stream, one, ';'))
        out.push_back(one);
    return out;
}

static std::string Show(std::vector<Value> const& values)
{
    std::string out;
    char text[160];
    for (Value const& v : values)
    {
        std::snprintf(text, sizeof text, "%s:%s=%g;", v.skill.c_str(), v.stat.c_str(), v.value);
        out += text;
    }
    return out;
}

static std::string Show(std::vector<Row> const& rows)
{
    std::string out;
    for (Row const& r : rows)
        out += r.owner + ":" + r.kind + ":" + r.skill + ":" + r.stat + ";";
    return out;
}

// m stored rows from c[at]: (key, value) pairs; returns the index after them
static std::size_t Stores(std::vector<std::string> const& c, std::size_t at, std::vector<Stored>& out)
{
    std::size_t const count = std::stoul(c[at]);
    for (std::size_t i = 0; i < count; ++i)
        out.push_back({c[at + 1 + 2 * i], std::stod(c[at + 2 + 2 * i])});
    return at + 1 + 2 * count;
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::vector<Row> rows;
    std::vector<BaseItem> bases;
    std::vector<Cubed> cubed;
    std::map<std::string, std::string> ids; // the twin map, rebuilt when the base list grew
    std::size_t idsFor = 0;
    auto Ids = [&]() -> std::map<std::string, std::string> const&
    {
        if (idsFor != bases.size())
        {
            ids = PowerIds(bases);
            idsFor = bases.size();
        }
        return ids;
    };
    Situation sit;
    std::map<std::string, unsigned> counts;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line);
        if (c.empty())
            continue;
        if (c[0] == "row")
        {
            Row row{c[1], static_cast<unsigned>(std::stoul(c[2])), c[3], c[4], c[5], std::stod(c[6]), std::stod(c[7]), c[8], std::stod(c[9]), List(c[10]),
                    std::stod(c[11]), static_cast<unsigned>(std::stoul(c[12]))};
            row.fireOn = c[13];
            row.fireSkills = List(c[14]);
            row.chancePct = std::stod(c[15]);
            row.icdSeconds = std::stod(c[16]);
            rows.push_back(row);
        }
        else if (c[0] == "base")
            bases.push_back({c[1], c[2], c[3], c[4] == "1"});
        else if (c[0] == "powerid")
            std::printf("%s\n", PowerId(Ids(), c[1]).c_str());
        else if (c[0] == "built")
            std::printf("%d\n", Built(rows, c[1]) ? 1 : 0);
        else if (c[0] == "values")
        {
            std::vector<Stored> stored;
            Stores(c, 3, stored);
            std::printf("%s\n", Show(PowerValues(rows, c[2], c[1] == "cube" ? Source::Cube : Source::Worn, stored)).c_str());
        }
        else if (c[0] == "rowsof")
            std::printf("%s\n", Show(RowsOf(rows, Ids(), c[1])).c_str());
        else if (c[0] == "statsof")
            std::printf("%s\n", Show(StatsOf(rows, Ids(), c[1])).c_str());
        else if (c[0] == "active")
        {
            std::vector<Active> wornList;
            std::size_t at = 2;
            for (std::size_t i = 0; i < std::stoul(c[1]); ++i)
            {
                std::vector<Stored> stored;
                std::string const id = c[at];
                at = Stores(c, at + 1, stored);
                wornList.push_back({id, Source::Worn, PowerValues(rows, id, Source::Worn, stored)});
            }
            std::vector<std::string> ids;
            for (std::size_t i = 0; i < std::stoul(c[at]); ++i)
                ids.push_back(c[at + 1 + i]);
            std::string out;
            for (Active const& a : ActivePowers(rows, wornList, ids))
                out += a.id + "/" + (a.source == Source::Worn ? "W" : "C") + "/" + std::to_string(a.values.size()) + ";";
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "worn")
        {
            std::vector<Stored> stored;
            Stores(c, 3, stored);
            sit.wornSince[c[1]] = static_cast<std::uint32_t>(std::stoul(c[2]));
            sit.itemValues[c[1]] = PowerValues(rows, c[1], Source::Worn, stored);
        }
        else if (c[0] == "cubed")
            cubed.push_back({c[1], static_cast<std::uint32_t>(std::stoul(c[2]))});
        else if (c[0] == "merge")
            AddCubed(sit, rows, cubed);
        else if (c[0] == "now")
            sit.now = static_cast<std::uint32_t>(std::stoul(c[1]));
        else if (c[0] == "resource")
            sit.resourcePct = std::stod(c[1]);
        else if (c[0] == "counts")
            counts[c[1]] = static_cast<unsigned>(std::stoul(c[2]));
        else if (c[0] == "since")
        {
            std::string out;
            for (auto const& [id, at] : sit.wornSince)
                out += id + "=" + std::to_string(at) + ";";
            std::printf("%s\n", out.c_str());
        }
        else if (c[0] == "sum")
        {
            double sum = 0;
            for (double v : ActiveValues(rows, counts, c[1], c[2], c[3], sit))
                sum += v;
            std::printf("%g\n", sum);
        }
        else if (c[0] == "clear")
        {
            sit = Situation{};
            cubed.clear();
            counts.clear();
        }
        else if (c[0] == "cubeid")
            std::printf("%llu\n", static_cast<unsigned long long>(CubeContributionId(static_cast<unsigned>(std::stoul(c[1])), static_cast<unsigned>(std::stoul(c[2])))));
        else if (c[0] == "fit") // fit <usable_by or -> <designated_class or -> <class key or ->
        {
            auto const cell = [&](std::size_t at) { return c[at] == "-" ? std::string() : c[at]; };
            std::printf("%d\n", DC::RollClass::Eligible(cell(1), cell(2), cell(3)) ? 1 : 0);
        }
        else if (c[0] == "slotok") // slotok <slot> <the Cube's slot numbers>...
        {
            std::vector<unsigned> slots;
            for (std::size_t at = 2; at < c.size(); ++at)
                slots.push_back(static_cast<unsigned>(std::stoul(c[at])));
            std::printf("%d\n", CubeSlotExists(slots, static_cast<unsigned>(std::stoul(c[1]))) ? 1 : 0);
        }
    }
    return 0;
}
