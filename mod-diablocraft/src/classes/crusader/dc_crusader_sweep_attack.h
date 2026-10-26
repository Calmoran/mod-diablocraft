#pragma once
// Sweep Attack's rules that need no core type, header-only so tests/crusader_sweep_attack compiles this exact code:
// which rune is which and which enemies the sweep reaches beyond the core's own cone. The production half is
// dc_crusader_sweep_attack.cpp.
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::SweepAttack
{
    enum class Rune
    {
        None,
        GatheringSweep, // the enemies caught are pulled toward you
        BlazingSweep,   // the enemies hit catch fire
        HolyShock,      // Life for each enemy hit
        TripAttack,     // a chance to stun each enemy hit
        InspiringSweep  // Armor for a while
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Gathering Sweep")
            return Rune::GatheringSweep;
        if (rune == "Blazing Sweep")
            return Rune::BlazingSweep;
        if (rune == "Holy Shock")
            return Rune::HolyShock;
        if (rune == "Trip Attack")
            return Rune::TripAttack;
        if (rune == "Inspiring Sweep")
            return Rune::InspiringSweep;
        return Rune::None;
    }

    inline double ArcRadians(double degrees)
    {
        return degrees * 3.14159265358979323846 / 180.0;
    }

    // "Sweep a mystical flail through enemies up to {radius_yards} yards before you": an enemy the core's narrower cone
    // did not take, within the reach, in the half circle in front (the caller has asked whether it stands inside the
    // arc).
    inline bool Swept(double distance, double reach, bool inArc, bool alreadyStruck)
    {
        return !alreadyStruck && inArc && reach > 0 && distance <= reach;
    }

    // Holy Shock: "Heal for {heal_per_hit_life} Life for each enemy hit": the Life of a sweep that hit `enemies`.
    inline double HealFor(double perEnemy, unsigned enemies)
    {
        return perEnemy > 0 ? perEnemy * enemies : 0.0;
    }

    // The production half (dc_crusader_sweep_attack.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The sweep's own hit: 480%, which every rune inherits (Blazing Sweep's 120% is its fire's).
    std::optional<double> BasePct(std::uint32_t spellId);
    // "Requires Weapon": a main hand that holds one.
    bool WeaponWorn(Player* player);
    // The swing resolved on `targets`: the rest of the half circle, and what the rune does to every enemy hit.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Crusader::SweepAttack
