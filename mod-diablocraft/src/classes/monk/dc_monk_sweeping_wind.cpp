/*
 * Sweeping Wind and its five runes. The shape of each rune is Power/Monk_SweepingWind.pow: a vortex around the
 * Monk that ticks every SF_11 seconds, stacks that every attack of a Spirit Generator adds, and the rune's own change.
 */

#include "dc_monk_sweeping_wind_cast.h"
#include "dc_monk_sweeping_wind.h"
#include "dc_monk_common.h"
#include "../dc_resources.h"
#include "../../combat/dc_item_powers.h"
#include "../../combat/dc_taunt_decoy.h"
#include "../../combat/dc_taunt_decoy_math.h"
#include "../../rifts/dc_ally.h"
#include "../../stats/dc_resource_pulse.h"
#include "Util.h"

#include <chrono>
#include <string>

namespace DC::Combat::Monk::Wind
{
    namespace
    {
        constexpr std::string_view Skill = "Sweeping Wind";
        // Stock "Ice Blast", the freeze Fists of Thunder - Wind Blast holds with: one MOD_STUN, mechanic STUN.
        constexpr std::uint32_t FreezeHold = 15878;

        Shells::Ability const* Row(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        bool IsRune(std::uint32_t spellId, std::string_view rune)
        {
            auto const* row = Row(spellId);
            return row && rune == row->rune;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        // Vengeful Wind: the stacks the worn item adds to the vortex's maximum (`max_stacks_add`, 0
        // with none). Asked before the vortex's lock, as every item-power reader.
        double Raise(Player const* player)
        {
            return ItemPowers::SkillSetTo(player, std::string(Skill), "max_stacks_add", 0);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint32_t Millis(double seconds)
        {
            return seconds > 0 ? std::uint32_t(seconds * 1000 + 0.5) : 0u;
        }

        // The vortex lasts the skill's duration_seconds (6): Cyclone's and Master of Wind's own duration_seconds is
        // something else (the tornado's, the run of damage), so a rune answers with what it inherits.
        double VortexSeconds(std::uint32_t spellId)
        {
            if (auto inherited = Numbers::Inherited(spellId, "duration_seconds"))
                return *inherited;
            return Numbers::Num(spellId, "duration_seconds");
        }

        struct Vortex
        {
            std::uint32_t spellId = 0;
            std::uint64_t until = 0;
            unsigned stacks = 0;
            unsigned ticks = 0;
            std::uint64_t stamp = 0;
            std::uint64_t quietMs = 0; // Kyoshiro's Soul: the run of ticks that damaged no enemy
            std::uint64_t lastHit = 0; // the last enemy the Monk hit (raw guid): Monkey King's Garb 4-piece puts its decoy beside it
            std::unordered_map<std::uint64_t, Streak> streaks; // Master of Wind, by enemy
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Vortex> vortices; // by Monk
        std::uint64_t stamps = 0;

        void Freeze(Player* player, Unit* enemy, double seconds)
        {
            if (seconds <= 0 || !enemy->IsAlive())
                return;
            enemy->RemoveAurasDueToSpell(FreezeHold, player->GetGUID());
            if (Aura* hold = player->AddAura(FreezeHold, enemy))
            {
                hold->SetMaxDuration(int32(seconds * 1000));
                hold->SetDuration(int32(seconds * 1000));
            }
        }

        // Monkey King's Garb 4-piece: "spawns a decoy next to the last enemy you hit that taunts nearby enemies and then explodes for
        // {perStackPct}% weapon damage for each stack of Sweeping Wind you have". The creature is the decoy of data/legendary_summons.csv;
        // the taunt radius, the delay and the explosion radius are the set's power file numbers (the monk sheet's d3_value), and a zero builds no decoy.

        // How far off an enemy the decoy stands, so it is not inside it.
        constexpr float DecoyBesideYards = 1.5f;

        double OpenNumber(char const* name)
        {
            return DC::Tunables::Has("monk", name) ? DC::Tunables::Get("monk", name) : 0.0;
        }

        unsigned StacksNow(Player const* player)
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = vortices.find(player->GetGUID().GetRawValue());
            return found == vortices.end() ? 0u : found->second.stacks;
        }

        void Decoy(Player* player, std::uint32_t spellId, std::uint64_t lastHit, double perStackPct)
        {
            // "next to the last enemy you hit"; with none, a little in front of the Monk (the power file's offset when there are no enemies).
            Unit* near = lastHit ? ObjectAccessor::GetUnit(*player, ObjectGuid(lastHit)) : nullptr;
            Position where = near && near->IsAlive() && player->IsValidAttackTarget(near)
                                 ? near->GetNearPosition(DecoyBesideYards, near->GetAbsoluteAngle(player))
                                 : player->GetNearPosition(float(OpenNumber("monkey_kings_garb_decoy_empty_offset_yards")), player->GetOrientation());
            Combat::TauntDecoy::Spec spec;
            spec.entry = Rifts::Ally::DecoyEntry;
            spec.spellId = spellId;
            spec.tauntRadius = OpenNumber("monkey_kings_garb_decoy_taunt_radius_yards");
            spec.delaySeconds = OpenNumber("monkey_kings_garb_decoy_explode_delay_seconds");
            spec.blastRadius = OpenNumber("monkey_kings_garb_decoy_explode_radius_yards");
            spec.blastPct = [player, perStackPct] { return Combat::TauntDecoy::BlastPct(perStackPct, StacksNow(player)); };
            Combat::TauntDecoy::Place(player, where, spec);
        }

        void Schedule(Player* player, std::uint64_t stamp);

        void Tick(Player* player, std::uint64_t stamp)
        {
            auto const now = Now();
            std::uint32_t spellId;
            unsigned stacks, index;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = vortices.find(player->GetGUID().GetRawValue());
                if (found == vortices.end() || found->second.stamp != stamp)
                    return;
                Vortex& vortex = found->second;
                if (now >= vortex.until || !player->IsAlive() || !player->IsInWorld())
                {
                    vortices.erase(found);
                    return;
                }
                spellId = vortex.spellId;
                stacks = vortex.stacks;
                index = ++vortex.ticks;
            }
            double const tick = Tune("sweeping_wind_tick_seconds");
            // "continuously deals {damage_pct:base} weapon damage to all enemies within {radius_yards} yards" (Fire
            // Storm's radius_yards is 14).
            double const pct = TickPct(Numbers::Num(spellId, "damage_pct", "base"), stacks, tick);
            std::vector<Unit*> struck;
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                if (Combat::Strike(player, enemy, spellId, pct, true))
                    struck.push_back(enemy);
            // Kyoshiro's Soul: stacks for each whole second the vortex damages no enemy, up to the
            // skill's maximum. The item powers are asked before the vortex's lock.
            unsigned const idle = static_cast<unsigned>(
                std::lround(ItemPowers::SkillSetTo(player, std::string(Skill), "idle_stacks_per_second", 0)));
            double const raise = Raise(player); // Vengeful Wind's raised maximum
            double const decoyPct = ItemPowers::SkillSetTo(player, std::string(Skill), "decoy_damage_pct_per_stack", 0);
            std::uint64_t lastHit = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = vortices.find(player->GetGUID().GetRawValue());
                if (found == vortices.end() || found->second.stamp != stamp)
                    return;
                Vortex& vortex = found->second;
                vortex.stacks = std::min(vortex.stacks + IdleGain(vortex.quietMs, !struck.empty(), Millis(tick), idle),
                                         MaxStacks(Numbers::Num(spellId, "max_stacks_count"), raise));
                if (!struck.empty())
                    vortex.lastHit = struck.back()->GetGUID().GetRawValue();
                lastHit = vortex.lastHit;
            }
            // Monkey King's Garb 4-piece: a decoy each whole second of the vortex's ticks.
            if (decoyPct > 0 && CompletesSecond(index, tick))
                Decoy(player, spellId, lastHit, decoyPct);

            auto const threshold = Numbers::Get(spellId, "stack_threshold_count");
            bool const full = threshold && stacks >= *threshold;
            // Inner Storm: a module tick, since Spirit has no regeneration aura: the rate's worth once a
            // second, as a flow over that second.
            if (full && IsRune(spellId, "Inner Storm") && PaysSpirit(index, tick))
                Resources::Flow(player, Resources::Spirit, Numbers::Num(spellId, "regen_per_second_resource"), 1000);

            if (IsRune(spellId, "Master of Wind"))
            {
                // "While your vortex is at {stack_threshold_count} or more stacks, enemies damaged by Sweeping Wind for
                // {duration_seconds} consecutive seconds are Frozen for {freeze_duration_seconds} seconds ... not more
                // than once every {internal_cooldown_seconds} seconds."
                std::vector<Unit*> frozen;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    auto found = vortices.find(player->GetGUID().GetRawValue());
                    if (found == vortices.end() || found->second.stamp != stamp)
                        return;
                    Vortex& vortex = found->second;
                    if (!full)
                        vortex.streaks.clear();
                    else
                    {
                        for (Unit* enemy : struck)
                            if (vortex.streaks[enemy->GetGUID().GetRawValue()].Damaged(
                                    now, Millis(tick), Millis(Numbers::Num(spellId, "duration_seconds")),
                                    Millis(Numbers::Num(spellId, "internal_cooldown_seconds"))))
                                frozen.push_back(enemy);
                        std::erase_if(vortex.streaks, [now](auto const& entry) { return entry.second.last != now; });
                    }
                }
                for (Unit* enemy : frozen)
                    Freeze(player, enemy, Numbers::Num(spellId, "freeze_duration_seconds"));
            }
            Schedule(player, stamp);
        }

