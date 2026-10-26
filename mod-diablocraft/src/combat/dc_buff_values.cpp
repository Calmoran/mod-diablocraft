#include "dc_buff_values.h"
#include "dc_buff_values_math.h"
#include "../common/dc_bridge.h"
#include "../common/dc_tunables.h"
#include "Player.h"
#include "SpellAuras.h"
#include "SpellInfo.h"
#include "ScriptMgr.h"
#include "Timer.h"

#include <algorithm>
#include <cmath>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::BuffValues
{
    namespace
    {
        constexpr char const* Prefix = "DCBUFFVAL";

        std::mutex mutex;
        std::unordered_map<std::uint64_t, Channel> channels;

        std::uint32_t Interval()
        {
            double const ms = DC::Tunables::Get("combat", "buff_values_push_ms");
            return ms > 0 ? static_cast<std::uint32_t>(ms) : 0;
        }

        void Send(Player* player, Record const& record)
        {
            DC::Bridge::Push(player, Prefix, Fields(record.aura, record.gone, record.values));
        }
    } // namespace

    void Set(Player* player, std::uint32_t aura, std::vector<double> const& values)
    {
        if (!player || !aura)
            return;
        std::optional<Record> now;
        {
            std::lock_guard<std::mutex> lock(mutex);
            now = channels[player->GetGUID().GetRawValue()].Set(aura, values, getMSTime(), Interval());
        }
        if (now)
            Send(player, *now);
    }

    void Clear(Player* player, std::uint32_t aura)
    {
        if (!player || !aura)
            return;
        std::optional<Record> now;
        {
            std::lock_guard<std::mutex> lock(mutex);
            auto found = channels.find(player->GetGUID().GetRawValue());
            if (found == channels.end())
                return;
            now = found->second.Clear(aura);
            if (found->second.Empty())
                channels.erase(found);
        }
        if (now)
            Send(player, *now);
    }

    void Show(Player* player, std::uint32_t auraId, unsigned stacks, double seconds, std::vector<double> const& values)
    {
        if (!player || !auraId)
            return;
        if (!stacks || !player->IsAlive())
        {
            player->RemoveAurasDueToSpell(auraId);
            Clear(player, auraId);
            return;
        }
        Aura* aura = player->GetAura(auraId);
        if (!aura)
            aura = player->AddAura(auraId, player);
        if (!aura)
            return;
        auto const shown = std::uint8_t(std::min<unsigned>(stacks, std::max<unsigned>(1, aura->GetSpellInfo()->StackAmount)));
        if (aura->GetStackAmount() != shown)
            aura->SetStackAmount(shown);
        if (seconds > 0)
        {
            auto const milliseconds = std::int32_t(std::llround(seconds * 1000.0));
            if (TimerDiffers(aura->GetDuration(), milliseconds))
            {
                aura->SetMaxDuration(milliseconds);
                aura->SetDuration(milliseconds);
            }
        }
        if (!values.empty())
            Set(player, auraId, values);
    }

    namespace
    {
        // The held records go out once their interval has passed; a logout forgets the player.
        class Flusher final : public PlayerScript
        {
        public:
            Flusher() : PlayerScript("dc_buff_values", {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT}) {}

            void OnPlayerUpdate(Player* player, uint32) override
            {
                std::vector<Record> due;
                {
                    std::lock_guard<std::mutex> lock(mutex);
                    auto found = channels.find(player->GetGUID().GetRawValue());
                    if (found == channels.end())
                        return;
                    due = found->second.Flush(getMSTime(), Interval());
                }
                for (Record const& record : due)
                    Send(player, record);
            }

            void OnPlayerLogout(Player* player) override
            {
                std::lock_guard<std::mutex> lock(mutex);
                channels.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    void RegisterScripts()
    {
        new Flusher();
    }
} // namespace DC::Combat::BuffValues
