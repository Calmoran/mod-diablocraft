#pragma once
// Caltrops' rules that need no core type, header-only so tests/demon_hunter_caltrops compiles this exact code: which rune is
// which, how many traps are laid at once, what a tick of the sprung trap deals. The production half is
// dc_demon_hunter_caltrops.cpp.
#include "dc_demon_hunter_clock.h"
#include "dc_demon_hunter_dot.h"

#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;
struct Position;

namespace DC::Combat::DemonHunter::Caltrops
{
    enum class Rune
    {
        None,
        JaggedSpikes,   // the sprung trap also hurts, Physical
        HookedSpines,   // a stronger slow
        TorturousGround, // springing it immobilizes
        CarvedStakes,   // a cheaper trap (a sheet number)
        BaitTheTrap     // critical hit chance while standing in it
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Jagged Spikes")
            return Rune::JaggedSpikes;
        if (name == "Hooked Spines")
            return Rune::HookedSpines;
        if (name == "Torturous Ground")
            return Rune::TorturousGround;
        if (name == "Carved Stakes")
            return Rune::CarvedStakes;
        if (name == "Bait the Trap")
            return Rune::BaitTheTrap;
        return Rune::None;
    }

    // "Max Traps": laying one more when `placed` are down takes away this many of the oldest, so that no more than `most` stand.
    // No limit stated, none taken away.
    inline std::size_t Overflow(std::size_t placed, std::size_t most)
    {
        return most > 0 && placed >= most ? placed - most + 1 : 0;
    }

    // "Enemies in the area also take {damage_pct} weapon damage over {dot_duration_seconds} seconds": what one tick of
    // `tickSeconds` carries.
    inline double TickPct(double totalPct, double seconds, double tickSeconds)
    {
        return Dot::TickPct(totalPct, Dot::Ticks(seconds, tickSeconds));
    }

    // Whether a trap that has waited `waitedMs` for an enemy has waited out its `limitMs`. No limit, never.
    inline bool WaitedOut(double waitedMs, double limitMs)
    {
        return limitMs > 0 && waitedMs >= limitMs;
    }

    // The production half (dc_demon_hunter_caltrops.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The trap deals nothing when it is laid; its damage is the sprung trap's.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved at the ground point `center`: the trap is laid there.
    void Ground(Player* player, std::uint32_t spellId, Position const& center);
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::Caltrops
