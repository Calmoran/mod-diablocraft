#pragma once
// Way of the Hundred Fists' rules that need no core type, header-only so
// tests/monk_hundred_fists compiles this exact code. The combo counter is dc_monk_fists.h's `Combo`, one instance
// per skill (this skill's own state, never Fists of Thunder's); what is here is what the stages and runes add to it.
#include "dc_monk_fists.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

namespace DC::Combat::Monk::HundredFists
{
    // Power/Monk_WayOfTheHundredFists.pow: stage 1 hits one target, stage 2 is a cone with `hits` punches, stage 3 an
    // area. The sheet's damage_pct is the TOTAL of the stage-2 series (SF_1 0.2714 x SF_27 7 = 1.9; Hands of Lightning
    // SF_12 0.4231 x 10 = 4.23), so each of its punches deals the total divided by the hit count.
    inline unsigned StageHits(unsigned stage, bool handsOfLightning, unsigned baseHits, unsigned upgradedHits)
    {
        if (stage != 2)
            return 1;
        return std::max(1u, handsOfLightning ? upgradedHits : baseHits);
    }

    inline double HitPct(unsigned stage, double totalPct, unsigned hits)
    {
        return stage == 2 && hits ? totalPct / hits : totalPct;
    }

    // Stage 3's area (SF_30 radius, SF_31 "aoe offset forward"): a circle whose centre lies `offsetYards` in front of
    // the Monk along `facing` (radians, WoW's orientation: 0 along +x, counter-clockwise).
    struct Point
    {
        double x = 0, y = 0;
    };
    inline Point AoeCentre(Point monk, double facing, double offsetYards)
    {
        return {monk.x + std::cos(facing) * offsetYards, monk.y + std::sin(facing) * offsetYards};
    }
    inline bool InCircle(Point centre, double radiusYards, Point at)
    {
        return std::hypot(at.x - centre.x, at.y - centre.y) <= radiusYards;
    }

    // The wave of Windforce Flurry ("enemies directly ahead of you"): a strip `length` yards long and `width` wide that
    // starts at the Monk and runs along `facing`.
    inline bool InStrip(Point monk, double facing, double lengthYards, double widthYards, Point at)
    {
        double const dx = at.x - monk.x, dy = at.y - monk.y;
        double const along = dx * std::cos(facing) + dy * std::sin(facing);
        double const across = -dx * std::sin(facing) + dy * std::cos(facing);
        return along >= 0 && along <= lengthYards && std::fabs(across) <= widthYards / 2;
    }

    // Blazing Fists: "Critical Hits increase your attack speed and movement speed by {attack_speed_pct} for
    // {duration_seconds} seconds. This effect can stack up to {max_stacks_count} times." Each crit adds a stack and
    // renews the whole buff's time (d3planner addBuff, as dc_monk_effects.h's Book does).
    struct Stacked
    {
        unsigned stacks = 0;
        std::uint64_t until = 0; // ms

        unsigned Add(std::uint64_t now, std::uint64_t durationMs, unsigned cap)
        {
            if (now >= until)
                stacks = 0;
            stacks = std::min(stacks + 1, std::max(1u, cap));
            until = now + durationMs;
            return stacks;
        }

        // True when the buff has run out at `now` and was not renewed: the removal that was scheduled is still due.
        bool Over(std::uint64_t now) const
        {
            return now >= until;
        }
    };

    // Fists of Fury: "enemies hit take an additional {damage_pct} weapon damage as Holy over {dot_duration_seconds}
    // seconds. Fists of Fury damage can stack multiple times on the same enemy." One stack per hit; the power file
    // caps them (SF_17) and ticks every SF_18 seconds. At the cap a new hit replaces the OLDEST stack (the sheets
    // say nothing about the refresh: a question in the report). A tick pays each stack the share of its total that
    // falls inside the time since the last tick, so a late tick never loses damage and the total is the sheet's.
    struct FuryStacks
    {
        std::vector<std::uint64_t> ends; // ms at which each running stack ends, oldest first

        void Add(std::uint64_t now, std::uint64_t durationMs, unsigned cap)
        {
            ends.erase(std::remove_if(ends.begin(), ends.end(), [now](std::uint64_t end) { return end <= now; }), ends.end());
            if (cap == 0)
                return;
            if (ends.size() >= cap)
                ends.erase(ends.begin());
            ends.push_back(now + durationMs);
        }

        unsigned Count(std::uint64_t now) const
        {
            return unsigned(std::count_if(ends.begin(), ends.end(), [now](std::uint64_t end) { return end > now; }));
        }

        // Weapon-damage percent owed for the time from `previous` to `now`; the stacks that ended are dropped.
        double Pay(std::uint64_t previous, std::uint64_t now, double totalPct, std::uint64_t durationMs)
        {
            double pct = 0;
            if (durationMs && now > previous)
                for (std::uint64_t end : ends)
                {
                    std::uint64_t const start = end > durationMs ? end - durationMs : 0;
                    std::uint64_t const from = std::max(start, previous), to = std::min(end, now);
                    if (to > from)
                        pct += totalPct * double(to - from) / double(durationMs);
                }
            ends.erase(std::remove_if(ends.begin(), ends.end(), [now](std::uint64_t end) { return end <= now; }), ends.end());
            return pct;
        }
    };
} // namespace DC::Combat::Monk::HundredFists
