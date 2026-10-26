#pragma once
// Strafe's rules that need no core type, header-only so tests/demon_hunter_strafe compiles this exact code: which rune
// is which, how many shots a second of attack speed holds, which enemy a shot goes to, when Icy Trail drops a patch,
// what a patch tick and a critical hit's extra are worth. The shots' timing, damage and cost share are Rapid Fire's
// arithmetic (both channels state their numbers the same way); the production half is dc_demon_hunter_strafe.cpp.
#include "dc_demon_hunter_clock.h"
#include "dc_demon_hunter_dot.h"
#include "dc_demon_hunter_pick.h"
#include "dc_demon_hunter_rapid_fire.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::DemonHunter::Strafe
{
    enum class Rune
    {
        None,
        Demolition,     // grenades that explode round the enemy, Fire, at half the rate
        IcyTrail,       // patches of ice left behind, Cold
        RocketStorm,    // homing rockets besides the shots, Fire
        DriftingShadow, // faster while strafing, Lightning
        StingingSteel   // knives that hit harder on a critical hit
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Demolition")
            return Rune::Demolition;
        if (name == "Icy Trail")
            return Rune::IcyTrail;
        if (name == "Rocket Storm")
            return Rune::RocketStorm;
        if (name == "Drifting Shadow")
            return Rune::DriftingShadow;
        if (name == "Stinging Steel")
            return Rune::StingingSteel;
        return Rune::None;
    }

    // The shots a second of attack speed holds: the skill's, and Demolition's grenades at their own fraction of it.
    inline double ShotsPerAttack(Rune rune, double base, double demolitionFraction)
    {
        return rune == Rune::Demolition ? base * demolitionFraction : base;
    }

    // "while moving at {movement_speed_pct} of normal movement speed": the share of normal speed a slow takes away.
    inline double SlowPct(double speedPct)
    {
        return std::clamp(100.0 - speedPct, 0.0, 100.0);
    }

    // The seconds a refreshed slow holds: two refreshes, so one late check does not let go of it.
    inline double HoldSeconds(double refreshSeconds)
    {
        return refreshSeconds > 0 ? 2.0 * refreshSeconds : 0.0;
    }

    // Icy Trail: whether the Demon Hunter, `moved` yards from where the last patch lies, drops another. No distance,
    // never.
    inline bool DropsPatch(double moved, double dropYards)
    {
        return dropYards > 0 && moved >= dropYards;
    }

    // "deals {damage_pct} weapon damage over {dot_duration_seconds} seconds": what one tick of a patch carries.
    inline double PatchTickPct(double totalPct, double seconds, double tickSeconds)
    {
        return Dot::TickPct(totalPct, Dot::Ticks(seconds, tickSeconds));
    }

    // "knives ... that deal an extra {damage_bonus_pct} damage on Critical Hits": the extra strike of a shot that
    // carried `shotPct`.
    inline double CritExtraPct(double shotPct, double bonusPct)
    {
        return std::max(0.0, shotPct) * std::max(0.0, bonusPct) / 100.0;
    }

    // The production half (dc_demon_hunter_strafe.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // No hit of the cast itself: the channel's shots are the damage.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The channel began (Combat::ResolveCast): the first shot fires and the slow is on.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // A shot of `spellId` landed on `target` (`critical` when it was a critical hit): Stinging Steel's extra.
    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical);
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::Strafe
