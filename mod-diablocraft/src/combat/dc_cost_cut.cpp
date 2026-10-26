#include "dc_cost_cut.h"
#include "dc_item_powers.h"
#include "GameTime.h"
#include "Player.h"
#include "ScriptMgr.h"
#include <chrono>
#include <map>
#include <mutex>
#include <string>
#include <unordered_map>

namespace DC::Combat::CostCut
{
    namespace
    {
        std::mutex mutex;
        // Each player's cuts: by skill, then by the caller's key.
        std::unordered_map<std::uint64_t, std::map<std::string, std::map<std::uint32_t, Held>>> held;

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        // The owner leaves: nothing it held stays.
        class Owner final : public PlayerScript
        {
        public:
            Owner()
                : PlayerScript("dc_cost_cut", {PLAYERHOOK_ON_LOGOUT})
            {
            }

            void OnPlayerLogout(Player* player) override
            {
                Clear(player);
            }
        };
    } // namespace

    void Hold(Player* player, std::string_view skill, std::uint32_t key, double pct, double seconds)
    {
        if (!player)
            return;
        Held const given = Given(pct, Now(), seconds);
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto& mine = held[player->GetGUID().GetRawValue()][std::string(skill)];
            if (Live(given, Now()))
                mine[key] = given;
            else
                mine.erase(key);
        }
        // The core charges the cost from the aura: put it where the cut is now, and again where the cut ends.
        ItemPowers::RefreshCostAuras(player);
        if (Live(given, Now()))
            player->m_Events.AddEventAtOffset(
                [player] { ItemPowers::RefreshCostAuras(player); },
                std::chrono::milliseconds(static_cast<std::uint64_t>(seconds * 1000.0) + 1));
    }

    void Stand(Player* player, std::string_view skill, std::uint32_t key, double pct)
    {
        if (!player)
            return;
        Held const standing = Standing(pct);
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto& mine = held[player->GetGUID().GetRawValue()][std::string(skill)];
            if (Live(standing, Now()))
                mine[key] = standing;
            else
                mine.erase(key);
        }
        ItemPowers::RefreshCostAuras(player);
    }

    double Pct(Player const* player, std::string_view skill)
    {
        if (!player)
            return 0.0;
        std::uint64_t const now = Now();
        std::lock_guard<std::mutex> guard(mutex);
        auto mine = held.find(player->GetGUID().GetRawValue());
        if (mine == held.end())
            return 0.0;
        auto cuts = mine->second.find(std::string(skill));
        if (cuts == mine->second.end())
            return 0.0;
        double pct = 0.0;
        for (auto const& [key, cut] : cuts->second)
            if (Live(cut, now))
                pct = Combine(pct, cut.pct);
        return pct;
    }

    void Clear(Player* player)
    {
        if (!player)
            return;
        {
            std::lock_guard<std::mutex> guard(mutex);
            held.erase(player->GetGUID().GetRawValue());
        }
        ItemPowers::RefreshCostAuras(player);
    }

    void RegisterScripts()
    {
        new Owner();
    }
} // namespace DC::Combat::CostCut
