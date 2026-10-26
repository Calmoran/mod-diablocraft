#include "dc_legendary_gem.h"
#include "DatabaseEnv.h"
#include "QueryResult.h"
#include "Field.h"
#include <cmath>
#include <map>
#include <stdexcept>

namespace DC::LegendaryGem
{
    namespace
    {
        std::map<std::string, Row> const& Rows()
        {
            static auto const values = []
            {
                std::map<std::string, Row> result;
                auto rows =
                    WorldDatabase.Query("SELECT gem_id,gem_name,base_value,per_rank,base_value_2,per_rank_2,max_rank,"
                                        "rank25_value_1,rank25_value_2,fixed_1,fixed_2,fixed_3 FROM dc_legendary_gem");
                if (!rows)
                    throw std::runtime_error("Missing generated dc_legendary_gem");
                do
                {
                    auto* f = rows->Fetch();
                    Row row;
                    row.id = f[0].Get<std::string>();
                    row.name = f[1].Get<std::string>();
                    row.base = f[2].Get<double>();
                    row.perRank = f[3].Get<double>();
                    if (!f[4].IsNull())
                        row.base2 = f[4].Get<double>();
                    if (!f[5].IsNull())
                        row.perRank2 = f[5].Get<double>();
                    if (!f[6].IsNull())
                        row.maxRank = f[6].Get<uint32>();
                    if (!f[7].IsNull())
                        row.rank25[0] = f[7].Get<double>();
                    if (!f[8].IsNull())
                        row.rank25[1] = f[8].Get<double>();
                    for (int i = 0; i < 3; ++i)
                        if (!f[9 + i].IsNull())
                            row.fixed[i] = f[9 + i].Get<double>();
                    if (f[2].IsNull() || f[3].IsNull() || !std::isfinite(row.base) || !std::isfinite(row.perRank) ||
                        !result.emplace(row.id, row).second)
                        throw std::runtime_error("Invalid or duplicate dc_legendary_gem row");
                } while (rows->NextRow());
                return result;
            }();
            return values;
        }
    } // namespace

    Row const* Find(std::string const& gemId)
    {
        auto const& rows = Rows();
        auto it = rows.find(gemId);
        return it == rows.end() ? nullptr : &it->second;
    }
} // namespace DC::LegendaryGem
