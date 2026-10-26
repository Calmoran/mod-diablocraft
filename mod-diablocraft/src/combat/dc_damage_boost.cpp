#include "dc_damage_boost.h"
#include "dc_damage_boost_math.h"
#include "GameTime.h"
#include "Player.h"
#include "ScriptMgr.h"
#include <map>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::DamageBoost
{
    namespace
    {
        std::mutex mutex;
        std::unordered_map<std::uint64_t, std::map<std::uint32_t, Held>> held;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // The owner leaves: nothing it held stays.
        class Owner final : public PlayerScript
        {
        public:
            Owner()
                : PlayerScript("dc_damage_boost", {PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerLogout(Player* player) override
            {
                Clear(player);
            }
        };
    } // namespace

    void Hold(Player* target, std::uint32_t key, double pct, double seconds)
    {
        if (!target)
            return;
        Held const given = Given(pct, Now(), seconds);
        std::lock_guard<std::mutex> guard(mutex);
        auto& mine = held[target->GetGUID().GetRawValue()];
        if (Live(given, Now()))
            mine[key] = given;
        else
            mine.erase(key);
    }

    void Multipliers(Player const* player, Factors& out)
    {
        if (!player)
            return;
        std::uint64_t const now = Now();
        std::lock_guard<std::mutex> guard(mutex);
        auto found = held.find(player->GetGUID().GetRawValue());
        if (found == held.end())
            return;
        for (auto boost = found->second.begin(); boost != found->second.end();)
        {
            if (!Live(boost->second, now))
            {
                boost = found->second.erase(boost);
                continue;
            }
            AddFactor(out, "Damage boost", boost->second.pct);
            ++boost;
        }
        if (found->second.empty())
            held.erase(found);
    }

    void Clear(Player const* player)
    {
        if (!player)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        held.erase(player->GetGUID().GetRawValue());
    }

    void RegisterScripts()
    {
        new Owner();
    }
} // namespace DC::Combat::DamageBoost
