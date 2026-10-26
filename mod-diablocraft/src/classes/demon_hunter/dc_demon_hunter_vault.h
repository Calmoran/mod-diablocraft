#pragma once
// Vault's rules that need no core type, header-only so tests/demon_hunter_vault compiles this exact code: which rune is
// which, where an enemy stands against the path, which enemy a shot goes to. The
// production half is dc_demon_hunter_vault.cpp.
#include "dc_demon_hunter_clock.h"
#include "dc_demon_hunter_dot.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>

class Player;
class Unit;
struct Position;

namespace DC::Combat::DemonHunter::Vault
{
    enum class Rune
    {
        None,
        TrailOfCinders, // a trail of fire along the path, Fire
        Acrobatics,     // no Discipline cost, a cooldown (the record holds both)
        ActionShot,     // arrows at nearby enemies that always crit
        Tumble,         // the next Vault within a time costs less
        RattlingRoll    // enemies vaulted through are knocked away and stunned
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Trail of Cinders")
            return Rune::TrailOfCinders;
        if (name == "Acrobatics")
            return Rune::Acrobatics;
        if (name == "Action Shot")
            return Rune::ActionShot;
        if (name == "Tumble")
            return Rune::Tumble;
        if (name == "Rattling Roll")
            return Rune::RattlingRoll;
        return Rune::None;
    }

    // Where a point stands against a path that starts at (startX, startY) and heads `angle`: yards along it and yards
    // to its side.
    struct Place
    {
        double along = 0;
        double across = 0;
    };

    inline Place PlaceOn(double startX, double startY, double angle, double x, double y)
    {
        double const dx = x - startX, dy = y - startY;
        return {dx * std::cos(angle) + dy * std::sin(angle), dy * std::cos(angle) - dx * std::sin(angle)};
    }

    // A box `length` long and `width` wide with the path's start at its middle ("E: Stun While Vaulting Length/Width"):
    // the box that travels with the Demon Hunter. No size, nothing in it.
    inline bool InBox(Place place, double length, double width)
    {
        return length > 0 && width > 0 && std::fabs(place.along) <= length / 2 && std::fabs(place.across) <= width / 2;
    }

    // A band `width` wide from the path's start for `reach` yards (the trail left behind). No width, nothing in it.
    inline bool InBand(Place place, double reach, double width)
    {
        return width > 0 && place.along >= 0 && place.along <= reach && std::fabs(place.across) <= width / 2;
    }

    // "Leave a trail of fire ... that deals {damage_pct} weapon damage over {dot_duration_seconds} seconds": what one
    // tick of `tickSeconds` carries.
    inline double TrailTickPct(double totalPct, double seconds, double tickSeconds)
    {
        return Dot::TickPct(totalPct, Dot::Ticks(seconds, tickSeconds));
    }

    // "shoot {projectile_count} arrows ... at nearby enemies": the enemy (nearest first) the `shot`th arrow flies at,
    // the arrows shared round the `enemies` there are. None to shoot at, none chosen.
    inline std::size_t ShotAt(std::size_t shot, std::size_t enemies)
    {
        return enemies ? shot % enemies : 0;
    }

    // "These shots are guaranteed Critical Hits": the chance the rune adds to every hit of its arrows (the chance is
    // capped at all).
    inline double CritBonus(Rune rune)
    {
        return rune == Rune::ActionShot ? 100.0 : 0.0;
    }

    // The production half (dc_demon_hunter_vault.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The vault itself hits nothing; the runes' damage is the trail's and the arrows'.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The chance Action Shot's arrows add to the critical hit roll of a hit of `spellId`.
    double CritBonus(std::uint32_t spellId);
    // The cast resolved with the Demon Hunter bound for `destination`: the rune's part begins.
    void Ground(Player* player, std::uint32_t spellId, Position const& destination);
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::Vault
