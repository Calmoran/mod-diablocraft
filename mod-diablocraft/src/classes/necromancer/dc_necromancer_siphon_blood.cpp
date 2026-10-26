/*
 * Siphon Blood and its five runes. The core runs the channel; this strikes the targeted enemy every tick (the engine's
 * hit on the cast is none), pays the Essence of each strike, heals the Necromancer every second, and adds the rune's
 * part: Suppress slows the enemy, Purity of Essence pays more at full health, Drain Life heals more, Power Shift hits
 * harder with each strike. Blood Sucker's pull of health globes waits for the globes (not built).
 */

#include "dc_necromancer_siphon_blood.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_siphon_blood_math.h"

#include "ObjectAccessor.h"
#include "ScriptMgr.h"
#include "Spell.h"

#include <algorithm>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Necromancer::SiphonBlood
{
    namespace
    {
        constexpr std::string_view Skill = "Siphon Blood";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        struct Channel
        {
            std::uint32_t spellId = 0;
            ObjectGuid aim;
            double strikeClock = 0; // ms since the last strike
            double healClock = 0;   // ms since the last heal
            unsigned stacks = 0;    // Power Shift's
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Channel> channels;

        double Interval(Player* player, std::uint32_t spellId)
        {
            return TickSeconds(Tune("siphon_blood_tick_seconds"), Combat::AttacksPerSecond(player, spellId));
        }

        // One strike on `target`: the weapon damage of the tick, its Essence, and the rune's part.
        void Strike(Player* player, Unit* target, Channel& channel)
        {
            std::uint32_t const spellId = channel.spellId;
            Rune const rune = RuneAt(spellId);
            double pct = TickPct(Numbers::Num(spellId, "damage_pct"), Interval(player, spellId));
            if (rune == Rune::PowerShift)
                pct = PowerShiftPct(pct, Numbers::Num(spellId, "damage_bonus_pct"), channel.stacks);
            if (!Combat::Strike(player, target, spellId, pct))
                return;
            double const gainedAtFull = rune == Rune::PurityOfEssence ? Numbers::Num(spellId, "gain_resource") : 0.0;
            PayEssence(player, spellId,
                       EssenceOfTick(Numbers::Num(spellId, "generated_resource"), gainedAtFull,
                                     player->GetHealth() >= player->GetMaxHealth()));
            // A slow lasts to the next strike and a little past it, so it never lapses between two.
            if (rune == Rune::Suppress)
                Slow(player, target, Numbers::Num(spellId, "slow_pct"), Tune("siphon_blood_slow_linger_seconds"));
            if (rune == Rune::PowerShift)
                channel.stacks = NextStacks(channel.stacks, unsigned(Numbers::Num(spellId, "max_stacks_count")));
            Combat::Connected(player, spellId, 1);
        }

        class Channels final : public PlayerScript
        {
        public:
            Channels()
                : PlayerScript("dc_necromancer_siphon_blood",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                Channel channel;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = channels.find(player->GetGUID().GetRawValue());
                    if (found == channels.end())
                        return;
                    channel = found->second;
                }
                // The player let go - moved, cast something else, was interrupted - or died: the core ended the
                // channel.
                Spell* current = player->GetCurrentSpell(CURRENT_CHANNELED_SPELL);
                Unit* target = ObjectAccessor::GetUnit(*player, channel.aim);
                if (!player->IsAlive() || !current || current->GetSpellInfo()->Id != channel.spellId || !target ||
                    !target->IsAlive())
                {
                    if (current && current->GetSpellInfo()->Id == channel.spellId)
                        player->InterruptSpell(CURRENT_CHANNELED_SPELL);
                    Stop(player);
                    return;
                }
                unsigned const strikes = Due(channel.strikeClock, diff, Interval(player, channel.spellId) * 1000.0);
                for (unsigned i = 0; i < strikes && target->IsAlive(); ++i)
                    Strike(player, target, channel);
                // "heals you for {heal_pct} of your total health every second while channeled."
                if (Due(channel.healClock, diff, Tune("siphon_blood_heal_seconds") * 1000.0))
                    Heal(player, channel.spellId,
                         player->GetMaxHealth() * Numbers::Num(channel.spellId, "heal_pct") / 100.0);
                std::lock_guard<std::mutex> guard(mutex);
                if (auto found = channels.find(player->GetGUID().GetRawValue()); found != channels.end())
                    found->second = channel;
            }

            void OnPlayerLogout(Player* player) override
            {
                Stop(player);
            }

            void OnPlayerMapChanged(Player* player) override
            {
                Stop(player);
            }

            static void Stop(Player* player)
            {
                std::lock_guard<std::mutex> guard(mutex);
                channels.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) ? std::optional<double>(0.0) : std::nullopt;
    }

    bool PaysByStrike(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        if (!player || !RowOf(spellId, Skill) || targets.empty())
            return;
        Channel channel;
        channel.spellId = spellId;
        channel.aim = targets.front()->GetGUID();
        // The first strike lands at once.
        Strike(player, targets.front(), channel);
        std::lock_guard<std::mutex> guard(mutex);
        channels[player->GetGUID().GetRawValue()] = channel;
    }

    void RegisterScripts()
    {
        new Channels();
    }
} // namespace DC::Combat::Necromancer::SiphonBlood
