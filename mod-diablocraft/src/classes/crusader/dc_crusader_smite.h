#pragma once
// Smite's rules that need no core type, header-only so tests/crusader_smite compiles this exact code: which rune is
// which, which enemies the chains break off to, and when two bound enemies have moved far enough apart. The production
// half is dc_crusader_smite.cpp.
#include "dc_crusader_nearest.h"

#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Crusader::Smite
{
    enum class Rune
    {
        None,
        SharedFate, // the enemies hit are bound; moving apart stuns them
        Shackle,    // a chance to Immobilize each enemy hit
        Shatter,    // the chains explode around each enemy hit
        Reaping,    // Life regeneration for every enemy hit
        Surge       // more enemies hit (the sheet's number is the record's)
    };

    inline Rune RuneOf(std::string_view rune)
    {
        if (rune == "Shared Fate")
            return Rune::SharedFate;
        if (rune == "Shackle")
            return Rune::Shackle;
        if (rune == "Shatter")
            return Rune::Shatter;
        if (rune == "Reaping")
            return Rune::Reaping;
        if (rune == "Surge")
            return Rune::Surge;
        return Rune::None;
    }

    // "The chains break off and strike up to {target_count} additional enemies within {radius_yards:chain} yards": the
    // nearest enemies inside the radius, up to the count (dc_crusader_nearest.h).
    inline std::vector<std::size_t> Chained(std::vector<double> const& distances, double radius, std::size_t count)
    {
        return Nearest(distances, radius, count);
    }

    // "Enemies who share fate will be stunned ... if they move {distance_yards} yards away from each other": two bound
    // enemies were `then` yards apart when bound and are `now` yards apart; they have moved that far apart when the gap
    // has grown by the distance.
    inline bool MovedApart(double now, double then, double distance)
    {
        return distance > 0 && now - then >= distance;
    }

    // A binding lasts to its end time and not past it.
    inline bool Bound(std::uint64_t now, std::uint64_t until)
    {
        return now < until;
    }

    // The production half (dc_crusader_smite.cpp), called from dc_crusader.cpp.
    bool Is(std::uint32_t spellId);
    // The skill's hit: 175%, which every rune inherits (the chains' 150% is the chain's).
    std::optional<double> BasePct(std::uint32_t spellId);
    // The hit landed on `targets.front()`: the chains, and what the rune does to every enemy they struck.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
} // namespace DC::Combat::Crusader::Smite
