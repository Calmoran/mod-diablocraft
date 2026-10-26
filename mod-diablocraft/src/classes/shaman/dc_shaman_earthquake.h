#pragma once
// The Shaman's Earthquake rules that need no core type, header-only so tests/shaman_earthquake compiles this exact
// code: which rune is which, whose damage the ticks deal, who stands inside, the chill, the freeze and the bonuses of
// Magma Chamber and Earth Shock. The production half is dc_shaman_earthquake.cpp.
#include "../../combat/dc_damage_buckets.h"
#include "../../combat/dc_periodic_strike.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string_view>

class Player;
struct Position;
class Unit;

namespace DC::Combat::Shaman::Earthquake
{
    enum class Rune
    {
        None,
        Aftershock,     // the ground erupts when it ends, Physical
        RollingQuake,   // centred on the Shaman, smaller, moves with them, Physical
        MagmaChamber,   // enemies inside take more damage from Lava Burst, Fire
        FrozenTundra,   // chills the enemies inside and freezes them now and then, Cold
        ThunderingEarth // lightning on a few random enemies inside instead of the whole area, Lightning
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Aftershock")
            return Rune::Aftershock;
        if (name == "Rolling Quake")
            return Rune::RollingQuake;
        if (name == "Magma Chamber")
            return Rune::MagmaChamber;
        if (name == "Frozen Tundra")
            return Rune::FrozenTundra;
        if (name == "Thundering Earth")
            return Rune::ThunderingEarth;
        return Rune::None;
    }

    // Whether the rune states the damage the ticks deal (Thundering Earth's 3000) where every other rune's own
    // `damage_pct` is not the ticks' (Aftershock's is its eruption) or is absent and the skill's is the ticks'.
    inline bool OwnsTickDamage(Rune rune)
    {
        return rune == Rune::ThunderingEarth;
    }

    // Rolling Quake moves with the Shaman; every other Earthquake stays where it was cast.
    inline bool Follows(Rune rune)
    {
        return rune == Rune::RollingQuake;
    }

    // Thundering Earth strikes a few random enemies a tick; every other rune strikes all that stand inside.
    inline bool StrikesAll(Rune rune)
    {
        return rune != Rune::ThunderingEarth;
    }

    // How many enemies a tick strikes of `inside` standing in the area when it strikes `most`.
    inline std::size_t Struck(Rune rune, std::size_t inside, std::size_t most)
    {
        return StrikesAll(rune) ? inside : std::min(inside, most);
    }

    // Whether the point (`ex`, `ey`) stands inside the area of `radius` yards about (`cx`, `cy`).
    inline bool Inside(double cx, double cy, double ex, double ey, double radius)
    {
        return radius > 0 && std::hypot(ex - cx, ey - cy) <= radius;
    }

    // Frozen Tundra: the chill lasts through the next tick, so an enemy that stays inside is chilled all the while.
    inline double ChillSeconds(double tickSeconds)
    {
        return tickSeconds > 0 ? tickSeconds * 2.0 : 0.0;
    }

    // Frozen Tundra: "Frozen for {freeze_duration_seconds} second every {interval_seconds} seconds": whether a freeze
    // is due at `nowMs` given the last one at `lastMs` (0 for none yet).
    inline bool FreezeDue(std::uint64_t nowMs, std::uint64_t lastMs, double intervalSeconds)
    {
        return intervalSeconds > 0 && (lastMs == 0 || nowMs >= lastMs + std::uint64_t(intervalSeconds * 1000.0));
    }

    // Magma Chamber: "Enemies inside take {damage_taken_pct} more damage from Lava Burst": the percent a Lava Burst hit
    // adds.
    inline double MagmaBonus(Rune rune, bool inside, double pct)
    {
        return rune == Rune::MagmaChamber && inside && pct > 0 ? pct : 0.0;
    }

    // Earth Shock: "plus {gain_resource} more if the target is inside your Earthquake".
    inline double EarthShockGain(bool inside, double gain)
    {
        return inside && gain > 0 ? gain : 0.0;
    }

    // The production half (dc_shaman_earthquake.cpp), called from dc_shaman.cpp and the Flame Shock file.
    bool Is(std::uint32_t spellId);
    // The cast of an Earthquake resolved at `center`: the area starts, moving the one the Shaman had.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    // Whether `target` stands inside the Earthquake `player` has now, of any rune.
    bool Inside(Player* player, Unit const* target);
    // The hit of `spellId` on `target` being computed: Magma Chamber's bonus to Lava Burst.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
} // namespace DC::Combat::Shaman::Earthquake
