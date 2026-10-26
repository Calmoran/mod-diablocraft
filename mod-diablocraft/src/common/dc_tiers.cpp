#include "dc_tiers.h"
#include "dc_tunables.h"
#include "DatabaseEnv.h"
#include "QueryResult.h"
#include "Field.h"
#include "Log.h"
#include <map>
#include <mutex>

namespace DC
{
namespace
{
std::map<unsigned, TierUnlockRule> const& UnlockRules()
{
    // Immutable sourced rules; table migrations become visible on restart.
    static auto const rules = []
    {
        std::map<unsigned, TierUnlockRule> result;
        auto rows = WorldDatabase.Query("SELECT p.tier_id,t.unlock_character_level,t.unlock_account_level,t.unlock_solo_gr "
            "FROM dc_tier_phase p JOIN dc_difficulty_tiers t ON t.tier=p.tier_name ORDER BY p.tier_id");
        if (!rows) throw std::runtime_error("Missing generated tier unlock rules");
        unsigned expected = 1;
        do
        {
            auto* f = rows->Fetch();
            unsigned id = f[0].Get<uint32>();
            if (id != expected++) throw std::runtime_error("Tier unlock keys must be contiguous from one");
            result.emplace(id, TierUnlockRule{f[1].Get<uint32>(), f[2].Get<uint32>(), f[3].Get<uint32>()});
        } while (rows->NextRow());
        return result;
    }();
    return rules;
}
}

unsigned LaunchTierCount()
{
    try
    {
        if (!Tunables::Has("monsters", "launch_tier_count"))
            throw std::runtime_error("Missing monsters.launch_tier_count");
        double value = Tunables::Get("monsters", "launch_tier_count");
        if (!std::isfinite(value) || value < 1 || value != std::floor(value) || value > UnlockRules().size())
            throw std::runtime_error("Launch tier count must fit generated tier rows; regenerate data before increasing it");
        return static_cast<unsigned>(value);
    }
    catch (std::exception const& error)
    {
        static std::once_flag logged;
        std::call_once(logged, [&] { LOG_ERROR("server", "[DC tiers] Disabled: {}", error.what()); });
        return 0; // Explicit invalid-configuration state; never a gameplay fallback.
    }
}

TierUnlockRule const& TierUnlock(unsigned tier)
{
    return UnlockRules().at(tier);
}

bool TierUnlocked(unsigned tier, unsigned level, unsigned accountLevel, unsigned beatenSoloGreaterRift)
{
    return tier >= 1 && tier <= LaunchTierCount()
        && MeetsTierUnlock(TierUnlock(tier), level, accountLevel, beatenSoloGreaterRift);
}
}
