/*
 * Devour and its five runes. The cast takes every corpse of the Necromancer's within reach and pays Essence for each;
 * the runes add Life, the minions' Essence, a cut to costs, a rise in maximum Life, or become an aura that does it as
 * the corpses come.
 */

#include "dc_necromancer_devour.h"
#include "dc_necromancer_common.h"
#include "dc_necromancer_devour_math.h"
#include "../../combat/dc_corpses.h"
#include "../../combat/dc_minions.h"
#include "../../stats/dc_stats.h"

#include "ScriptMgr.h"

#include <limits>
#include <mutex>
#include <unordered_map>

namespace DC::Combat::Necromancer::Devour
{
    namespace
    {
        constexpr std::string_view Skill = "Devour";

        double Tune(char const* name)
        {
            return DC::Tunables::Get("necromancer", name);
        }

        // Voracious's and Satiated's most stacks (the power's RUNEC and RUNEE Max Stacks, 25).
        unsigned StackCap()
        {
            return unsigned(Tune("devour_max_stacks"));
        }

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The reach: the skill's 60 yards, or the aura's radius with its share of the gold pickup radius.
        double Reach(Player* player, std::uint32_t spellId)
        {
            if (!TogglesAnAura(RuneAt(spellId)))
                return Numbers::Num(spellId, "radius_yards");
            auto const sheet = DC::Stats::Get(player->GetGUID().GetRawValue());
            return AuraRadius(Numbers::Num(spellId, "radius_yards"), Numbers::Num(spellId, "radius_share_pct"),
                              sheet ? (*sheet)[Stat::GoldPickupRange] : 0.0, Tune("devour_aura_max_radius_increase_yards"));
        }

        // Every corpse within reach goes, and the Essence of each is paid; the rune's part follows.
        void Consume(Player* player, std::uint32_t spellId)
        {
            Rune const rune = RuneAt(spellId);
            // The aura takes a few corpses a look; the cast takes every one within reach.
            auto const taken = Corpses::Consume(player, player->GetPosition(), float(Reach(player, spellId)),
                                                TogglesAnAura(rune) ? std::size_t(Tune("devour_aura_corpses_per_tick"))
                                                                    : std::numeric_limits<std::size_t>::max());
            double essence =
                EssenceOf(Numbers::Num(TogglesAnAura(rune) ? spellId : BaseId(Skill), "gain_resource"), taken.size());
            if (rune == Rune::Ruthless)
                // "Additionally consumes your minions for {gain_resource} Essence per minion killed."
                essence += EssenceOf(Numbers::Num(spellId, "gain_resource"), Minions::DismissAll(player));
            if (essence > 0)
                PayEssence(player, spellId, essence);
            if (taken.empty())
                return;
            switch (rune)
            {
                case Rune::Cannibalize:
                    // "Each corpse consumed also restores {heal_pct} health."
                    Heal(player, spellId,
                         HealOf(player->GetMaxHealth(), Numbers::Num(spellId, "heal_pct"), taken.size()));
                    break;
                case Rune::Voracious:
                    // "Reduces all essence costs by {cost_reduction_pct} for each corpse consumed for
                    // {duration_seconds} seconds."
                    Buffs::Stack(player, spellId, Stat::ResourceCostReduction, Bucket::Flat,
                                 Numbers::Num(spellId, "cost_reduction_pct"), StackCap(),
                                 Numbers::Num(spellId, "duration_seconds"), unsigned(taken.size()));
                    break;
                case Rune::Satiated:
                    // "Increases maximum life by {max_life_pct} for {duration_seconds} seconds for each corpse
                    // devoured."
                    Buffs::Stack(player, spellId, Stat::LifePercent, Bucket::Flat,
                                 Numbers::Num(spellId, "max_life_pct"), StackCap(),
                                 Numbers::Num(spellId, "duration_seconds"), unsigned(taken.size()));
                    break;
                default:
                    break;
            }
        }

        // The Necromancers whose Devouring Aura is on, and the clock to its next look.
        struct Standing
        {
            std::uint32_t spellId = 0;
            double clock = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Standing> auras;

        class Sweeps final : public PlayerScript
        {
        public:
            Sweeps()
                : PlayerScript("dc_necromancer_devour",
                               {PLAYERHOOK_ON_UPDATE, PLAYERHOOK_ON_LOGOUT, PLAYERHOOK_ON_MAP_CHANGED})
            {
            }

            void OnPlayerUpdate(Player* player, uint32 diff) override
            {
                Standing aura;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = auras.find(player->GetGUID().GetRawValue());
                    if (found == auras.end())
                        return;
                    aura = found->second;
                }
                // The aura goes with the rune on the bar and with the Necromancer's life.
                if (!player->IsAlive() || !Slotted(player, Skill) ||
                    RuneAt(Slotted(player, Skill)) != Rune::DevouringAura)
                {
                    Stop(player);
                    return;
                }
                for (unsigned i = PulsesDue(aura.clock, diff, Tune("devour_aura_tick_seconds")); i > 0; --i)
                    Consume(player, aura.spellId);
                std::lock_guard<std::mutex> guard(mutex);
                if (auto found = auras.find(player->GetGUID().GetRawValue()); found != auras.end())
                    found->second.clock = aura.clock;
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
                auras.erase(player->GetGUID().GetRawValue());
            }
        };
    } // namespace

    SpellCastResult CanCast(Player* player, std::uint32_t spellId)
    {
        if (!player || !RowOf(spellId, Skill) || TogglesAnAura(RuneAt(spellId)))
            return SPELL_CAST_OK;
        return CanDevour(RuneAt(spellId), Corpses::Count(player, player->GetPosition(), float(Reach(player, spellId))),
                         Minions::Count(player))
                   ? SPELL_CAST_OK
                   : SPELL_FAILED_NO_VALID_TARGETS;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !RowOf(spellId, Skill))
            return;
        if (!TogglesAnAura(RuneAt(spellId)))
        {
            Consume(player, spellId);
            return;
        }
        // "Becomes an aura": a cast turns it on, another off.
        bool on;
        {
            std::lock_guard<std::mutex> guard(mutex);
            on = !auras.erase(player->GetGUID().GetRawValue());
            if (on)
                auras[player->GetGUID().GetRawValue()] = {spellId, 0};
        }
        if (on)
            Consume(player, spellId);
    }

    void RegisterScripts()
    {
        new Sweeps();
    }
} // namespace DC::Combat::Necromancer::Devour
