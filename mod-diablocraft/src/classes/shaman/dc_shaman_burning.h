#pragma once
// Burning: an enemy is Burning while a Fire damage over time or burn of the Shaman's is on it. The rule needs no core type,
// header-only so tests/shaman_flame_shock compiles this exact code; the state is dc_shaman_burning.cpp's.
#include <algorithm>
#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::Shaman::Burning
{
    // When the burn ends after `seconds` more from `nowMs`, given it ended at `untilMs` (0 for none): a second burn extends it and
    // never shortens it. Nothing for no seconds.
    inline std::uint64_t Until(std::uint64_t untilMs, std::uint64_t nowMs, double seconds)
    {
        return seconds > 0 ? std::max(untilMs, nowMs + std::uint64_t(seconds * 1000.0)) : untilMs;
    }

    // Whether a burn that ends at `untilMs` still holds at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // `target` is Burning, from `player`, for `seconds` more (dc_shaman_burning.cpp).
    void Ignite(Player* player, Unit* target, double seconds);
    // A burn of `spellId` on `target`: `totalPct` of weapon damage over `seconds` in ticks of `tickSeconds`, and the enemy Burning for as long.
    // Call of Flame makes it last longer (the same damage each second for the longer time). Nothing for no seconds or tick.
    void Burn(Player* player, Unit* target, std::uint32_t spellId, double totalPct, double seconds, double tickSeconds);
    // Whether `target` is Burning from `player` now.
    bool Is(Player const* player, Unit const* target);
} // namespace DC::Combat::Shaman::Burning
