#pragma once
// Multishot's rules that need no core type, header-only so tests/demon_hunter_multishot compiles this exact code: which
// rune is which, how long a chill's critical hit window lasts, which hits Suppression Fire knocks back, when each of
// Arsenal's rockets leaves. The production half is dc_demon_hunter_multishot.cpp.
#include "dc_demon_hunter_pick.h"

#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::Multishot
{
    enum class Rune
    {
        None,
        FullBroadside,  // more damage (the record's)
        WindChill,      // enemies hit are chilled and crit more easily
        Arsenal,        // rockets at nearby enemies, Fire
        FireAtWill,     // a cheaper cost, Lightning (the record's)
        SuppressionFire // the first enemies hit are knocked back
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Full Broadside")
            return Rune::FullBroadside;
        if (name == "Wind Chill")
            return Rune::WindChill;
        if (name == "Arsenal")
            return Rune::Arsenal;
        if (name == "Fire at Will")
            return Rune::FireAtWill;
        if (name == "Suppression Fire")
            return Rune::SuppressionFire;
        return Rune::None;
    }

    // The game time (ms) a window of `seconds` that opens at `nowMs` closes at; none for no seconds.
    inline std::uint64_t ClosesAt(std::uint64_t nowMs, double seconds)
    {
        return nowMs + std::uint64_t(seconds > 0 ? seconds * 1000.0 : 0.0);
    }

    // Whether a window that closes at `closesMs` is open at `nowMs`.
    inline bool Open(std::uint64_t closesMs, std::uint64_t nowMs)
    {
        return nowMs < closesMs;
    }

    // "Knockback the first {target_count} enemies hit": whether the hit in `place` among the cast's enemies, nearest
    // first (1 the first), is one. No place (a hit outside a cast's enemies), never.
    inline bool KnockedBack(unsigned place, unsigned count)
    {
        return place >= 1 && place <= count;
    }

    // "launch {projectile_count} rockets": the milliseconds after the cast the `index`th rocket leaves, the first after
    // the warmup and the rest a rocket interval apart.
    inline std::uint32_t RocketDelayMs(unsigned index, double warmupSeconds, double intervalSeconds)
    {
        double const seconds =
            (warmupSeconds > 0 ? warmupSeconds : 0.0) + (intervalSeconds > 0 ? intervalSeconds : 0.0) * index;
        return std::uint32_t(seconds * 1000.0 + 0.5);
    }

    // The production half (dc_demon_hunter_multishot.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // Arsenal's volley deals the skill's own damage, not its rockets' (the rune states the rockets').
    std::optional<double> BasePct(std::uint32_t spellId);
    // The volley resolved: Arsenal's rockets are on their way.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // A hit of the volley landed on `target`: Wind Chill's chill, Suppression Fire's knockback.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The critical hit chance, in percent, Wind Chill puts on `target` for every attacker.
    double CritBonus(Unit* target);
} // namespace DC::Combat::DemonHunter::Multishot
