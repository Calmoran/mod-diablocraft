#pragma once
// Spirit Wolves' rules that need no core type, header-only so tests/shaman_spirit_wolves compiles this exact code: which rune
// is which, how the wolves fan out, which enemies a wolf's lane touches and when its wave reaches them, what each rune adds
// to a hit, where the burning trail's patches lie and how much Maelstrom the Pack pays. The production half is
// dc_shaman_spirit_wolves.cpp, called from dc_shaman.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <numeric>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Shaman::SpiritWolves
{
    enum class Rune
    {
        None,
        SpiritPack,      // five wolves fanned in a cone
        LightningWolves, // Lightning; each wolf hit arcs to nearby enemies
        FieryWolves,     // Fire; the wolves leave a burning trail
        FrostWolves,     // Cold; enemies hit are frozen
        SpiritOfThePack  // each enemy hit pays Maelstrom
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Spirit Pack")
            return Rune::SpiritPack;
        if (name == "Lightning Wolves")
            return Rune::LightningWolves;
        if (name == "Fiery Wolves")
            return Rune::FieryWolves;
        if (name == "Frost Wolves")
            return Rune::FrostWolves;
        if (name == "Spirit of the Pack")
            return Rune::SpiritOfThePack;
        return Rune::None;
    }

    // What a rune adds to the wave.
    inline bool Arcs(Rune rune) { return rune == Rune::LightningWolves; }
    inline bool LeavesTrail(Rune rune) { return rune == Rune::FieryWolves; }
    inline bool Freezes(Rune rune) { return rune == Rune::FrostWolves; }
    inline bool Pays(Rune rune) { return rune == Rune::SpiritOfThePack; }

    // The directions of the wolves, as angles from the aim in radians: one wolf straight ahead, more spread evenly across
    // `coneDegrees` (no cone: all of them down the same line).
    inline std::vector<double> Fan(unsigned wolves, double coneDegrees)
    {
        std::vector<double> angles(wolves, 0.0);
        if (wolves < 2 || coneDegrees <= 0)
            return angles;
        double const half = coneDegrees * 3.14159265358979323846 / 360.0;
        for (unsigned index = 0; index < wolves; ++index)
            angles[index] = -half + 2.0 * half * index / (wolves - 1);
        return angles;
    }

    // A wolf's lane: a strip `halfWidth` either side of a line of `range` yards. `dx`/`dy` is the enemy's place from the caster,
    // `bearing` the lane's direction in radians. `ahead` is how far along the lane the enemy stands.
    struct Reach
    {
        bool touched = false;
        double ahead = 0;
    };
    inline Reach Touch(double bearing, double dx, double dy, double range, double halfWidth)
    {
        double const ahead = dx * std::cos(bearing) + dy * std::sin(bearing);
        double const aside = -dx * std::sin(bearing) + dy * std::cos(bearing);
        return {ahead >= 0 && ahead <= range && std::abs(aside) <= halfWidth, ahead};
    }

    // Seconds the wave takes to run `yards` at `speed` yards a second. No speed, no wait.
    inline double Seconds(double yards, double speed)
    {
        return speed > 0 && yards > 0 ? yards / speed : 0.0;
    }

    // The enemies a hit arcs to: the `count` nearest, nearest first. `distances[i]` is enemy i's yards from the struck one.
    inline std::vector<std::size_t> Nearest(std::vector<double> const& distances, std::size_t count)
    {
        std::vector<std::size_t> order(distances.size());
        std::iota(order.begin(), order.end(), std::size_t(0));
        std::stable_sort(order.begin(), order.end(),
                         [&](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        if (order.size() > count)
            order.resize(count);
        return order;
    }

    // The patches of a trail along `range` yards, one every `spacing` yards, the first at one spacing out. No spacing, none.
    inline unsigned Patches(double range, double spacing)
    {
        return range > 0 && spacing > 0 ? static_cast<unsigned>(std::floor(range / spacing + 1e-9)) : 0u;
    }

    // "N% weapon damage per second" pulsed every `tickSeconds`: the percent of one pulse.
    inline double PulsePct(double perSecondPct, double tickSeconds)
    {
        return perSecondPct * tickSeconds;
    }

    // The Maelstrom the next enemy hit pays: `perHit`, never past `cap` for the cast. `gained` is what the cast has paid.
    inline double Pay(double gained, double perHit, double cap)
    {
        return std::max(0.0, std::min(perHit, cap - gained));
    }

    // The production half (dc_shaman_spirit_wolves.cpp).
    bool Is(std::uint32_t spellId);
    // The cast hits nothing itself; each wolf strikes as it passes.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved: the wolves run.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Shaman::SpiritWolves
