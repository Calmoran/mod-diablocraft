#pragma once
// Shadow Power's rules that need no core type, header-only so tests/demon_hunter_shadow_power compiles this exact code:
// which rune is which and the Life per Hit the skill gives. The production half is dc_demon_hunter_shadow_power.cpp.
#include <cstdint>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::ShadowPower
{
    enum class Rune
    {
        None,
        NightBane,      // the enemies around are slowed
        ShadowGlide,    // more movement speed while it lasts
        Gloom,          // less damage taken while it lasts
        WellOfDarkness, // a cheaper cast (a sheet number)
        BloodMoon       // twice the Life per Hit
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Night Bane")
            return Rune::NightBane;
        if (name == "Shadow Glide")
            return Rune::ShadowGlide;
        if (name == "Gloom")
            return Rune::Gloom;
        if (name == "Well of Darkness")
            return Rune::WellOfDarkness;
        if (name == "Blood Moon")
            return Rune::BloodMoon;
        return Rune::None;
    }

    // "gaining {heal_per_hit_life} Life per Hit ... Life per Hit gained is increased by {life_per_kill_share_pct} of
    // your Life per Kill": the power file's Life On Hit Base is `healingShare` of D3's Healing table at the player's
    // level (`healingAtLevel`), and the Life per Kill adds its share; Blood Moon "doubles the total amount of Life per
    // Hit gained" (its own Life On Hit Bonus and Life on Kill Bonus equal the base ones).
    inline double LifePerHit(Rune rune, double healingShare, double healingAtLevel, double killSharePct,
                             double lifePerKill)
    {
        double const base = healingShare * healingAtLevel + killSharePct / 100.0 * lifePerKill;
        return rune == Rune::BloodMoon ? 2.0 * base : base;
    }

    // The production half (dc_demon_hunter_shadow_power.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The cast resolved: the shadows are drawn in.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::DemonHunter::ShadowPower