        void Schedule(Player* player, std::uint64_t stamp)
        {
            player->m_Events.AddEventAtOffset([player, stamp] { Tick(player, stamp); },
                                              std::chrono::milliseconds(Millis(Tune("sweeping_wind_tick_seconds"))));
        }

        // Cyclone's lightning tornado: it stays where the Monk stood when it spawned and, every SF_28 seconds for its
        // duration, arcs lightning to SF_32 enemy within SF_30 yards of itself (SF_36: the tornado deals no damage of
        // its own).
        void Arc(Player* player, std::uint32_t spellId, Position where, unsigned left)
        {
            if (!left || !player->IsAlive() || !player->IsInWorld())
                return;
            auto enemies = Combat::Enemies(player, spellId, where, Tune("sweeping_wind_tornado_seek_yards"));
            for (unsigned arc = 0; arc < unsigned(Tune("sweeping_wind_tornado_arcs")) && !enemies.empty(); ++arc)
            {
                std::size_t pick = urand(0, uint32(enemies.size() - 1));
                Combat::Strike(player, enemies[pick], spellId, Numbers::Num(spellId, "damage_pct"), true);
                enemies.erase(enemies.begin() + pick);
            }
            if (left > 1)
                player->m_Events.AddEventAtOffset(
                    [player, spellId, where, left] { Arc(player, spellId, where, left - 1); },
                    std::chrono::milliseconds(Millis(Tune("sweeping_wind_tornado_tick_seconds"))));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return Row(spellId) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        // The vortex deals the damage: the cast's own hit is nothing (Cyclone's 95% is its tornado's).
        return Row(spellId) ? std::optional<double>(0.0) : std::nullopt;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !Row(spellId) || !Millis(Tune("sweeping_wind_tick_seconds")))
            return;
        std::uint64_t stamp;
        {
            // A new cast starts the vortex over with one stack; the old one's ticks find their stamp gone.
            std::lock_guard<std::mutex> guard(mutex);
            Vortex& vortex = vortices[player->GetGUID().GetRawValue()];
            vortex = Vortex{};
            vortex.spellId = spellId;
            vortex.until = Now() + Millis(VortexSeconds(spellId));
            vortex.stacks = 1;
            vortex.stamp = stamp = ++stamps;
        }
        Schedule(player, stamp);
    }

