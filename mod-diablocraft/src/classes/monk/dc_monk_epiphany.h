#pragma once
// Epiphany and its five runes. The entry points are below; the rules that need no core
// type are inline here so tests/monk_epiphany compiles this exact code. Sources: monk_skills.csv, monk_runes.csv and
// monk_skill_values.csv (the sheets), Power/X1_Monk_Epiphany.pow (the power file, SF_ numbers) and d3planner's
// simulator monk.js:1057-1088 @898918b (the on-cast rule of Inner Fire and Soothing Mist).
#include <cmath>
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Monk::Epiphany
{
    bool Is(std::uint32_t spellId);
    // The logout hook that drops a Monk's buff state (Monk::RegisterScripts).
    void RegisterScripts();
    // The cast's own hit is nothing: Inner Fire's 353% is its fireballs'.
    std::optional<double> BasePct(std::uint32_t spellId);
    // Before a Monk attack's hits (Monk::Begin, and Monk::Approach for a selected enemy): while Epiphany is up, the dash to
    // `target`. True when the Monk moved.
    bool Dash(Player* player, std::uint32_t spellId, Unit* target);
    // An Epiphany cast has resolved (Monk::Cast): the buff starts.
    void Cast(Player* player, std::uint32_t spellId);
    // Every cast as it begins (Monk::Casting, the shared OnCast hook): while Epiphany is up, Inner Fire throws, Soothing
    // Mist heals and Ascendance decides whether this cast's hits stun.
    void Casting(Player* player, std::uint32_t spellId);
    // One hit of a cast landed (Monk::Landed): Ascendance's stun.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);

    // Rabid Strike: "Spirit spenders that teleport you while Epiphany is active are also mimicked on a nearby
    // target with [350-450]% increased damage for free." A dash carries the copy when the item is worn (its percent above 0) and the
    // dashing skill costs Spirit.
    inline bool Mimics(double pct, double cost)
    {
        return pct > 0 && cost > 0;
    }
    // The copy's enemy among the enemies near the Monk (`distances` from it, `primary` the index of the dash's own target, -1 when it is
    // not among them): the nearest other one, or the dash's target when it stands alone. -1 when there is none.
    inline int MimicTarget(std::vector<double> const& distances, int primary)
    {
        int best = -1;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (int(i) != primary && (best < 0 || distances[i] < distances[std::size_t(best)]))
                best = int(i);
        return best >= 0 ? best : primary;
    }
    // The copy's damage: 1 + N/100 of the skill's own.
    inline double MimicFactor(double pct)
    {
        return 1.0 + pct / 100.0;
    }

    struct Point
    {
        double x = 0, y = 0;
    };

    // "enabling your melee attacks to instantly dash to your target": only past SF_3 'Min Teleport Range' and inside
    // SF_6 'Max Teleport Distance'.
    inline bool Dashes(double distance, double minYards, double maxYards)
    {
        return minYards > 0 && distance > minYards && distance <= maxYards;
    }

    // Where the dash lands: SF_4 'Teleport Offset (Teleport in front of target)' yards short of the target, on the line
    // from the Monk.
    inline Point Landing(Point from, Point to, double offset)
    {
        double const dx = to.x - from.x, dy = to.y - from.y, distance = std::hypot(dx, dy);
        if (distance <= offset)
            return from;
        double const share = (distance - offset) / distance;
        return {from.x + dx * share, from.y + dy * share};
    }

    // An internal cooldown (SF_1, SF_25): true, and `last` stamped, when `ms` has passed since the last one.
    inline bool Ready(std::uint64_t now, std::optional<std::uint64_t>& last, std::uint64_t ms)
    {
        if (last && now < *last + ms)
            return false;
        last = now;
        return true;
    }

    // Inner Fire's piercing fireball: ahead of `from` along `facing` (radians), no farther than `length` (SF_26) and
    // within `halfWidth` (SF_28) of its line.
    inline bool OnLine(Point from, double facing, Point unit, double length, double halfWidth)
    {
        double const dx = unit.x - from.x, dy = unit.y - from.y;
        double const along = dx * std::cos(facing) + dy * std::sin(facing);
        double const across = -dx * std::sin(facing) + dy * std::cos(facing);
        return along >= 0 && along <= length && std::abs(across) <= halfWidth;
    }

    // The Spirit per second is paid once a second, the first a second after the cast: the payments a buff of `seconds`
    // makes.
    inline unsigned Payments(double seconds)
    {
        return seconds > 0 ? unsigned(seconds + 1e-9) : 0u;
    }

    // Ascendance: "your next attack after moving {distance_yards} yards" stuns. The yards moved since the last stun.
    struct Stride
    {
        double moved = 0;

        void Add(double yards)
        {
            if (yards > 0)
                moved += yards;
        }
        bool Armed(double needed) const
        {
            return needed > 0 && moved >= needed;
        }
        void Spend()
        {
            moved = 0;
        }
    };

    // Ascendance's decision, in the order the cast path runs it: Begin as a cast starts (the OnCast hook), Dashed when
    // that cast's dash lands (Monk::Begin, before its hits), Hit for each of its hits (Monk::Landed). A dash that fills
    // the stride arms the attack it carries. The stun is that attack's: its first hit spends the stride, and the hits
    // landing in the same moment (one cast resolves its hits in one server tick) stun too; a later hit of the same
    // spell (a channel tick, a later shell) does not, and clears it.
    struct Ascent
    {
        Stride stride;
        std::uint32_t cast = 0;
        std::optional<std::uint64_t> struckAt;

        void Begin(std::uint32_t spellId, double needed)
        {
            cast = stride.Armed(needed) ? spellId : 0;
            struckAt.reset();
        }
        void Dashed(std::uint32_t spellId, double yards, double needed)
        {
            stride.Add(yards);
            if (stride.Armed(needed) && cast != spellId)
            {
                cast = spellId;
                struckAt.reset();
            }
        }
        bool Hit(std::uint32_t spellId, std::uint64_t now)
        {
            if (!cast || cast != spellId)
                return false;
            if (!struckAt)
            {
                stride.Spend();
                struckAt = now;
                return true;
            }
            if (*struckAt == now)
                return true;
            cast = 0;
            struckAt.reset();
            return false;
        }
    };
} // namespace DC::Combat::Monk::Epiphany
