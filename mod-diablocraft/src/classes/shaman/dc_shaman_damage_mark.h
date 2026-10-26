#pragma once
// A mark a Shaman's skill puts on an enemy: "the target takes N% more damage from you for S seconds". The rules need no
// core type, header-only so the harness of the skills that use it compiles this exact code; the state is
// dc_shaman_damage_mark.cpp's. One mark an enemy carries from each Shaman: a second replaces the first.
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::Shaman::DamageMark
{
    // The percent a hit of the Shaman adds on an enemy that is marked, none otherwise.
    inline double Bonus(bool marked, double pct)
    {
        return marked && pct > 0 ? pct : 0.0;
    }

    // Whether a mark that ends at `untilMs` still holds at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // `target` takes `pct` percent more damage from `player` for `seconds`.
    void Set(Player* player, Unit* target, double pct, double seconds);
    // The hit on `target` being computed: the mark of `player` raises it.
    void Multipliers(Player* player, Unit* target, DC::Combat::Factors& out);
} // namespace DC::Combat::Shaman::DamageMark
