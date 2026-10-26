// Drives the production group B math of src/combat/dc_gem_power_math.h (Resolve, the stacking clock, the factors)
// with the number rows the generator emitted.
//   "row <gem_id> <base> <per_rank> <max|none> <base2|none> <per2|none> <fixed1|none> <fixed2|none> <fixed3|none>
//        <rank25_1|none> <rank25_2|none>"
//   "case <n> <gem_id> <rank> ... <powerful 0|1> <trapped 0|1> <stricken> <yards> <taeguk> <gogok> <invigorating>"
//     prints: standalone additive dodge ias healing zei powerfulSeconds taegukSeconds taegukMax gogokSeconds gogokMax
//             invigSeconds invigMax
//   "stack <seconds> <max> <n> <t1> ... <tn> <m> <q1> ... <qm>": n adds at the times (ms), then the live count at
//     each query time (ms); prints the m counts
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
    namespace GP = DC::Combat::GemPower;
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
            int powerful, trapped;
            unsigned stricken, taeguk, gogok, invigorating;
            double yards;
            in >> powerful >> trapped >> stricken >> yards >> taeguk >> gogok >> invigorating;
            auto const active = DC::LegendaryGemItem::Counted(worn);
            auto const p = GP::Resolve(active, [&](std::string const& id) -> DC::LegendaryGem::Row const* {
                auto it = rows.find(id);
                return it == rows.end() ? nullptr : &it->second;
            });
            std::printf("%.9g %.9g %.9g %.9g %.9g %.9g %.9g %.9g %u %.9g %u %.9g %u\n",
                        GP::StandaloneFactor(p, powerful, trapped, stricken, yards), GP::AdditivePct(p, taeguk),
                        GP::DodgePct(p, gogok), GP::AttackSpeedPct(p, gogok), GP::HealingFactor(p, invigorating),
                        GP::ZeiPct(p, yards), p.powerfulSeconds, p.taeguk.seconds, p.taeguk.max, p.gogok.seconds,
                        p.gogok.max, p.invigorating.seconds, p.invigorating.max);
        }
        else if (command == "stack")
        {
            double seconds;
            unsigned max, n, m;
            in >> seconds >> max >> n;
            GP::Stacks stacks;
            for (unsigned i = 0; i < n; ++i)
            {
                uint32_t t;
                in >> t;
                GP::AddStack(stacks, t, seconds, max);
            }
            in >> m;
            for (unsigned i = 0; i < m; ++i)
            {
                uint32_t t;
                in >> t;
                std::printf("%u%c", GP::Live(stacks, t), i + 1 == m ? '\n' : ' ');
            }
        }
    }
    return 0;
}
