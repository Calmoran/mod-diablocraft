#pragma once
// The rules of Death Nova's runes that need no core type, header-only so tests/necromancer_death_nova compiles this
// exact code: which rune is which, which runes strike for themselves, Unstable Compound's growing radius, Tendril
// Nova's heal and how many pulses of Blight's patch fit its time. The production half is dc_necromancer_death_nova.cpp.
#include <algorithm>
#include <cmath>
#include <string_view>

namespace DC::Combat::Necromancer::DeathNova
{
    enum class Rune
    {
        None,
        TendrilNova,
        BoneNova,
        BloodNova,
        Blight,
        UnstableCompound
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Tendril Nova")
            return Rune::TendrilNova;
        if (name == "Bone Nova")
            return Rune::BoneNova;
        if (name == "Blood Nova")
            return Rune::BloodNova;
        if (name == "Blight")
            return Rune::Blight;
        if (name == "Unstable Compound")
            return Rune::UnstableCompound;
        return Rune::None;
    }

    // The runes whose nova is the module's: Bone Nova's smaller radius and Unstable Compound's growing one. The
    // engine's hit is the skill's own radius.
    inline bool StrikesForItself(Rune rune)
    {
        return rune == Rune::BoneNova || rune == Rune::UnstableCompound;
    }

    // "Each cast increases the radius of your next Nova by {radius_yards} yards up to {max_stacks_count} times": the
    // radius of a nova cast after `stacks` earlier ones.
    inline double GrownRadius(double baseYards, double perStackYards, unsigned stacks, unsigned maxStacks)
    {
        return baseYards + std::max(0.0, perStackYards) * std::min(stacks, maxStacks);
    }

    // "heals you for {heal_pct} of your health per target hit": the Life of a nova that hit `enemies` enemies.
    inline double HealOfEnemies(double maxLife, double healPct, unsigned enemies)
    {
        return maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 * enemies : 0.0;
    }

    // Blight's patch lasts `seconds` and is felt again every `pulseSeconds`: the pulses after the first, which the cast
    // itself gives. No time or no pulse length, none.
    inline unsigned PatchPulses(double seconds, double pulseSeconds)
    {
        return seconds > 0 && pulseSeconds > 0 ? static_cast<unsigned>(std::floor(seconds / pulseSeconds + 1e-9)) : 0u;
    }
} // namespace DC::Combat::Necromancer::DeathNova
