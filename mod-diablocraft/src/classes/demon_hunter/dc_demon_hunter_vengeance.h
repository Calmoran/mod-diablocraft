#pragma once
// Vengeance's rules that need no core type, header-only so tests/demon_hunter_vengeance compiles this exact code: which
// rune is which, how many side guns fire, the angle of a shot, how often the guns and the second weapon may fire, which
// enemies they pick and what Seethe pays. The production half is dc_demon_hunter_vengeance.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;

namespace DC::Combat::DemonHunter::Vengeance
{
    enum class Rune
    {
        None,
        FromTheShadows, // shadow allies freeze, instead of the rockets, Cold
        DarkHeart,      // less damage taken, Lightning
        PersonalMortar, // grenades at far enemies, instead of the rockets, Fire
        SideCannons,    // the side guns become fewer, heavier cannons that heal, instead of the rockets
        Seethe          // Hatred a second
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "From the Shadows")
            return Rune::FromTheShadows;
        if (name == "Dark Heart")
            return Rune::DarkHeart;
        if (name == "Personal Mortar")
            return Rune::PersonalMortar;
        if (name == "Side Cannons")
            return Rune::SideCannons;
        if (name == "Seethe")
            return Rune::Seethe;
        return Rune::None;
    }

    // "Gain {projectile_count:side_guns} additional piercing shots": the sheet's count is for the file's split-shot
    // multiplier
    // (`gunMultiplier`); the cannons of Side Cannons fire the multiplier the file gives that rune (`cannonMultiplier`),
    // so a proportional share of them.
    inline unsigned GunCount(Rune rune, double sheetCount, double gunMultiplier, double cannonMultiplier)
    {
        if (sheetCount <= 0 || gunMultiplier <= 0)
            return 0;
        double const count =
            rune == Rune::SideCannons ? sheetCount * std::max(0.0, cannonMultiplier) / gunMultiplier : sheetCount;
        return unsigned(std::lround(count));
    }

    // A shot's angle off the aimed line, in degrees: `roll` (0 to 1) of the way across the file's spread, which starts
    // at `minDegrees`.
    inline double Spread(double minDegrees, double deltaDegrees, double roll)
    {
        return minDegrees + deltaDegrees * std::clamp(roll, 0.0, 1.0);
    }

    // The seconds the guns wait between two bursts: the file's internal cooldown is a share of an attack's length
    // (`share` attacks), and an attack lasts 1 / attacks a second. 0 for a Demon Hunter with no attack speed.
    inline double GunCooldownSeconds(double share, double attacksPerSecond)
    {
        return attacksPerSecond > 0 && share > 0 ? share / attacksPerSecond : 0.0;
    }

    // The seconds between two volleys of the second weapon: the file shoots its number of missiles for each attack
    // (missiles a second = the number times attacks a second), so one volley for each attack.
    inline double VolleySeconds(double attacksPerSecond)
    {
        return attacksPerSecond > 0 ? 1.0 / attacksPerSecond : 0.0;
    }

    // Whether the guns or the volley may fire at game time `nowMs`: `lastMs` is when it last did (0 for never).
    inline bool Ready(std::uint64_t lastMs, std::uint64_t nowMs, double intervalSeconds)
    {
        return lastMs == 0 || double(nowMs - std::min(nowMs, lastMs)) >= intervalSeconds * 1000.0;
    }

    // The enemies (their positions in `distances`) a volley of `count` shots goes to: the nearest first, each shot the
    // next nearest, and the nearest again once every enemy within `within` yards has one. Nothing when none is that
    // near.
    inline std::vector<std::size_t> Nearest(std::vector<double> const& distances, double within, unsigned count)
    {
        std::vector<std::size_t> near;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (distances[i] <= within)
                near.push_back(i);
        std::stable_sort(near.begin(), near.end(),
                         [&distances](std::size_t a, std::size_t b) { return distances[a] < distances[b]; });
        std::vector<std::size_t> picked;
        if (near.empty())
            return picked;
        for (unsigned shot = 0; shot < count; ++shot)
            picked.push_back(near[shot % near.size()]);
        return picked;
    }

    // Personal Mortar's grenades go to "random enemies outside melee range": the enemies (their positions in
    // `distances`) at least `minYards` away and no more than `maxYards`.
    inline std::vector<std::size_t> InBand(std::vector<double> const& distances, double minYards, double maxYards)
    {
        std::vector<std::size_t> band;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (distances[i] >= minYards && distances[i] <= maxYards)
                band.push_back(i);
        return band;
    }

    // Seethe: "Gain {regen_per_second_resource} Hatred per second", paid every `tickSeconds`.
    inline double SeethePerTick(double perSecond, double tickSeconds)
    {
        return perSecond > 0 && tickSeconds > 0 ? perSecond * tickSeconds : 0.0;
    }

    // From the Shadows freezes an enemy once in `cooldownSeconds`: `readyAtMs` is when it may again (0 for never
    // frozen).
    inline bool FreezeReady(std::uint64_t readyAtMs, std::uint64_t nowMs)
    {
        return nowMs >= readyAtMs;
    }

    // The production half (dc_demon_hunter_vengeance.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The cast does no damage of its own.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The form begins: Dark Heart's damage reduction, the clock the rest reads.
    void Cast(Player* player, std::uint32_t spellId);
    // An attack of `spellId` connected (Combat::Connected): the side guns and the second weapon fire while the form
    // lasts.
    void Attack(Player* player, std::uint32_t spellId);
    // "Gain {damage_bonus_pct} increased damage" while the form lasts: a factor on every hit.
    void Multipliers(Player* player, DC::Combat::Factors& out);
    void RegisterScripts();
} // namespace DC::Combat::DemonHunter::Vengeance
