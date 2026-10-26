/*
 * Burning: which enemies carry a Fire burn of which Shaman, and until when.
 */

#include "dc_shaman_burning.h"
#include "dc_shaman_common.h"
#include "dc_shaman_passives.h"
#include "../../combat/dc_periodic_strike.h"
#include "Unit.h"

#include <map>
#include <mutex>
#include <utility>

namespace DC::Combat::Shaman::Burning
{
    namespace
    {
        // The most entries kept before the ended ones are swept out.
        constexpr std::size_t SweepAt = 512;

        using Key = std::pair<std::uint64_t, std::uint64_t>; // the Shaman, the enemy
        std::mutex mutex;
        std::map<Key, std::uint64_t> burns; // game time the burn ends, ms

        Key KeyOf(Player const* player, Unit const* target)
        {
            return {player->GetGUID().GetRawValue(), target->GetGUID().GetRawValue()};
        }
    } // namespace

    void Ignite(Player* player, Unit* target, double seconds)
    {
        if (!player || !target || seconds <= 0)
            return;
        std::uint64_t const now = Now();
        std::lock_guard<std::mutex> guard(mutex);
        if (burns.size() >= SweepAt)
            for (auto it = burns.begin(); it != burns.end();)
                it = Holds(now, it->second) ? std::next(it) : burns.erase(it);
        std::uint64_t& until = burns[KeyOf(player, target)];
        until = Until(until, now, seconds);
    }

    void Burn(Player* player, Unit* target, std::uint32_t spellId, double totalPct, double seconds, double tickSeconds)
    {
        if (!player || !target || seconds <= 0 || tickSeconds <= 0)
            return;
        double const longer = Passive::BurnSecondsFor(player, seconds);
        PeriodicStrike::Start(player, target, spellId, Passive::BurnTotal(totalPct, seconds, longer), longer, tickSeconds);
        Ignite(player, target, longer);
    }

    bool Is(Player const* player, Unit const* target)
    {
        if (!player || !target)
            return false;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = burns.find(KeyOf(player, target));
        if (found == burns.end())
            return false;
        if (Holds(Now(), found->second))
            return true;
        burns.erase(found);
        return false;
    }
} // namespace DC::Combat::Shaman::Burning
