/*
 * The Shaman's free Lava Burst: which Shamans hold the state.
 */

#include "dc_shaman_free_lava_burst.h"
#include "../../combat/dc_cost_cut.h"
#include "Player.h"

#include <cstdint>
#include <mutex>
#include <string_view>
#include <unordered_set>

namespace DC::Combat::Shaman::FreeLavaBurst
{
    namespace
    {
        constexpr std::string_view Skill = "Lava Burst";
        // The source of the cut: the free Lava Burst.
        constexpr std::uint32_t Key = 1;

        std::mutex mutex;
        std::unordered_set<std::uint64_t> pending;
    } // namespace

    void Grant(Player* player)
    {
        if (!player)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        pending.insert(player->GetGUID().GetRawValue());
        // The core charges the cost before the cast, so the whole cost comes off the skill's price until the cast.
        CostCut::Stand(player, Skill, Key, 100.0);
    }

    bool Pending(Player const* player)
    {
        if (!player)
            return false;
        std::lock_guard<std::mutex> guard(mutex);
        return pending.count(player->GetGUID().GetRawValue()) != 0;
    }

    void Spend(Player* player)
    {
        if (!player)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        pending.erase(player->GetGUID().GetRawValue());
        CostCut::Stand(player, Skill, Key, 0.0);
    }
} // namespace DC::Combat::Shaman::FreeLavaBurst
