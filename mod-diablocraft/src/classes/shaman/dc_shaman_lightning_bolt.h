#pragma once
// Lightning Bolt's rules that need no core type, header-only so tests/shaman_lightning_bolt compiles this exact code: which rune
// is which, the chance of an Overload, the Maelstrom the runes add and the damage the Earthen Spike mark adds. The production half is
// dc_shaman_lightning_bolt.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Shaman::LightningBolt
{
    enum class Rune
    {
        None,
        Overload,     // a cast may strike the target again, Lightning
        LavaBeam,     // a beam through every enemy in a line, Fire
        Hailstone,    // chills, and generates more against a chilled enemy, Cold
        EarthenSpike, // marks the target to take more Physical damage from the Shaman, Physical
        Stormcaller   // generates more, and more again on a critical hit, Lightning
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Overload")
            return Rune::Overload;
        if (name == "Lava Beam")
            return Rune::LavaBeam;
        if (name == "Hailstone")
            return Rune::Hailstone;
        if (name == "Earthen Spike")
            return Rune::EarthenSpike;
        if (name == "Stormcaller")
            return Rune::Stormcaller;
        return Rune::None;
    }

    // Whether the skill hands the loader the hit of a record of `rune` itself. All of them: Earthen Spike states a duration beside its
    // damage, and the loader (dc_combat.cpp, DamageWaits) would read that as a damage that waits and load the record with none.
    inline bool ClaimsHit(Rune)
    {
        return true;
    }

    // A chance of `chancePct` percent that comes up on `roll` (0 to 1).
    inline bool Overloads(double roll, double chancePct)
    {
        return chancePct > 0 && roll * 100.0 < chancePct;
    }

    // Hailstone: "Generates {gain_resource} extra Maelstrom against Chilled enemies".
    inline double ChilledGain(bool chilled, double gain)
    {
        return chilled && gain > 0 ? gain : 0.0;
    }

    // Stormcaller: "Critical hits generate {gain_resource} more".
    inline double CriticalGain(bool critical, double gain)
    {
        return critical && gain > 0 ? gain : 0.0;
    }

    // Earthen Spike: "The target takes {damage_taken_pct} more Physical damage from you": the percent a hit of the Shaman adds, none
    // for another element or an enemy that is not marked.
    inline double MarkBonus(bool marked, bool physical, double pct)
    {
        return marked && physical && pct > 0 ? pct : 0.0;
    }

    // Whether a mark that ends at `untilMs` still holds at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // The production half (dc_shaman_lightning_bolt.cpp), called from dc_shaman.cpp.
    bool Is(std::uint32_t spellId);
    // The weapon damage percent the cast's own hit of a Lightning Bolt record deals: the record's `damage_pct`, its own or its skill's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A hit of the skill landed on `target` (`critical` when it was a critical hit): Overload's second strike, Hailstone's chill,
    // Earthen Spike's mark, Stormcaller's Maelstrom.
    void Landed(Player* player, Unit* target, std::uint32_t spellId, bool critical);
    // The hit of `spellId` on `target` being computed: Earthen Spike's mark raises a Physical one.
    void Multipliers(Player* player, Unit* target, std::uint32_t spellId, DC::Combat::Factors& out);
} // namespace DC::Combat::Shaman::LightningBolt
