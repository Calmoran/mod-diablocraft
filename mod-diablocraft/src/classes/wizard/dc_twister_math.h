#pragma once
/*
 * Energy Twister's travel: the path a travelling twister wanders and where each of its ticks lands. Pure arithmetic, so
 * scripts/tests/classes/test_wizard_energy_twister.py compiles this header and drives it; dc_wizard_energy_twister.cpp reads
 * the numbers (the sheet's dot_duration_seconds and interval_seconds, the tunables wizard.energy_twister_*) and moves the
 * carrier along the same path.
 *
 * The twister appears at the aim point heading away from the Wizard and goes forward at `speed` yards a second. Every
 * `turnSeconds` it turns by a random angle within +-`turnLimitDegrees`, forward-biased: the turn is the limit times the
 * difference of two uniform rolls, a triangle that peaks at straight ahead (D3's wander). A turn
 * limit of 0 is a straight path (Valthek's Rebuke passes 0).
 */
#include <cmath>
#include <cstddef>
#include <vector>

namespace DC::Combat::Wizard::Twister
{
    struct Point
    {
        double x = 0, y = 0;
    };

    // Where the twister heads first: from the Wizard toward the aim point, or the Wizard's own facing when the aim is
    // at its feet.
    inline double Heading(Point wizard, double facing, Point aim)
    {
        double const dx = aim.x - wizard.x, dy = aim.y - wizard.y;
        return dx * dx + dy * dy < 0.01 ? facing : std::atan2(dy, dx);
    }

    // One turn in radians from two rolls in [0, 1): forward-biased within +-limit.
    inline double Turn(double turnLimitDegrees, double roll1, double roll2)
    {
        return turnLimitDegrees * (roll1 - roll2) * 3.14159265358979323846 / 180.0;
    }

    // How many legs the life takes: one per turn interval, the last one shorter when the life does not divide.
    inline std::size_t Legs(double lifeSeconds, double turnSeconds)
    {
        if (lifeSeconds <= 0)
            return 0;
        if (turnSeconds <= 0)
            return 1;
        return static_cast<std::size_t>(std::ceil(lifeSeconds / turnSeconds - 1e-9));
    }

    // The waypoints: the start, then the end of each leg. `rolls` holds two rolls per leg after the first (the first
    // leg goes straight ahead); a missing roll is 0.5, no turn.
    inline std::vector<Point> Path(Point start, double heading, double speed, double lifeSeconds, double turnSeconds,
                                   double turnLimitDegrees, std::vector<double> const& rolls)
    {
        std::vector<Point> path{start};
        std::size_t const legs = Legs(lifeSeconds, turnSeconds);
        for (std::size_t i = 0; i < legs; ++i)
        {
            if (i > 0)
            {
                auto roll = [&](std::size_t k) { return k < rolls.size() ? rolls[k] : 0.5; };
                heading += Turn(turnLimitDegrees, roll(2 * (i - 1)), roll(2 * (i - 1) + 1));
            }
            double const seconds =
                turnSeconds <= 0 ? lifeSeconds : std::fmin(turnSeconds, lifeSeconds - i * turnSeconds);
            Point const& from = path.back();
            path.push_back(
                {from.x + speed * seconds * std::cos(heading), from.y + speed * seconds * std::sin(heading)});
        }
        return path;
    }

    // Where the twister is `t` seconds into its life on `path` (legs of `turnSeconds`, the last one shorter).
    inline Point At(std::vector<Point> const& path, double turnSeconds, double lifeSeconds, double t)
    {
        if (path.size() < 2 || t <= 0)
            return path.empty() ? Point{} : path.front();
        double const step = turnSeconds <= 0 ? lifeSeconds : turnSeconds;
        std::size_t i = static_cast<std::size_t>(t / step);
        if (i >= path.size() - 1)
            return path.back();
        double const length = std::fmin(step, lifeSeconds - i * step);
        double const f = length > 0 ? std::fmin(1.0, (t - i * step) / length) : 1.0;
        return {path[i].x + (path[i + 1].x - path[i].x) * f, path[i].y + (path[i + 1].y - path[i].y) * f};
    }

    // The ticks: one every interval_seconds over dot_duration_seconds, the first at once (wizard_skill_values.csv
    // interval_seconds: "first tick at once"), so 6 s / 0.5 s is 12 ticks at 0, 0.5 .. 5.5.
    inline std::size_t Ticks(double lifeSeconds, double intervalSeconds)
    {
        return lifeSeconds > 0 && intervalSeconds > 0 ? static_cast<std::size_t>(lifeSeconds / intervalSeconds + 1e-9)
                                                      : 0;
    }

    // Each tick's share of the skill's damage_pct on every enemy inside the radius, as the stationary ground deals it.
    inline double TickPct(double damagePct, std::size_t ticks)
    {
        return ticks ? damagePct / static_cast<double>(ticks) : 0.0;
    }
} // namespace DC::Combat::Wizard::Twister
