#pragma once
// Mystic Ally's rules that need no core type, header-only so tests/monk_mystic_ally
// compiles this exact code. The game glue is dc_monk_mystic_ally.cpp.
#include <algorithm>
#include <cmath>
#include <cstdint>

namespace DC::Combat::Monk::MysticAlly
{
    // "A mystic ally fights by your side. ... When the ally dies, it is reborn after {duration_seconds:respawn}
    // seconds." The ally is there while the skill is on the bar: one look a poll, what to do about it.
    enum class Act
    {
        Keep,    // nothing to do
        Summon,  // no ally and none waiting to be reborn: bring the slotted rune's
        Despawn, // the skill left the bar: send it away
        Replace, // the rune on the bar changed: send this one away and bring the new one
    };

    // `slotted`: the Mystic Ally record on the bar (0 when none). `summoned`: the record the living ally was summoned
    // for (0 when there is no living ally). `rebornAt`: ms the dead or spent ally comes back (0 when none is waiting).
    inline Act Decide(std::uint32_t slotted, std::uint32_t summoned, std::uint64_t rebornAt, std::uint64_t now)
    {
        if (!slotted)
            return summoned ? Act::Despawn : Act::Keep;
        if (summoned)
            return summoned == slotted ? Act::Keep : Act::Replace;
        return now >= rebornAt ? Act::Summon : Act::Keep;
    }

    // The Crudest Boots (N-EXTRA): "Mystic Ally summons two Mystic Allies". The allies a Monk keeps: the skill's
    // one and the power's `summon_count_add` more, whole allies only.
    inline unsigned AllyCount(double extra)
    {
        return 1 + (extra >= 1 ? unsigned(extra + 1e-9) : 0u);
    }

    // The same item's "able to attack with their active forms longer": the seconds of an active form (Earth Ally's boulder, Fire
    // Ally's fuse, the base Active's window) lasting `pct` percent longer with the power (the tunable
    // mystic_ally_boots_form_duration_pct), each by its own seconds. No power, or a percent not above 0: the form's own seconds.
    inline double FormSeconds(double seconds, bool power, double pct)
    {
        return power && pct > 0 ? seconds * (1 + pct / 100) : seconds;
    }

    // Water Ally's waves "in quick succession": a strip `lengthYards` long and twice `radiusYards` wide that starts at
    // the ally and runs along `facing` (radians, WoW's orientation: 0 along +x, counter-clockwise).
    struct Point
    {
        double x = 0, y = 0;
    };
    inline bool InWave(Point ally, double facing, double lengthYards, double radiusYards, Point at)
    {
        double const dx = at.x - ally.x, dy = at.y - ally.y;
        double const along = dx * std::cos(facing) + dy * std::sin(facing);
        double const across = -dx * std::sin(facing) + dy * std::cos(facing);
        return along >= 0 && along <= lengthYards && std::fabs(across) <= radiusYards;
    }

    // Air Ally's "+{regen_per_second_resource} Spirit Regeneration", paid by the module once a second (monk-class.md:
    // the Runic Power slot takes no regeneration aura). `clockMs` carries what is left over; returns the whole seconds
    // to pay now.
    inline unsigned Seconds(std::uint64_t& clockMs, std::uint64_t diffMs)
    {
        clockMs += diffMs;
        unsigned const whole = unsigned(clockMs / 1000);
        clockMs %= 1000;
        return whole;
    }

    // Earth Ally's knock-up on the stock knockback (Unit::KnockbackFrom): the speeds that lift a unit `heightYards` and
    // carry it `yards` away (the core's parabola: height = vz^2 / 2g, distance = 2 * vz / g * vxy, Movement::gravity).
    // The core refuses a horizontal speed of 0.1 or less (MotionMaster::MoveKnockbackFrom), so a knock straight up
    // (the power file's magnitude 0) moves just over it: a hair sideways, no distance anyone sees.
    struct Knock
    {
        double xy = 0, z = 0;
    };
    constexpr double CoreMinimumSpeedXY = 0.1;
    inline Knock KnockUp(double heightYards, double yards, double gravity = 19.29110527038574)
    {
        if (heightYards <= 0)
            return {};
        double const z = std::sqrt(2 * gravity * heightYards);
        double const airborne = 2 * z / gravity;
        return {std::max(CoreMinimumSpeedXY * 1.1, std::max(0.0, yards) / airborne), z};
    }
} // namespace DC::Combat::Monk::MysticAlly
