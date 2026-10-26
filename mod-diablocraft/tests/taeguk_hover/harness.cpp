// Drives what the server tells the addon about Taeguk's buff (src/combat/dc_gem_powers.cpp ShowTaeguk) with the
// number row the generator emitted: the aura the buff is shown as and the addon record for the stacks.
//   "row <gem_id> <base> <per_rank> <max|none> <base2|none> <per2|none> <fixed1|none> <fixed2|none> <fixed3|none>
//        <rank25_1|none> <rank25_2|none>"
//   "hover <gem_id> <rank> <stacks>"  prints: the aura id, the Armor per stack the record states, the "V|aura|total" record
#include "combat/dc_buff_values_math.h"
#include "combat/dc_gem_power_math.h"
#include "combat/dc_spell_shells.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <optional>
#include <string>

static std::optional<double> Cell(std::string const& text)
{
    if (text == "none")
        return std::nullopt;
    return std::stod(text);
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::map<std::string, DC::LegendaryGem::Row> rows;
    std::string command;
    while (in >> command)
    {
        if (command == "row")
        {
            DC::LegendaryGem::Row row;
            std::string cells[8];
            in >> row.id >> row.base >> row.perRank;
            for (auto& cell : cells)
                in >> cell;
            row.name = row.id;
            if (auto v = Cell(cells[0]))
                row.maxRank = static_cast<uint32_t>(*v);
            row.base2 = Cell(cells[1]);
            row.perRank2 = Cell(cells[2]);
            for (int i = 0; i < 3; ++i)
                row.fixed[i] = Cell(cells[3 + i]);
            row.rank25[0] = Cell(cells[6]);
            row.rank25[1] = Cell(cells[7]);
            rows[row.id] = row;
        }
        else if (command == "hover")
        {
            std::string gem;
            unsigned rank, stacks;
            in >> gem >> rank >> stacks;
            std::vector<DC::LegendaryGemItem::Socketed> worn(1);
            worn[0].gemId = gem;
            worn[0].rank = rank;
            auto const powers = DC::Combat::GemPower::Resolve(
                DC::LegendaryGemItem::Counted(worn), [&](std::string const& id) -> DC::LegendaryGem::Row const* {
                    auto it = rows.find(id);
                    return it == rows.end() ? nullptr : &it->second;
                });
            // ShowTaeguk's call: the rank-25 record when the gem states an Armor, the damage total as the one value.
            std::uint32_t const aura = DC::Combat::Shells::GemBuffFor(
                DC::Combat::GemPower::Taeguk, powers.taegukArmorPctPerStack > 0);
            auto const fields = DC::Combat::BuffValues::Fields(
                aura, false, {DC::Combat::GemPower::AdditivePct(powers, stacks)});
            std::string record;
            for (auto const& field : fields)
                record += (record.empty() ? "" : "|") + field;
            std::printf("%u %.9g %s\n", aura, powers.taegukArmorPctPerStack, record.c_str());
        }
    }
    return 0;
}
