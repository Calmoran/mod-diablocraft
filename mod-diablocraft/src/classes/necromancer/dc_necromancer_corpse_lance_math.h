#pragma once
// The rules of Corpse Lance's runes that need no core type, header-only so tests/necromancer_corpse_lance compiles this
// exact code: which rune is which, whether a corpse is within reach, which search the corpse is taken from, whether a
// lance ricochets, what Shredding Splinters' stacks are worth and whether Brittle Touch still holds. The production
// half is dc_necromancer_corpse_lance.cpp; the stacks themselves are dc_necromancer_buffs.h.
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace DC::Combat::Necromancer::CorpseLance
{
    enum class Rune
    {
        None,
        Ricochet,
        BrittleTouch,
        BloodLance,
        VisceralImpact,
        ShreddingSplinters
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Ricochet")
            return Rune::Ricochet;
        if (name == "Brittle Touch")
            return Rune::BrittleTouch;
        if (name == "Blood Lance")
            return Rune::BloodLance;
        if (name == "Visceral Impact")
            return Rune::VisceralImpact;
        if (name == "Shredding Splinters")
            return Rune::ShreddingSplinters;
        return Rune::None;
    }

    // The runes whose engine hit is not the skill's number: Blood Lance states the additional lance's 525% as its own,
    // so the main lance keeps the skill's.
    inline bool KeepsTheSkillsHit(Rune rune)
    {
        return rune == Rune::BloodLance;
    }

    // "projectiles from nearby corpses": a lance may fly when a corpse lies near the Necromancer or near the target.
    inline bool CorpseInReach(std::size_t nearTheNecromancer, std::size_t nearTheTarget)
    {
        return nearTheNecromancer > 0 || nearTheTarget > 0;
    }

    // The corpse is taken from near the target when there is one there, else from near the Necromancer.
    inline bool TakeNearTheTarget(std::size_t nearTheTarget)
    {
        return nearTheTarget > 0;
    }

    // "has a {proc_chance_pct} chance to ricochet to one additional target": for a roll of `roll` (0 to 100). No chance
    // or no reach to the next enemy, no ricochet.
    inline bool Ricochets(double roll, double chancePct, double reachYards)
    {
        return chancePct > 0 && reachYards > 0 && roll < chancePct;
    }

    // "Stacks up to {max_stacks_count} times": what `stacks` stacks of `perStack` are worth.
    inline double StackedPct(double perStack, unsigned stacks, unsigned maxStacks)
    {
        return perStack > 0 ? perStack * std::min(stacks, maxStacks) : 0.0;
    }

    // "for {duration_seconds} seconds": whether a mark that runs to `untilMs` still holds at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }
} // namespace DC::Combat::Necromancer::CorpseLance
