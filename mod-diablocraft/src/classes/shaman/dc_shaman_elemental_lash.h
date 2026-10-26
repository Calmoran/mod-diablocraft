#pragma once
// Elemental Lash's rules that need no core type, header-only so tests/shaman_elemental_lash compiles this exact code:
// which rune is which, where the cast's own hit takes its number from, the chance of a Lava Surge and the Maelstrom
// Stonewhip adds for a crowd. The production half is dc_shaman_elemental_lash.cpp.
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Shaman::ElementalLash
{
    enum class Rune
    {
        None,
        SearingLash, // Fire, and the enemies hit are Burning
        LavaSurge,   // Fire; an enemy hit may make the next Lava Burst free
        Stonewhip,   // pushes the enemies back, and generates more against a crowd, Physical
        FrostLash,   // chills the enemies hit, Cold
        ThunderLash  // a longer cone, Lightning
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Searing Lash")
            return Rune::SearingLash;
        if (name == "Lava Surge")
            return Rune::LavaSurge;
        if (name == "Stonewhip")
            return Rune::Stonewhip;
        if (name == "Frost Lash")
            return Rune::FrostLash;
        if (name == "Thunder Lash")
            return Rune::ThunderLash;
        return Rune::None;
    }

    // Whether the rune states its hit as a "hit" number beside a burn (Searing Lash) where every other rune states one
    // plain number or inherits the skill's.
    inline bool HitIsTagged(Rune rune)
    {
        return rune == Rune::SearingLash;
    }

    // A chance of `chancePct` percent that comes up on `roll` (0 to 1).
    inline bool Procs(double roll, double chancePct)
    {
        return chancePct > 0 && roll * 100.0 < chancePct;
    }

    // Stonewhip: "Generates {gain_resource} extra Maelstrom when it hits {nearby_enemy_count} or more enemies".
    inline double CrowdGain(unsigned enemies, double needed, double gain)
    {
        return needed > 0 && gain > 0 && double(enemies) >= needed ? gain : 0.0;
    }

    // Stonewhip pushes back everything but an elite or a boss.
    inline bool Pushes(bool elite)
    {
        return !elite;
    }

    // The production half (dc_shaman_elemental_lash.cpp), called from dc_shaman.cpp and the Maelstrom file.
    bool Is(std::uint32_t spellId);
    // The weapon damage percent the cast's own hit of an Elemental Lash record deals when the plain loader rule would
    // read the wrong one; nullopt for the rest.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A hit of the skill landed on `target`: Searing Lash's burn, Lava Surge's chance, Stonewhip's push, Frost Lash's
    // chill.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The cast connected on `enemies` enemies: Stonewhip's extra Maelstrom.
    void Connected(Player* player, std::uint32_t spellId, unsigned enemies);
} // namespace DC::Combat::Shaman::ElementalLash
