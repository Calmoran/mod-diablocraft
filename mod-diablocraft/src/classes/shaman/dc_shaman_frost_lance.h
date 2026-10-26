#pragma once
// Frost Lance's rules that need no core type, header-only so tests/shaman_frost_lance compiles this exact code: which
// rune is which, which runes keep the skill's hit, the Icefury stacks and their damage, the cone Shattering Lance's
// shards fly in, Glacial Boulder's freeze cooldown and which hits burn. The production half is
// dc_shaman_frost_lance.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;

namespace DC::Combat::Shaman::FrostLance
{
    enum class Rune
    {
        None,
        Icefury,         // Cold damage stacks on the Shaman for each chilled enemy hit
        ShatteringLance, // stops on the first enemy and sends shards behind it, Cold
        FrostfireBolt,   // chilled enemies it hits also burn, Fire
        GlacialBoulder,  // stops on the first enemy and freezes it, Physical
        Thunderhail      // each enemy pierced releases an arc, Lightning
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Icefury")
            return Rune::Icefury;
        if (name == "Shattering Lance")
            return Rune::ShatteringLance;
        if (name == "Frostfire Bolt")
            return Rune::FrostfireBolt;
        if (name == "Glacial Boulder")
            return Rune::GlacialBoulder;
        if (name == "Thunderhail")
            return Rune::Thunderhail;
        return Rune::None;
    }

    // Whether the cast's own hit is the skill's number although the plain loader rule would read another: the rune states a
    // `damage_pct` of its own that is its shards, burn or arc, or a duration (Icefury's) that the loader reads as a damage
    // that waits. The lance still hits for the skill's.
    inline bool HitIsSkills(Rune rune)
    {
        return rune == Rune::ShatteringLance || rune == Rune::FrostfireBolt || rune == Rune::Thunderhail ||
               rune == Rune::Icefury;
    }

    // Icefury: the stacks after `gained` more, to at most `maxStacks`.
    inline unsigned Stacked(unsigned stacks, unsigned gained, unsigned maxStacks)
    {
        return std::min(stacks + gained, maxStacks);
    }

    // Icefury: the percent more Cold damage the stacks give.
    inline double IcefuryBonus(unsigned stacks, double perStackPct)
    {
        return perStackPct > 0 ? double(stacks) * perStackPct : 0.0;
    }

    // Whether a stack state that ends at `untilMs` still holds at `nowMs`.
    inline bool Holds(std::uint64_t nowMs, std::uint64_t untilMs)
    {
        return nowMs < untilMs;
    }

    // Shattering Lance: whether the point (`px`, `py`) lies in the cone behind the first enemy, which stands at (`fx`,
    // `fy`) on the line from the caster at (`cx`, `cy`): the cone opens away from the caster, `degrees` wide, `length`
    // long. The first enemy itself is not in it.
    inline bool BehindInCone(double cx, double cy, double fx, double fy, double px, double py, double length,
                             double degrees)
    {
        double const ax = fx - cx, ay = fy - cy, vx = px - fx, vy = py - fy;
        double const axisLength = std::sqrt(ax * ax + ay * ay), distance = std::sqrt(vx * vx + vy * vy);
        if (axisLength <= 0 || distance <= 0 || distance > length)
            return false;
        double const cosine = (ax * vx + ay * vy) / (axisLength * distance);
        return cosine >= std::cos(degrees * 0.5 * 3.14159265358979323846 / 180.0);
    }

    // Glacial Boulder: "({internal_cooldown_seconds}-second cooldown per target)": whether a freeze at `nowMs` is
    // allowed given the last one on that target at `lastMs` (0 for none).
    inline bool Freezes(std::uint64_t nowMs, std::uint64_t lastMs, double cooldownSeconds)
    {
        return lastMs == 0 || nowMs >= lastMs + std::uint64_t(cooldownSeconds * 1000.0);
    }

    // Frostfire Bolt: "Chilled enemies it hits also burn": the enemy was chilled before the hit.
    inline bool Burns(Rune rune, bool chilled)
    {
        return rune == Rune::FrostfireBolt && chilled;
    }

    // The production half (dc_shaman_frost_lance.cpp), called from dc_shaman.cpp.
    bool Is(std::uint32_t spellId);
    // The weapon damage percent the cast's own hit of a Frost Lance record deals when the plain loader rule would read
    // the wrong one.
    std::optional<double> BasePct(std::uint32_t spellId);
    // A hit of the skill landed on `target`: the chill, Icefury's stack, the shards, the burn, the freeze and the arc.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
    // The hit of `spellId` being computed: Icefury's stacks raise a Cold hit of the Shaman.
    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);
} // namespace DC::Combat::Shaman::FrostLance
