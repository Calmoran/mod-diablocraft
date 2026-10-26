/*
 * Tempest Rush and its five runes. Power/Monk_TempestRush.pow: a channel that drains its Spirit cost every
 * second in ticks of 0.2 s and deals 390% weapon damage a second in the same ticks to the enemies within 7 yards. Until
 * the Monk has channel records the module runs it: the press is the cast (its cost is the first second), a second
 * press stops it.
 */

#include "dc_monk_tempest_rush_cast.h"
#include "dc_monk_tempest_rush.h"
#include "../dc_resources.h"
#include "../../combat/dc_movement_effects.h"
#include "dc_monk_common.h"
#include "../../combat/dc_item_powers.h"
#include "../../stats/dc_stats.h"

#include <cmath>
#include <string>

namespace DC::Combat::Monk::TempestRush
{
    namespace
    {
        constexpr std::string_view Skill = "Tempest Rush";

        // Per Monk: the channel that runs. `generation` tells a tick of a channel that has since ended from the tick of
        // the one running now (a stop and a new press inside one tick).
        struct Run
        {
            bool active = false;
            std::uint32_t spellId = 0;
            std::uint64_t generation = 0;
            std::uint64_t start = 0;
            Prepaid prepaid;
            Seen knocked;
            // The Tailwind record whose speed this channel put on the Monk (TailwindOf at the press), 0 for none.
            std::uint32_t tailwind = 0;
        };
        std::mutex mutex;
        std::unordered_map<std::uint64_t, Run> runs;
        std::uint64_t lastGeneration = 0;

        Shells::Ability const* RowOf(std::uint32_t spellId)
        {
            auto const* row = Shells::FindAbility(spellId);
            return row && Skill == row->skill ? row : nullptr;
        }

        bool IsRune(std::uint32_t spellId, std::string_view rune)
        {
            auto const* row = RowOf(spellId);
            return row && rune == row->rune;
        }

        double Tune(char const* name)
        {
            return DC::Tunables::Get("monk", name);
        }

        std::uint64_t Now()
        {
            return std::uint64_t(GameTime::GetGameTimeMS().count());
        }

        std::uint64_t Millis(double seconds)
        {
            return std::uint64_t(seconds * 1000.0 + 0.5);
        }

        std::uint32_t SkillId()
        {
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && !*row.rune)
                    return row.id;
            return 0;
        }

        // The Tailwind record whose movement speed a Tempest Rush press puts on: the cast's own when Tailwind is the chosen rune,
        // else the rune's record when a power gives it without choosing it (kind `rune`, Warstaff of General Quang), else 0. Chosen and given, it counts once.
        std::uint32_t TailwindOf(Player* player, std::uint32_t spellId)
        {
            if (IsRune(spellId, "Tailwind"))
                return spellId;
            if (!ItemPowers::GrantsRune(player, std::string(Skill), "Tailwind"))
                return 0;
            for (auto const& row : Shells::Abilities)
                if (Skill == row.skill && std::string_view("Tailwind") == row.rune)
                    return row.id;
            return 0;
        }

        // The sheet's per-second damage: Northern Breeze states its own 500%; every other rune's damage_pct (Electric
        // Field's 135%, Flurry's 90%) is for its extra, so the channel itself stays the skill's 390%.
        double DamagePerSecond(std::uint32_t spellId)
        {
            return Numbers::Num(IsRune(spellId, "Northern Breeze") ? spellId : SkillId(), "damage_pct");
        }

        // The sheet's per-second cost: Northern Breeze states 25, the others inherit the skill's 30.
        double CostPerSecond(std::uint32_t spellId)
        {
            return Numbers::Num(spellId, "cost_resource");
        }

        double TickSeconds()
        {
            return Tune("tempest_rush_tick_seconds");
        }

        void Tick(Player* player, std::uint64_t generation);
        void FieldTick(Player* player, std::uint64_t generation);

