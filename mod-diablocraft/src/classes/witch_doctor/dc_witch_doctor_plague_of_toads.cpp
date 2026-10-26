/*
 * Plague of Toads and its five runes. The cast is the engine's line (a spell record and the sheet's numbers: free to
 * cast, the line's reach and width, each rune's school); here: the toads reaching the nearest enemy on the line
 * (Piercing Toads' reach every enemy, the engine's own hit), Rain of Toads' rain on the enemy's place and its faster
 * casting, Toad Affinity's Mana (the class's Connected seam), Addling Toads' confusion.
 */

#include "dc_witch_doctor_plague_of_toads.h"
#include "dc_witch_doctor_common.h"
#include "dc_witch_doctor_effects.h"
#include "../../combat/dc_combat.h"
#include "../../combat/dc_spell_numbers.h"
#include "Player.h"
#include "Position.h"
#include "Random.h"
#include "Unit.h"

#include <chrono>
#include <vector>

namespace DC::Combat::WitchDoctor::PlagueOfToads
{
    namespace
    {
        constexpr std::string_view Skill = "Plague of Toads";

        Rune RuneAt(std::uint32_t spellId)
        {
            auto const* row = RowOf(spellId, Skill);
            return row ? RuneOf(row->rune) : Rune::None;
        }

        // The enemy of `targets` nearest to the player, the first on a tie; null when there are none.
        Unit* Nearest(Player* player, std::vector<Unit*> const& targets)
        {
            if (targets.empty())
                return nullptr;
            std::vector<double> distances;
            for (Unit* enemy : targets)
                distances.push_back(player->GetExactDist(enemy));
            return targets[NearestOf(distances)];
        }

        // Rain of Toads: "Cause toads to rain from the sky that deal {damage_pct} weapon damage to enemies in the area
        // over {dot_duration_seconds} seconds": every enemy within the file's rain area of the enemy aimed at takes an
        // even share each tick.
        void Rain(Player* player, std::uint32_t spellId, Unit* aim)
        {
            Position const where = aim->GetPosition();
            unsigned const ticks = PeriodicStrike::Ticks(Numbers::Num(spellId, "dot_duration_seconds"),
                                                         Tune("plague_of_toads_rain_tick_seconds"));
            double const pct = PeriodicStrike::TickPct(Numbers::Num(spellId, "damage_pct"), ticks);
            for (unsigned tick = 0; tick < ticks; ++tick)
                player->m_Events.AddEventAtOffset(
                    [player, spellId, where, pct, first = tick == 0]
                    {
                        if (!player->IsAlive() || !player->IsInWorld())
                            return;
                        unsigned struck = 0;
                        for (Unit* enemy :
                             Combat::Enemies(player, spellId, where, Tune("plague_of_toads_rain_radius_yards")))
                            struck += Combat::Strike(player, enemy, spellId, pct, true) ? 1 : 0;
                        if (first && struck)
                            Combat::Connected(player, spellId, struck);
                    },
                    std::chrono::milliseconds(RainMs(tick, Tune("plague_of_toads_rain_tick_seconds"))));
        }
    } // namespace

    bool Is(std::uint32_t spellId)
    {
        return RowOf(spellId, Skill) != nullptr;
    }

    std::optional<double> BasePct(std::uint32_t spellId)
    {
        if (!Is(spellId))
            return std::nullopt;
        // Only the toads that go through every enemy are the engine's hit along the line; the others are struck in
        // Cast.
        return RuneAt(spellId) == Rune::PiercingToads ? Numbers::Num(spellId, "damage_pct") : 0.0;
    }

    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets)
    {
        Rune const rune = RuneAt(spellId);
        if (!player || !Is(spellId) || rune == Rune::PiercingToads)
            return;
        if (rune == Rune::RainOfToads)
        {
            // The rain falls on the enemy the Witch Doctor has selected while it is alive, hostile, within the line's
            // reach and in her line of sight, else on the nearest the toads would have reached.
            Unit* aim = player->GetSelectedUnit();
            if (!aim || !aim->IsAlive() || !player->IsValidAttackTarget(aim) ||
                !SelectedHolds(player->GetExactDist(aim), Combat::TargetRange(spellId), player->IsWithinLOSInMap(aim)))
                aim = Nearest(player, targets);
            if (aim)
                Rain(player, spellId, aim);
            return;
        }
        Unit* nearest = Nearest(player, targets);
        if (!nearest)
            return;
        if (!Combat::Strike(player, nearest, spellId, Numbers::Num(spellId, "damage_pct")))
            return;
        // "have a {proc_chance_pct} chance to Confuse affected enemies for {duration_seconds} seconds."
        if (rune == Rune::AddlingToads && Confuses(frand(0.0f, 100.0f), Numbers::Num(spellId, "proc_chance_pct")))
            Confuse(player, nearest, Numbers::Num(spellId, "duration_seconds"));
        Combat::Connected(player, spellId, 1);
    }

    double AttackSpeed(std::uint32_t spellId, double base)
    {
        return Is(spellId) ? base * SpeedFactor(RuneAt(spellId), Tune("plague_of_toads_rain_speed_bonus")) : base;
    }
} // namespace DC::Combat::WitchDoctor::PlagueOfToads
