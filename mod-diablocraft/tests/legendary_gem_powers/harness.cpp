// Drives the production sums of src/combat/dc_gem_power_math.h (Counted -> Resolve -> the two factors),
// with the number rows the generator emitted.
//   "row <gem_id> <base> <per_rank> <max|none> <base2|none> <per2|none> <fixed1|none> <fixed2|none> <fixed3|none>
//        <rank25_1|none> <rank25_2|none>"
//   "case <n> <gem_id> <rank> ... <physical 0|1> <melee 0|1> <primary 0|1>"
// A case prints: lifeRegen thorns nonPhysicalPct meleePct primaryPct incomingFactor primaryFactor
#include "combat/dc_gem_power_math.h"

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
        else if (command == "case")
        {
            unsigned n;
            in >> n;
            std::vector<DC::LegendaryGemItem::Socketed> worn(n);
            for (auto& gem : worn)
                in >> gem.gemId >> gem.rank;
            int physical, melee, primary;
            in >> physical >> melee >> primary;
            auto const active = DC::LegendaryGemItem::Counted(worn);
            auto const powers = DC::Combat::GemPower::Resolve(
                active, [&](std::string const& id) -> DC::LegendaryGem::Row const* {
                    auto it = rows.find(id);
                    return it == rows.end() ? nullptr : &it->second;
                });
            std::printf("%.9g %.9g %.9g %.9g %.9g %.9g %.9g\n", powers.lifeRegen, powers.thorns,
                        powers.nonPhysicalReductionPct, powers.meleeReductionPct, powers.primaryDamagePct,
                        DC::Combat::GemPower::IncomingFactor(powers, physical, melee),
                        DC::Combat::GemPower::PrimaryFactor(powers, primary));
        }
    }
    return 0;
}