    void Landed(Player* player)
    {
        if (!player)
            return;
        auto const now = Now();
        std::lock_guard<std::mutex> guard(mutex);
        auto found = vortices.find(player->GetGUID().GetRawValue());
        if (found != vortices.end() && found->second.until > now)
            found->second.until = now + Millis(VortexSeconds(found->second.spellId));
    }

    void Struck(Player* player, Unit* target)
    {
        if (!player || !target)
            return;
        std::lock_guard<std::mutex> guard(mutex);
        auto found = vortices.find(player->GetGUID().GetRawValue());
        if (found != vortices.end())
            found->second.lastHit = target->GetGUID().GetRawValue();
    }

    bool Active(Player const* player)
    {
        if (!player)
            return false;
        auto const now = Now();
        std::lock_guard<std::mutex> guard(mutex);
        auto found = vortices.find(player->GetGUID().GetRawValue());
        return found != vortices.end() && found->second.until > now;
    }

    unsigned Stacks(Player const* player)
    {
        if (!player)
            return 0;
        auto const now = Now();
        std::lock_guard<std::mutex> guard(mutex);
        auto found = vortices.find(player->GetGUID().GetRawValue());
        return found != vortices.end() && found->second.until > now ? found->second.stacks : 0u;
    }

    void Attack(Player* player, bool generates)
    {
        if (!player)
            return;
        auto const now = Now();
        std::uint32_t spellId = 0;
        bool tornado = false;
        double const raise = Raise(player);
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = vortices.find(player->GetGUID().GetRawValue());
            if (found == vortices.end() || found->second.until <= now)
                return;
            Vortex& vortex = found->second;
            spellId = vortex.spellId;
            unsigned const most = MaxStacks(Numbers::Num(spellId, "max_stacks_count"), raise);
            // The power file states no position for Cyclone's tornado and no trigger of its own: the tornado spawns on the
            // attack of a Spirit Generator that finds the vortex already at its maximum, at the Monk.
            tornado = IsRune(spellId, "Cyclone") && SpawnsTornado(vortex.stacks, most, generates);
            vortex.stacks = StacksAfter(vortex.stacks, most, generates);
        }
        if (tornado)
            Arc(player, spellId, player->GetPosition(),
                Ticks(Numbers::Num(spellId, "duration_seconds"), Tune("sweeping_wind_tornado_tick_seconds")));
    }
} // namespace DC::Combat::Monk::Wind
