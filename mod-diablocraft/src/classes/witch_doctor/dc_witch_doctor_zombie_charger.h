#pragma once
// Zombie Charger's rules that need no core type, header-only so tests/witch_doctor_zombie_charger compiles this exact
// code: which rune is which, where the zombies run, which enemies they reach, where Pile On falls and what Undeath
// reanimates. The production half is dc_witch_doctor_zombie_charger.cpp.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::WitchDoctor::ZombieCharger
{
    enum class Rune
    {
        None,
        ZombieBears,   // bears side by side, Poison
        LumberingCold, // zombies run in every direction, slowing, Cold
        PileOn,        // a tower of zombies falls on a place, Physical
        Undeath,       // a zombie that kills charges on, Poison
        ExplosiveBeast // an exploding dog, Fire
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Zombie Bears")
            return Rune::ZombieBears;
        if (name == "Lumbering Cold")
            return Rune::LumberingCold;
        if (name == "Pile On")
            return Rune::PileOn;
        if (name == "Undeath")
            return Rune::Undeath;
        if (name == "Explosive Beast")
            return Rune::ExplosiveBeast;
        return Rune::None;
    }

    // Whether a point `dx`, `dy` yards from where a zombie starts (east and north) stands on its path: it runs `length`
    // yards along `heading` (radians) and is `width` yards wide, half on each side. A path with no width reaches
    // nobody.
    inline bool OnPath(double dx, double dy, double heading, double length, double width)
    {
        double const along = dx * std::cos(heading) + dy * std::sin(heading);
        double const across = -dx * std::sin(heading) + dy * std::cos(heading);
        return width > 0 && along >= 0 && along <= length && std::fabs(across) <= width / 2;
    }

    // Zombie Bears: the bears run side by side, `spacing` yards apart, centred on the aim: the sideways yards of each.
    inline std::vector<double> BearOffsets(unsigned count, double spacing)
    {
        std::vector<double> offsets;
        for (unsigned bear = 0; bear < count; ++bear)
            offsets.push_back((double(bear) - (double(count) - 1.0) / 2.0) * spacing);
        return offsets;
    }

    // Lumbering Cold: "run in all directions": the heading (radians) of each of `count` zombies, evenly round from the
    // aim.
    inline std::vector<double> RunningHeadings(unsigned count, double aim)
    {
        constexpr double TwoPi = 6.28318530717958647692;
        std::vector<double> headings;
        for (unsigned zombie = 0; zombie < count; ++zombie)
            headings.push_back(aim + TwoPi * double(zombie) / double(count));
        return headings;
    }

    // Pile On: where the tower falls: on the enemy aimed at when it is within `reach` yards, else `distance` yards
    // ahead (the point's distance from the Witch Doctor along the aim).
    inline double TowerDistance(std::optional<double> aimedYards, double reach, double distance)
    {
        return aimedYards && *aimedYards <= reach ? *aimedYards : distance;
    }

    // Undeath: "If the Zombie Charger kills any enemies, it will reanimate and charge nearby enemies ... This effect
    // can repeat up to {max_count} times": a charge after `depth` reanimations (0 for the first zombie) may reanimate
    // while `depth` is below the most.
    inline bool Reanimates(bool killed, unsigned depth, unsigned most)
    {
        return killed && depth < most;
    }

    // The nearest enemy within `search` yards of the place a zombie fell (`distances`, one for each): its position,
    // none when no enemy is that near.
    inline std::optional<std::size_t> NearestWithin(std::vector<double> const& distances, double search)
    {
        std::optional<std::size_t> nearest;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (distances[i] <= search && (!nearest || distances[i] < distances[*nearest]))
                nearest = i;
        return nearest;
    }

    // The production half (dc_witch_doctor_zombie_charger.cpp), called from dc_witch_doctor.cpp.
    bool Is(std::uint32_t spellId);
    // The cast's own hit: the skill's, and Undeath's first zombie; every other rune strikes itself.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast resolved: the bears, the cold zombies, the tower and the beast.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets);
    // A zombie's hit landed on `target`: Undeath's reanimation when it killed.
    void Landed(Player* player, Unit* target, std::uint32_t spellId);
} // namespace DC::Combat::WitchDoctor::ZombieCharger
