#pragma once
// Inner Sanctuary and its five runes. The circle is module state, not a record: a
// centre, the sheet's radius and an end time, read by the damage path (Monk::TakenFactor, Monk::Absorb in
// Combat::Mitigate) when a player is hit, and ticked on the core's own event queue (Player::m_Events) at the power
// file's tick for what the runes do to whoever stands in it. The rules that need no core type are inline here, so
// tests/monk_inner_sanctuary compiles this exact code; the cast itself is dc_monk_inner_sanctuary.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>

class Player;
class Unit;

namespace DC::Combat::Monk::Sanctuary
{
    struct Zone
    {
        std::uint64_t owner = 0;   // the Monk's guid
        std::uint32_t spellId = 0; // the record cast (the skill or a rune): its numbers
        std::uint32_t map = 0, instance = 0;
        double x = 0, y = 0, z = 0, radius = 0;
        std::uint64_t until = 0; // game time, ms
    };

    // Whether a unit at (x, y) on `map`/`instance` stands in the circle at `now`: on the ground, so the height is not
    // asked, and the edge counts as in.
    inline bool Covers(Zone const& zone, std::uint32_t map, std::uint32_t instance, double x, double y,
                       std::uint64_t now)
    {
        double const dx = x - zone.x, dy = y - zone.y;
        return now < zone.until && map == zone.map && instance == zone.instance &&
               dx * dx + dy * dy <= zone.radius * zone.radius;
    }

    // "reduces all damage taken by {damage_reduction_pct}": one cut, however many circles overlap (the same power does
    // not stack with itself).
    inline double TakenFactor(double pct)
    {
        return std::clamp(1.0 - pct / 100.0, 0.0, 1.0);
    }

    // Intervene's shield "absorbs up to {absorb_life} damage": what of `damage` gets through; `left` loses what it
    // took.
    inline double Absorb(double damage, double& left)
    {
        double const taken = std::clamp(left, 0.0, std::max(0.0, damage));
        left -= taken;
        return damage - taken;
    }

    // The ticks in the circle's life: whole ticks of `tickSeconds` in `seconds` (6 s at the power file's 0.3 s is 20).
    // None for an open tick (a blank tunable).
    inline unsigned Ticks(double seconds, double tickSeconds)
    {
        return tickSeconds > 0 && seconds > 0 ? static_cast<unsigned>(std::floor(seconds / tickSeconds + 1e-9)) : 0;
    }

    // Safe Haven: "healed for {heal_per_second_life} every second", "increased by {life_per_second_share_pct} of your
    // Life per Second": each tick pays its share of a second.
    inline double HealPerTick(double perSecond, double lifePerSecond, double sharePct, double tickSeconds)
    {
        return std::max(0.0, (perSecond + lifePerSecond * sharePct / 100.0) * std::max(0.0, tickSeconds));
    }

    // Sanctified Ground, "cannot be passed by enemies": how far an enemy `distance` yards from the centre is pushed to
    // stand on the edge; 0 for one already outside.
    inline double PushYards(double distance, double radius)
    {
        return distance < radius ? radius - distance : 0.0;
    }

    // The cast side (dc_monk_inner_sanctuary.cpp).
    bool Is(std::uint32_t spellId);
    void Cast(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::Monk::Sanctuary
