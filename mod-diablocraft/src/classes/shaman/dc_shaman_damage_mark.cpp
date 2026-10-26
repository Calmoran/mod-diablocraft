/*
 * The Shaman's damage mark: which enemies take more damage from which Shaman, and until when.
 */

#include "dc_shaman_damage_mark.h"
#include "dc_shaman_common.h"
#include "ObjectGuid.h"
#include "Unit.h"

#include <mutex>
#include <unordered_map>

namespace DC::Combat::Shaman::DamageMark
{
    namespace
    {
        struct Marked
        {
            ObjectGuid owner;
            std::uint64_t until = 0; // game time, ms
            double pct = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Marked> marks; // by the marked enemy
    } // namespace

    void Set(Player* player, Unit* target, double pct, double seconds)
    {
        if (!player || !target || pct <= 0 || seconds <= 0)
            return;
        Marked mark;
        mark.owner = player->GetGUID();
        mark.until = Now() + std::uint64_t(seconds * 1000.0);
        mark.pct = pct;
        std::lock_guard<std::mutex> guard(mutex);
        marks[target->GetGUID().GetRawValue()] = mark;
    }

    void Multipliers(Player* player, Unit* target, DC::Combat::Factors& out)
    {
        if (!player || !target)
            return;
        double pct = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = marks.find(target->GetGUID().GetRawValue());
            if (found == marks.end())
                return;
            if (!Holds(Now(), found->second.until))
            {
                marks.erase(found);
                return;
            }
            if (found->second.owner == player->GetGUID())
                pct = found->second.pct;
        }
        if (double const bonus = Bonus(pct > 0, pct))
            AddFactor(out, "Damage mark", bonus);
    }
} // namespace DC::Combat::Shaman::DamageMark
