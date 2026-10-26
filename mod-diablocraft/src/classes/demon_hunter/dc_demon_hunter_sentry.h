#pragma once
// Sentry's rules that need no core type, header-only so tests/demon_hunter_sentry compiles this exact code: which rune is
// which, the pause between a turret's shots and rockets, how long a rocket is in the air, the damage of a chain pulse,
// how far a chain link reaches, which enemy the turret shoots and how long a pulse's shield is held. The production half
// is dc_demon_hunter_sentry.cpp.
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::DemonHunter::Sentry
{
    enum class Rune
    {
        None,
        ChainOfTorment, // a chain between you and the turrets and between the turrets, Physical
        ImpalingBolt,   // the bolts pierce, Lightning
        SpitfireTurret, // homing rockets as well, Fire
        PolarStation,   // chills the enemies about it, Cold
        GuardianTurret  // a shield on the allies about it, Physical
    };

    inline Rune RuneOf(std::string_view name)
    {
        if (name == "Chain of Torment")
            return Rune::ChainOfTorment;
        if (name == "Impaling Bolt")
            return Rune::ImpalingBolt;
        if (name == "Spitfire Turret")
            return Rune::SpitfireTurret;
        if (name == "Polar Station")
            return Rune::PolarStation;
        if (name == "Guardian Turret")
            return Rune::GuardianTurret;
        return Rune::None;
    }

    // Whether the turret's own shots take the rune's element: Spitfire Turret names Fire for its rockets alone.
    inline bool ShotTakesRuneElement(Rune rune)
    {
        return rune != Rune::SpitfireTurret;
    }

    // "Turret Fire Rate = Attacks_Per_Second_Total": the milliseconds between two shots. No speed, no shots.
    inline std::uint32_t ShotMs(double attacksPerSecond)
    {
        return attacksPerSecond > 0 ? std::uint32_t(1000.0 / attacksPerSecond + 0.5) : 0u;
    }

    // "Missile Fire Rate = 0.9 / Attacks_Per_Second_Total" seconds: the milliseconds between two rockets.
    inline std::uint32_t RocketMs(double rateFactor, double attacksPerSecond)
    {
        return attacksPerSecond > 0 ? std::uint32_t(rateFactor / attacksPerSecond * 1000.0 + 0.5) : 0u;
    }

    // "Damage Delay Warmup" plus "Damage Delay Per Ft" for each yard flown: the milliseconds before a rocket lands.
    inline std::uint32_t RocketDelayMs(double warmupSeconds, double perYardSeconds, double yards)
    {
        return std::uint32_t((warmupSeconds + perYardSeconds * std::max(0.0, yards)) * 1000.0 + 0.5);
    }

    // The tooltip states a chain's damage each second; a pulse of `intervalSeconds` deals its share.
    inline double PulsePct(double perSecondPct, double intervalSeconds)
    {
        return perSecondPct * intervalSeconds;
    }

    // The yards from the point (px, py) to the segment from (ax, ay) to (bx, by).
    inline double DistanceToSegment(double px, double py, double ax, double ay, double bx, double by)
    {
        double const dx = bx - ax, dy = by - ay, length2 = dx * dx + dy * dy;
        double along = length2 > 0 ? ((px - ax) * dx + (py - ay) * dy) / length2 : 0.0;
        along = std::clamp(along, 0.0, 1.0);
        return std::hypot(px - (ax + along * dx), py - (ay + along * dy));
    }

    // A chain link holds while its ends are no farther apart than the file's maximum; the enemies it touches are those
    // within `touch` yards of it.
    inline bool Linked(double length, double maxYards)
    {
        return length <= maxYards;
    }

    inline bool Touches(double distanceToLink, double touchYards)
    {
        return distanceToLink <= touchYards;
    }

    // The nearest of the distances (the turret shoots the enemy nearest to it); `none` for no enemy.
    constexpr std::size_t none = std::size_t(-1);
    inline std::size_t Nearest(std::vector<double> const& distances)
    {
        std::size_t best = none;
        for (std::size_t i = 0; i < distances.size(); ++i)
            if (best == none || distances[i] < distances[best])
                best = i;
        return best;
    }

    // A shield pulse is held for two pulses, so one pulse the server runs late does not lower it.
    inline double ShieldHoldSeconds(double pulseSeconds)
    {
        return 2.0 * pulseSeconds;
    }

    // The production half (dc_demon_hunter_sentry.cpp), called from dc_demon_hunter.cpp.
    bool Is(std::uint32_t spellId);
    // The cast puts the turret down, it hits nothing itself.
    std::optional<double> BasePct(std::uint32_t spellId);
    // The cast spends a charge and sets the turret (and the rune's pulse) down where the Demon Hunter stands.
    void Cast(Player* player, std::uint32_t spellId);
} // namespace DC::Combat::DemonHunter::Sentry
