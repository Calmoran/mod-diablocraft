#pragma once
// The rules of Bone Spikes' runes that need no core type, header-only so tests/necromancer_bone_spikes compiles this
// exact code: which rune is which, where an enemy stands on Path of Bones' line and what the line is worth there, which
// enemies Bone Pillars strikes, and how a bleed is cut into ticks and
// heals. The production half is dc_necromancer_bone_spikes.cpp.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string_view>
#include <vector>

namespace DC::Combat::Necromancer::BoneSpikes
{
    enum class Rune
    {
        None,
        SuddenImpact,
        PathOfBones,
        BonePillars,
        FrostSpikes,
        BloodSpikes
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Sudden Impact")
            return Rune::SuddenImpact;
        if (name == "Path of Bones")
            return Rune::PathOfBones;
        if (name == "Bone Pillars")
            return Rune::BonePillars;
        if (name == "Frost Spikes")
            return Rune::FrostSpikes;
        if (name == "Blood Spikes")
            return Rune::BloodSpikes;
        return Rune::None;
    }

    // The runes whose own code deals the hit, so the engine's hit on the area is none: the line and the pillars.
    inline bool DealsItsOwnHit(Rune rune)
    {
        return rune == Rune::PathOfBones || rune == Rune::BonePillars;
    }

    // Where an enemy at (ex, ey) stands on a line that leaves (px, py) along the unit direction (dx, dy), `length` long
    // and `width` wide: the distance along it, or -1 when it is off the line (behind the start, past the end, or more
    // than half the width to a side).
    inline double AlongTheLine(double px, double py, double dx, double dy, double ex, double ey, double length,
                               double width)
    {
        double const rx = ex - px, ry = ey - py;
        double const along = rx * dx + ry * dy;
        double const aside = std::fabs(rx * dy - ry * dx);
        if (along < 0 || along > length || aside > width / 2.0)
            return -1.0;
        return along;
    }

    // "Damage is increased by up to {max_bonus_pct} for those further away": the line's damage at `along` yards, the
    // bonus growing evenly from none at the Necromancer to its whole at the end of the line.
    inline double PathPct(double basePct, double maxBonusPct, double along, double length)
    {
        double const share = length > 0 ? std::clamp(along / length, 0.0, 1.0) : 0.0;
        return basePct * (1.0 + std::max(0.0, maxBonusPct) / 100.0 * share);
    }

    // Of the candidates' distances from a centre, the indices of the nearest `count` inside the radius, nearest first
    // (a tie keeps the candidate order).
    inline std::vector<std::size_t> Nearest(std::vector<double> const& distances, double radius, std::size_t count)
    {
        std::vector<std::size_t> inside;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (distances[i] <= radius)
                inside.push_back(i);
        std::stable_sort(inside.begin(), inside.end(),
                         [&distances](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        if (inside.size() > count)
            inside.resize(count);
        return inside;
    }

    // Sudden Impact's internal cooldown (the power's RUNEA ICD Duration): an enemy this rune stunned can be stunned by it
    // again only once `icdMs` has passed since that stun. Never stunned is ready; a clock behind the stun is not ready.
    inline bool StunReady(bool stunnedBefore, std::uint64_t lastMs, std::uint64_t nowMs, std::uint64_t icdMs)
    {
        if (!stunnedBefore)
            return true;
        return nowMs >= lastMs && nowMs - lastMs >= icdMs;
    }

    // The ticks that fit a bleed's duration at `tickSeconds`. No tick length, no ticks.
    inline unsigned Ticks(double seconds, double tickSeconds)
    {
        return seconds > 0 && tickSeconds > 0 ? static_cast<unsigned>(std::floor(seconds / tickSeconds + 1e-9)) : 0u;
    }

    // Each tick's share of a total.
    inline double TickShare(double total, unsigned ticks)
    {
        return ticks ? total / ticks : 0.0;
    }

    // "heal you for {heal_pct} of your total life over the duration": one tick's heal, in Life.
    inline double HealPerTick(double maxLife, double healPct, unsigned ticks)
    {
        return ticks && maxLife > 0 && healPct > 0 ? maxLife * healPct / 100.0 / ticks : 0.0;
    }
} // namespace DC::Combat::Necromancer::BoneSpikes
