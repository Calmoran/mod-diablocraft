// Drives the production Enforcer math of src/combat/dc_gem_power_math.h (diablocraft-ml7y) with the number rows and the
// pet list the generators emitted.
//   "row <gem_id> <base> <per_rank> <max|none> <base2|none> <per2|none> <fixed1|none> <fixed2|none> <fixed3|none>
//        <rank25_1|none> <rank25_2|none>"   one dc_legendary_gem row
//   "pet <entry> <skill name>"               one dc_legendary_gem_pet row (entry 0: no creature enemies can target)
//   "case <n> <gem_id> <rank> ..."           prints: petDamagePct, petDefencePct, PetDamageFactor(pet),
//                                            PetDamageFactor(not a pet), PetIncomingFactor(targetable pet),
//                                            PetIncomingFactor(not one)
//   "skill <name>" / "entry <n>"             (the name is the rest of the line) prints IsPetSkill / IsPetEntry of the list read so far
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

namespace GP = DC::Combat::GemPower;

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::map<std::string, DC::LegendaryGem::Row> rows;
    GP::Pets pets;
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
        else if (command == "pet")
        {
            std::string skill;
            std::uint32_t entry;
            in >> entry;
            std::getline(in >> std::ws, skill);
            GP::AddPet(pets, skill, entry ? std::optional<std::uint32_t>(entry) : std::nullopt);
        }
        else if (command == "case")
        {
            unsigned n;
            in >> n;
            std::vector<DC::LegendaryGemItem::Socketed> worn(n);
            for (auto& gem : worn)
                in >> gem.gemId >> gem.rank;
            auto const active = DC::LegendaryGemItem::Counted(worn);
            GP::Powers const p = GP::Resolve(active, [&](std::string const& id) -> DC::LegendaryGem::Row const* {
                auto it = rows.find(id);
                return it == rows.end() ? nullptr : &it->second;
            });
            std::printf("%.9g %.9g %.9g %.9g %.9g %.9g\n", p.petDamagePct, p.petDefencePct,
                        GP::PetDamageFactor(p, true), GP::PetDamageFactor(p, false), GP::PetIncomingFactor(p, true),
                        GP::PetIncomingFactor(p, false));
        }
        else if (command == "skill")
        {
            std::string skill;
            std::getline(in >> std::ws, skill);
            std::printf("%d\n", GP::IsPetSkill(pets, skill) ? 1 : 0);
        }
        else if (command == "entry")
        {
            std::uint32_t entry;
            in >> entry;
            std::printf("%d\n", GP::IsPetEntry(pets, entry) ? 1 : 0);
        }
    }
    return 0;
}
