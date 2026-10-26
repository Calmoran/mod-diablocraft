#pragma once
// Bloodlust's rules that need no core type, header-only so tests/shaman_bloodlust compiles this exact code: which rune
// is which, what each rune adds to the buff, how far a kill may extend it and whether it still holds. The production
// half is dc_shaman_bloodlust.cpp.
#include <algorithm>
#include <cstdint>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::Bloodlust
{
    enum class Rune
    {
        None,
        Heroism,         // also reduces the damage taken
        AncestralFury,   // also increases the damage dealt
        ThirstForBattle, // each kill extends the buff
        ElementalFervor, // more Maelstrom generated
        PrimalRage       // cooldown reduction
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Heroism")
            return Rune::Heroism;
        if (name == "Ancestral Fury")
            return Rune::AncestralFury;
        if (name == "Thirst for Battle")
            return Rune::ThirstForBattle;
        if (name == "Elemental Fervor")
            return Rune::ElementalFervor;
        if (name == "Primal Rage")
            return Rune::PrimalRage;
        return Rune::None;
    }

    // What a rune adds to the buff beyond the attack and movement speed every Bloodlust gives.
    enum class Adds
    {
        Nothing,
        DamageReduction,
        DamageBonus,
        MaelstromGeneration,
        CooldownReduction
    };

    inline Adds AddsOf(Rune rune)
    {
        switch (rune)
        {
            case Rune::Heroism:
                return Adds::DamageReduction;
            case Rune::AncestralFury:
                return Adds::DamageBonus;
            case Rune::ElementalFervor:
                return Adds::MaelstromGeneration;
            case Rune::PrimalRage:
                return Adds::CooldownReduction;
            default:
                return Adds::Nothing;
        }
    }

    // Thirst for Battle: "Each kill during Bloodlust extends it by {extend} seconds, up to {cap} extra seconds": the
    // milliseconds a kill adds when `extendedMs` have been added already.
    inline std::uint64_t Extension(Rune rune, std::uint64_t extendedMs, double extendSeconds, double capSeconds)
    {
        if (rune != Rune::ThirstForBattle || extendSeconds <= 0 || capSeconds <= 0)
            return 0;
        auto const cap = std::uint64_t(capSeconds * 1000.0), step = std::uint64_t(extendSeconds * 1000.0);
        return extendedMs >= cap ? 0 : std::min(step, cap - extendedMs);
    }

    // Whether a buff that ends at `untilMs` still holds at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // The production half (dc_shaman_bloodlust.cpp), called from dc_shaman.cpp.
    bool Is(std::uint32_t spellId);
    // A cast of `spellId` resolved on `targets` (the Shaman and the allies in reach): Bloodlust starts on every player
    // among them.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    void RegisterScripts();
} // namespace DC::Combat::Shaman::Bloodlust
