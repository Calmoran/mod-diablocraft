#pragma once
// The rules the follower skills share, with no core include so tests/follower_skills compiles them alone: how far a number scales
// with the follower's main stat, which tiers are open and which skills are on, the cooldowns and the arithmetic of a hit, a heal and
// a pick. dc_follower_skills.cpp is the player and creature side around them.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string_view>

namespace DC::Classes::Follower
{
// How far the follower's main stat is up its scale: 0 at none and 1 at `cap` and above ("reaching the maximum at 25,000 main stat").
inline double MainStatShare(double mainStat, double cap)
{
    return cap > 0 ? std::clamp(mainStat / cap, 0.0, 1.0) : 0.0;
}

// A number that runs from `low` (no main stat) to `high` (the cap) is `low` when `high` is below it: the sheet leaves a number that
// does not scale with no maximum.
inline double Scaled(double low, double high, double share)
{
    return high > low ? low + (high - low) * std::clamp(share, 0.0, 1.0) : low;
}

// A tier opens at the follower's level (the player's) reaching the tier's own.
inline bool TierOpen(unsigned level, unsigned tierLevel)
{
    return level >= tierLevel;
}

// A skill is on when its tier is open and it is the pick of that tier, or the follower wears the relic that gives it every skill.
inline bool Active(bool picked, bool allSkills, bool tierOpen)
{
    return tierOpen && (picked || allSkills);
}

// A skill's cooldown in milliseconds; the relics that halve the cooldown of every follower skill give `halved`.
inline std::uint64_t CooldownMs(double seconds, bool halved)
{
    return seconds > 0 ? std::uint64_t(std::llround(seconds * (halved ? 0.5 : 1.0) * 1000.0)) : 0;
}

inline bool Ready(std::uint64_t nowMs, std::uint64_t readyAtMs)
{
    return nowMs >= readyAtMs;
}

// Inspire's "N% generated": the factor on what the player's skills generate of a resource, 1 for no percent (a negative one is no scale).
inline double GeneratedFactor(double pct)
{
    return std::max(pct, 0.0) / 100.0 + 1.0;
}

// A fatal blow: the Life the player has left is not more than the damage.
inline bool Fatal(double health, double damage)
{
    return damage > 0 && damage >= health;
}

// Whether a unit with `life` of `maxLife` is below `belowPct` percent of it (a unit with no Life is not asked to be healed).
inline bool Below(double life, double maxLife, double belowPct)
{
    return life > 0 && maxLife > 0 && life * 100.0 < maxLife * belowPct;
}

// A heal written as a share of D3's Healing table at the level (Table(Healing, Level) in the power files).
inline double TableHeal(double share, double tableAtLevel)
{
    return share > 0 && tableAtLevel > 0 ? share * tableAtLevel : 0.0;
}

// A heal written as a percent of the maximum Life.
inline double LifeHeal(double maxLife, double pct)
{
    return maxLife > 0 && pct > 0 ? maxLife * pct / 100.0 : 0.0;
}

// A hit of `pct` percent of the follower's weapon damage: the swing's range at `roll` (0 to 1).
inline double WeaponHit(double pct, double swingMin, double swingMax, double roll)
{
    double const swing = swingMin + (std::max(swingMax, swingMin) - swingMin) * std::clamp(roll, 0.0, 1.0);
    return pct > 0 && swing > 0 ? pct / 100.0 * swing : 0.0;
}

// The whole pulses that fell due when `diffMs` was added to a clock that counts toward `periodMs`; the clock keeps the rest.
inline unsigned Pulses(double& clockMs, double diffMs, double periodMs)
{
    if (periodMs <= 0)
        return 0;
    clockMs += std::max(0.0, diffMs);
    unsigned due = 0;
    while (clockMs >= periodMs)
    {
        clockMs -= periodMs;
        ++due;
    }
    return due;
}

// The choice a pick names in a tier of two skills: "1" or "2", or a skill's id. -1 when it is neither.
inline int ChoiceOf(std::string_view text, std::string_view first, std::string_view second)
{
    if (text == "1" || (!text.empty() && text == first))
        return 0;
    if (text == "2" || (!text.empty() && text == second))
        return 1;
    return -1;
}

// A critical hit: the sheet's Critical Hit Damage as the multiplier of the hit.
inline double CritMultiplier(double critDamagePct)
{
    return 1.0 + std::max(0.0, critDamagePct) / 100.0;
}

// A chance in percent that comes up on `roll` (0 to 1): a critical hit, a proc.
inline bool Rolls(double roll, double chancePct)
{
    return chancePct > 0 && roll * 100.0 < chancePct;
}

// "N% more damage": the multiplier of a hit.
inline double MoreDamage(double pct)
{
    return 1.0 + std::max(0.0, pct) / 100.0;
}

// Whether a timed effect (a shield, a cloud, a bonus) that runs until `untilMs` still holds at `nowMs`.
inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
{
    return nowMs < untilMs;
}

// Whether the point (px, py) is within `halfWidth` yards of the segment from (ax, ay) to (bx, by): who a shot that pierces along that
// line hits.
inline bool OnLine(double ax, double ay, double bx, double by, double px, double py, double halfWidth)
{
    double const dx = bx - ax, dy = by - ay, length2 = dx * dx + dy * dy;
    double const along = length2 > 0 ? std::clamp(((px - ax) * dx + (py - ay) * dy) / length2, 0.0, 1.0) : 0.0;
    double const nx = ax + along * dx - px, ny = ay + along * dy - py;
    return halfWidth > 0 && nx * nx + ny * ny <= halfWidth * halfWidth;
}

// The enemy a bolt of a volley goes to, when `available` enemies stand in reach: the bolts take them in turn, the first again when the
// enemies run out.
inline unsigned BoltTarget(unsigned bolt, std::size_t available)
{
    return available ? unsigned(bolt % available) : 0;
}

// A pool that deals `totalPct` over `seconds`, ticking every `tickSeconds`: what each tick deals.
inline double PerTick(double totalPct, double seconds, double tickSeconds)
{
    return totalPct > 0 && seconds > 0 && tickSeconds > 0 ? totalPct * std::min(tickSeconds, seconds) / seconds : 0.0;
}

// "Reduces damage by pct% from ranged attacks": the multiplier of a blow, 1 for a melee blow.
inline double RangedFactor(double reductionPct, bool melee)
{
    return melee ? 1.0 : 1.0 - std::clamp(reductionPct, 0.0, 100.0) / 100.0;
}

// "Increases your highest static elemental damage bonus by pct%": what is added to that bonus.
inline double Amplified(double highest, double pct)
{
    return highest > 0 && pct > 0 ? highest * pct / 100.0 : 0.0;
}

// The place of the largest of `count` values (the first of equals; 0 when there are none).
inline std::size_t Highest(double const* values, std::size_t count)
{
    std::size_t best = 0;
    for (std::size_t i = 1; i < count; ++i)
        if (values[i] > values[best])
            best = i;
    return best;
}

// Whether the place an effect was laid at, a map and an instance of it, is the place now: a pool or a cloud does not follow its owner to
// another floor or another run of the same map.
inline bool SamePlace(std::uint32_t map, std::uint32_t instance, std::uint32_t nowMap, std::uint32_t nowInstance)
{
    return map == nowMap && instance == nowInstance;
}

// Whether a unit at `distance` yards is within `range` of the follower.
inline bool InRange(double distance, double range)
{
    return range > 0 && distance <= range;
}

} // namespace DC::Classes::Follower
