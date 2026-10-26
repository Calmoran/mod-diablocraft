// Drives Legacy of Dreams' production rules (diablocraft-do2wo): Resolve and the Legacy functions of
// src/combat/dc_gem_power_math.h, and AnySetBonus of src/combat/dc_item_power_math.h, with the generated gem rows.
// Input, tab separated, one command a line:
//   gem <gem_id> <base> <per_rank> <max|none> <base2|none> <per2|none> <fixed1|none> <fixed2|none> <fixed3|none>
//       <rank25_1|none> <rank25_2|none>
//   case <gem_id> <rank|none> <legendaries> <ancients> <n> (<set> <worn>)xn
// A case prints: setBonusOn items damageFactor incomingFactor
#include "combat/dc_gem_power_math.h"
#include "combat/dc_item_power_math.h"

#include <cstdio>
#include <fstream>
#include <map>
#include <optional>
#include <sstream>
#include <string>
#include <vector>

static std::vector<std::string> Split(std::string const& line)
{
    std::vector<std::string> cells;
    std::stringstream stream(line);
    std::string cell;
    while (std::getline(stream, cell, '\t'))
        cells.push_back(cell);
    return cells;
}

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
    std::map<std::string, DC::LegendaryGem::Row> gems;
    std::string line;
    while (std::getline(in, line))
    {
        auto c = Split(line);
        if (c.empty())
            continue;
        if (c[0] == "gem")
        {
            DC::LegendaryGem::Row row;
            row.id = row.name = c[1];
            row.base = std::stod(c[2]);
            row.perRank = std::stod(c[3]);
            if (auto v = Cell(c[4]))
                row.maxRank = static_cast<uint32_t>(*v);
            row.base2 = Cell(c[5]);
            row.perRank2 = Cell(c[6]);
            for (int i = 0; i < 3; ++i)
                row.fixed[i] = Cell(c[7 + i]);
            row.rank25[0] = Cell(c[10]);
            row.rank25[1] = Cell(c[11]);
            gems[row.id] = row;
        }
        else if (c[0] == "case")
        {
            std::vector<DC::LegendaryGemItem::Socketed> worn;
            if (c[2] != "none")
                worn.push_back({c[1], static_cast<uint32_t>(std::stoul(c[2]))});
            unsigned const legendaries = std::stoul(c[3]), ancients = std::stoul(c[4]), n = std::stoul(c[5]);
            std::map<std::string, unsigned> counts;
            for (unsigned i = 0; i < n; ++i)
                counts[c[6 + 2 * i]] = std::stoul(c[7 + 2 * i]);
            auto const powers = DC::Combat::GemPower::Resolve(DC::LegendaryGemItem::Counted(worn),
                                                              [&](std::string const& id) -> DC::LegendaryGem::Row const*
                                                              {
                                                                  auto it = gems.find(id);
                                                                  return it == gems.end() ? nullptr : &it->second;
                                                              });
            bool const setOn = DC::Combat::ItemPower::AnySetBonus(counts);
            unsigned const items = DC::Combat::GemPower::LegacyItems(powers, legendaries, ancients, setOn);
            std::printf("%d %u %.9g %.9g\n", setOn ? 1 : 0, items, DC::Combat::GemPower::LegacyFactor(powers, items),
                        DC::Combat::GemPower::LegacyIncomingFactor(powers, items));
        }
    }
    return 0;
}
