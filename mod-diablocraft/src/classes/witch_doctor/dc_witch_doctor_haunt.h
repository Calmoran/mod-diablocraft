#pragma once
// Haunt's rules that need no core type, header-only so tests/witch_doctor_haunt compiles this exact code: which rune is which, how many
// spirits a cast releases, which spirit gives way to a new one, whether a cast passes over an enemy already haunted, the Life and Mana a
// spirit returns, which enemy a spirit jumps to and how long a lingering one looks. The production half is dc_witch_doctor_haunt.cpp.
#include "dc_witch_doctor_clock.h"
#include "dc_witch_doctor_pick.h"

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::Haunt
{
    enum class Rune
    {
        None,
        ConsumingSpirit, // Life back each tick, Fire
        LingeringSpirit, // a spirit with no enemy left looks for a new one, Cold
        PoisonedSpirit,  // the haunted take more damage from the Witch Doctor's attacks, Poison
        DrainingSpirit,  // Mana back each tick, Physical
        ResentfulSpirits // two spirits a cast, Cold
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Consuming Spirit")
            return Rune::ConsumingSpirit;
        if (name == "Lingering Spirit")
            return Rune::LingeringSpirit;
        if (name == "Poisoned Spirit")
            return Rune::PoisonedSpirit;
        if (name == "Draining Spirit")
            return Rune::DrainingSpirit;
        if (name == "Resentful Spirits")
            return Rune::ResentfulSpirits;
        return Rune::None;
    }

    // "Release two spirits with every cast": the spirits a cast releases, `resentful` for that rune and one for every other.
    inline unsigned Spirits(Rune rune, double resentful)
    {
        return rune == Rune::ResentfulSpirits ? std::max(1u, static_cast<unsigned>(resentful + 0.5)) : 1u;
    }

    // "An enemy can only be affected by one Haunt at a time": whether a cast passes over an enemy a spirit already holds with `leftSeconds`
    // to go, `minLeft` being the power's "Skip Active Buffed Target Min Duration Left".
    inline bool PassesOver(double leftSeconds, double minLeft)
    {
        return leftSeconds > minLeft;
    }

    // "Max Num of Simultaneous Haunts": the spirit a new one displaces, the oldest of those `startedAt` (the order each was released in)
    // when `most` are out, none when the new one fits.
    inline std::optional<std::size_t> Displaced(std::vector<std::uint64_t> const& startedAt, unsigned most)
    {
        if (startedAt.size() < most || startedAt.empty())
            return std::nullopt;
        return static_cast<std::size_t>(std::min_element(startedAt.begin(), startedAt.end()) - startedAt.begin());
    }

    // Consuming Spirit: "0.008 * Table(Healing, Effective_Level)": the Life a second one spirit returns at a level whose Healing table row is
    // `table`.
    inline double LifePerSecond(double share, double table)
    {
        return share > 0 && table > 0 ? share * table : 0.0;
    }

    // Draining Spirit: "150 / the haunt's duration": the Mana a second one spirit returns over a haunt of `durationSeconds`.
    inline double ManaPerSecond(double total, double durationSeconds)
    {
        return total > 0 && durationSeconds > 0 ? total / durationSeconds : 0.0;
    }

    // Lingering Spirit: "If there are no enemies left, the spirit will linger for up to {duration_seconds} seconds looking for new
    // enemies": whether a spirit that has waited `waitedSeconds` still looks.
    inline bool StillLooking(double waitedSeconds, double lingerSeconds)
    {
        return lingerSeconds > 0 && waitedSeconds < lingerSeconds;
    }

    // The production half (dc_witch_doctor_haunt.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // No hit of the cast itself: the spirit's ticks are the damage.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved on `targets`: the spirit (two for Resentful Spirits) is released.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::WitchDoctor::Haunt
