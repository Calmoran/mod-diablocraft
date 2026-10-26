#include "dc_numeric_data.h"
#include "dc_common.h"
#include "DatabaseEnv.h"
#include "QueryResult.h"
#include "Field.h"
#include <cmath>
#include <map>
#include <stdexcept>
#include <string>

namespace DC::NumericData
{
namespace
{
std::map<unsigned, double> const& Bases()
{
    static auto const values = []
    {
        std::map<unsigned, double> result;
        auto rows = WorldDatabase.Query("SELECT level,fury_max FROM dc_barbarian_base_stats ORDER BY level");
        if (!rows) throw std::runtime_error("Missing sourced base stats");
        unsigned expected = 1;
        do
        {
            auto* f = rows->Fetch();
            unsigned level = f[0].Get<uint32>();
            double fury = f[1].Get<double>();
            if (level != expected++ || !std::isfinite(fury) || fury <= 0)
                throw std::runtime_error("Invalid sourced base-stat range or Fury");
            result.emplace(level, fury);
        } while (rows->NextRow());
        return result;
    }();
    return values;
}
}

double Rule(char const* name)
{
    static auto const values = []
    {
        std::map<std::string, double> result;
        auto rows = WorldDatabase.Query("SELECT name,value FROM dc_numeric_rule");
        if (!rows) throw std::runtime_error("Missing generated numeric rules");
        do
        {
            auto* f = rows->Fetch();
            double value = f[1].Get<double>();
            if (f[1].IsNull() || !std::isfinite(value) || value < 0 ||
                !result.emplace(f[0].Get<std::string>(), value).second)
                throw std::runtime_error("Invalid or duplicate numeric source rule");
        } while (rows->NextRow());
        return result;
    }();
    return values.at(name);
}

unsigned MaximumLevel() { return Bases().rbegin()->first; }
double BaseFury(unsigned level) { return Bases().at(level); }

BlockTuning Block()
{
    static auto const values = []
    {
        std::map<std::string, double> result;
        auto rows = WorldDatabase.Query("SELECT parameter,COALESCE(tuned_value,d3_value) FROM dc_block_tuning");
        if (!rows) throw std::runtime_error("Missing dc_block_tuning");
        do
        {
            auto* f = rows->Fetch();
            if (f[1].IsNull()) continue;
            result.emplace(f[0].Get<std::string>(), f[1].Get<double>());
        } while (rows->NextRow());
        BlockTuning tuning{result.at("block_chance_base_cap"), result.at("block_chance_total_cap"),
                           result.at("block_amount_percent_scale")};
        if (!std::isfinite(tuning.baseChanceCap) || !std::isfinite(tuning.totalChanceCap) ||
            !std::isfinite(tuning.amountPercentScale) || tuning.baseChanceCap < 0 ||
            tuning.totalChanceCap < 0 || tuning.amountPercentScale < 0)
            throw std::runtime_error("Invalid dc_block_tuning");
        return tuning;
    }();
    return values;
}
}
