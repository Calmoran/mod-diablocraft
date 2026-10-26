#include "dc_monster_d3_type.h"

#include "../monsters/dc_family_ai.h"

#include "Creature.h"
#include "DatabaseEnv.h"
#include "Field.h"
#include "Log.h"
#include "QueryResult.h"

#include <cstdint>
#include <string>
#include <unordered_map>

namespace DC::Combat::MonsterTypes
{
    namespace
    {
        // Read once, on the first hit that asks; a world without the table has no typed monster and says so.
        std::unordered_map<std::uint32_t, std::string> const& Types()
        {
            static auto const types = []
            {
                std::unordered_map<std::uint32_t, std::string> loaded;
                QueryResult rows = WorldDatabase.Query("SELECT entry, d3_type FROM dc_monster_d3_type");
                if (!rows)
                {
                    LOG_ERROR("module.dc.combat",
                              "dc_monster_d3_type is missing or empty; apply monster_types_0001_d3_types.sql");
                    return loaded;
                }
                do
                {
                    Field* f = rows->Fetch();
                    loaded[f[0].Get<std::uint32_t>()] = f[1].Get<std::string>();
                } while (rows->NextRow());
                return loaded;
            }();
            return types;
        }
    } // namespace

    std::string_view D3TypeOf(Creature const* creature)
    {
        if (!creature)
            return {};
        auto const& types = Types();
        auto const found = types.find(Rifts::Family::BaseEntry(creature->GetEntry()));
        return found == types.end() ? std::string_view{} : std::string_view{found->second};
    }
} // namespace DC::Combat::MonsterTypes
