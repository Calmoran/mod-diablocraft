#pragma once
// Elemental Arrow's rules that need no core type, header-only so tests/demon_hunter_elemental_arrow compiles this exact
// code: which rune is which, how far a slow projectile has flown, what a shock and a tentacle's life cost or give. The
// production half is dc_demon_hunter_elemental_arrow.cpp.
#include "dc_demon_hunter_clock.h"
#include "dc_demon_hunter_dot.h"

#include <algorithm>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::ElementalArrow
{
    enum class Rune
    {
        None,
        FrostArrow,      // chills, then splits into a cone of arrows, Cold
        BallLightning,   // a slow ball that shocks every enemy near it as it goes, Lightning
        ImmolationArrow, // explodes into burning ground, Fire
        NetherTentacles, // a slow tentacle that strikes near it as it goes and heals, Physical
        LightningBolts   // a critical hit stuns, Lightning
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Frost Arrow")
            return Rune::FrostArrow;
        if (name == "Ball Lightning")
            return Rune::BallLightning;
        if (name == "Immolation Arrow")
            return Rune::ImmolationArrow;
        if (name == "Nether Tentacles")
            return Rune::NetherTentacles;
        if (name == "Lightning Bolts")
            return Rune::LightningBolts;
        return Rune::None;
    }

    // The yards a projectile that flies `yardsPerSecond` has covered `elapsedMs` after it left, stopping at `travel`.
    inline double Flown(double yardsPerSecond, double elapsedMs, double travel)
    {
        if (yardsPerSecond <= 0 || elapsedMs <= 0 || travel <= 0)
            return 0.0;
        return std::min(travel, yardsPerSecond * elapsedMs / 1000.0);
    }

    // Whether a projectile that has covered `flown` yards of its `travel` has reached the end of its path.
    inline bool Arrived(double flown, double travel)
    {
        return flown >= travel;
    }

    // Ball Lightning: the rune's weapon damage is for the two shocks a tick of the ball makes on each enemy, so one
    // carries `shocks` parts of it. No shocks, none.
    inline double ShockPct(double damagePct, unsigned shocks)
    {
        return shocks ? damagePct / shocks : 0.0;
    }

    // Nether Tentacles: "returns {heal_pct} of your maximum Life for each enemy hit": the Life of `hits` enemies
    // struck.
    inline double TentacleHeal(double maxLife, double healPct, unsigned hits)
    {
        return maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 * hits : 0.0;
    }

    // Immolation Arrow: the damage of one tick of the burning ground, whose total is spread over its duration.
    inline double GroundTickPct(double totalPct, double seconds, double tickSeconds)
    {
        return Dot::TickPct(totalPct, Dot::Ticks(seconds, tickSeconds));
    }

    // The production half (dc_demon_hunter_elemental_arrow.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The arrow's own hit is each rune's own damage; Ball Lightning's and Nether Tentacles' are done by the projectile
    // as it flies, not by the arrow that sends it.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A hit of the arrow landed on `target` (`critical` when it was a critical hit): Frost Arrow's chill and split,
    // Immolation Arrow's fire, Lightning Bolts' stun.
    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical);
    // The cast resolved: Ball Lightning's ball and Nether Tentacles' tentacle set out toward the enemy aimed at.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::ElementalArrow