        // Whether the channel `generation` of this Monk still runs; its spell id when it does.
        std::uint32_t Running(Player* player, std::uint64_t generation)
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = runs.find(player->GetGUID().GetRawValue());
            return found != runs.end() && found->second.active && found->second.generation == generation
                       ? found->second.spellId
                       : 0;
        }

        void End(Player* player)
        {
            std::uint32_t spellId = 0;
            std::uint32_t tailwind = 0;
            std::uint64_t start = 0;
            {
                std::lock_guard<std::mutex> guard(mutex);
                auto found = runs.find(player->GetGUID().GetRawValue());
                if (found == runs.end() || !found->second.active)
                    return;
                found->second.active = false;
                spellId = found->second.spellId;
                tailwind = found->second.tailwind;
                start = found->second.start;
            }
            // Tailwind's speed lasts as long as the channel.
            if (tailwind)
            {
                Stats::RemoveContribution(player->GetGUID().GetRawValue(), Source::Temporary, Stat::MovementSpeed,
                                          tailwind);
                Stats::Recompute(player);
            }
            // Flurry: "After you stop channeling Tempest Rush, you cause an icy blast to all enemies within
            // {radius_yards} yards. The damage of the explosion increases by {damage_pct} weapon damage as Cold while
            // channeling": one stack of that damage for each attack period the channel ran (pow SF_34, SF_36).
            if (IsRune(spellId, "Flurry") && player->IsAlive())
                if (unsigned stacks =
                        FlurryStacks(double(Now() - start) / 1000.0, Combat::AttacksPerSecond(player, spellId),
                                     unsigned(Tune("tempest_rush_flurry_max_stacks")));
                    stacks > 0)
                    Combat::StrikeArea(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards"),
                                       Numbers::Num(spellId, "damage_pct") * stacks);
        }

        // One tick of the channel's own damage on the enemies around the Monk, with Bluster's extras.
        void Hit(Player* player, std::uint32_t spellId)
        {
            double const pct = PerTick(DamagePerSecond(spellId), TickSeconds());
            unsigned struck = 0;
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, player->GetPosition(), Tune("tempest_rush_radius_yards")))
            {
                if (!Combat::Strike(player, enemy, spellId, pct))
                    continue;
                ++struck;
                // The power file's base skill knocks every enemy it hits back (SF_6): once
                // for the channel, or the 7 yard circle would shove an enemy out on the first tick and again on every return.
                bool first = false;
                {
                    std::lock_guard<std::mutex> guard(mutex);
                    first = runs[player->GetGUID().GetRawValue()].knocked.First(enemy->GetGUID().GetRawValue());
                }
                if (first)
                    Abilities::Knockback(player, enemy, Tune("tempest_rush_knockback_yards"));
                // "Enemies hit ... deal {enemy_damage_pct} reduced damage for {duration_seconds} seconds": renewed by every tick.
                if (IsRune(spellId, "Bluster"))
                    Effects::Weaken(enemy, spellId, Numbers::Num(spellId, "enemy_damage_pct"),
                                    Numbers::Num(spellId, "duration_seconds"));
            }
            // A tick that hit is a spender's hit, once for the tick as a cast is (Life per Hit, the hit_spender powers: Won Khim Lau's
            // Cyclone Strike; the press is ResolveCast's own).
            if (struck)
                Combat::Connected(player, spellId, struck);
        }

        // One tick: pay it unless the press already did, then hit; the next tick, or the end.
        void Tick(Player* player, std::uint64_t generation)
        {
            std::uint32_t const spellId = Running(player, generation);
            if (!spellId)
                return;
            if (!player->IsAlive())
            {
                End(player);
                return;
            }
            bool covered = false;
            {
                std::lock_guard<std::mutex> guard(mutex);
                covered = runs[player->GetGUID().GetRawValue()].prepaid.Covers(Now());
            }
            // Kekegi's Unbreakable Spirit: a tick inside its window is free; the core's own costs are free through the gear aura.
            if (!covered && !ItemPowers::CostFree(player))
            {
                auto const units = std::int32_t(std::llround(
                    Resources::ToUnits(Resources::Spirit, PerTick(CostPerSecond(spellId), TickSeconds()))));
                // The channel stops when a tick cannot be paid: the empty pool.
                if (Resources::Units(player, Resources::Spirit) < std::uint32_t(units))
                {
                    End(player);
                    return;
                }
                Resources::SpendUnits(player, Resources::Spirit, units);
            }
            Hit(player, spellId);
            player->m_Events.AddEventAtOffset([player, generation] { Tick(player, generation); },
                                              Milliseconds(Millis(TickSeconds())));
        }

        // Electric Field: "Enemies within {radius_yards} yards take an additional {damage_pct} weapon damage as
        // Lightning every second", in ticks of pow SF_27 (0.25 s).
        void FieldTick(Player* player, std::uint64_t generation)
        {
            std::uint32_t const spellId = Running(player, generation);
            if (!spellId)
                return;
            double const seconds = Tune("tempest_rush_field_tick_seconds");
            double const pct = PerTick(Numbers::Num(spellId, "damage_pct"), seconds);
            for (Unit* enemy :
                 Combat::Enemies(player, spellId, player->GetPosition(), Numbers::Num(spellId, "radius_yards")))
                Combat::Strike(player, enemy, spellId, pct);
            player->m_Events.AddEventAtOffset([player, generation] { FieldTick(player, generation); },
                                              Milliseconds(Millis(seconds)));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId) != nullptr;
    }

    bool Toggle(Player* player, std::uint32_t spellId)
    {
        if (!player || !RowOf(spellId))
            return false;
        {
            std::lock_guard<std::mutex> guard(mutex);
            auto found = runs.find(player->GetGUID().GetRawValue());
            if (found == runs.end() || !found->second.active)
                return false;
        }
        End(player);
        return true;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!RowOf(spellId))
            return std::nullopt;
        return DamagePerSecond(spellId);
    }

    Punch Begin(Player* player, std::uint32_t spellId)
    {
        Punch punch;
        if (!player || !RowOf(spellId))
            return punch;
        // The press is the channel's first tick: the cast's own hit deals one tick's share.
        punch.pct = PerTick(DamagePerSecond(spellId), TickSeconds());
        return punch;
    }

    void Cast(Player* player, std::uint32_t spellId)
    {
        if (!player || !RowOf(spellId))
            return;
        // Read before the lock: the item powers take their own.
        std::uint32_t const tailwind = TailwindOf(player, spellId);
        std::uint64_t generation = 0;
        {
            std::lock_guard<std::mutex> guard(mutex);
            Run& run = runs[player->GetGUID().GetRawValue()];
            if (run.active)
                return;
            run = Run{};
            run.active = true;
            run.spellId = spellId;
            run.generation = generation = ++lastGeneration;
            run.start = Now();
            run.tailwind = tailwind;
            // The record's cost is one second of the channel's.
            run.prepaid.Press(run.start, 1000);
        }
        if (tailwind)
        {
            Stats::AddContribution(player->GetGUID().GetRawValue(),
                                   {Source::Temporary, Stat::MovementSpeed, tailwind,
                                    Numbers::Num(tailwind, "movement_speed_pct"), Bucket::Uncapped});
            Stats::Recompute(player);
        }
        player->m_Events.AddEventAtOffset([player, generation] { Tick(player, generation); },
                                          Milliseconds(Millis(TickSeconds())));
        if (IsRune(spellId, "Electric Field"))
            player->m_Events.AddEventAtOffset([player, generation] { FieldTick(player, generation); },
                                              Milliseconds(Millis(Tune("tempest_rush_field_tick_seconds"))));
    }

    void Stop(Player* player)
    {
        if (player)
            End(player);
    }
} // namespace DC::Combat::Monk::TempestRush
