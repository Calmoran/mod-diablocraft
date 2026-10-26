/*
 * World of DiabloCraft - the family AI's pure rules (monster-families.md section 5 Part 3).
 *
 * What a family monster's ability rows mean, with no world in it: the kinds and triggers, where each number comes from,
 * which ability to run next, and the geometry of a cone, a spread of summons and a charge. dc_family_ai.cpp runs these
 * against creatures; tests/family_ai/harness.cpp compiles this header on its own. Internal to the rifts folder.
 */

#ifndef DC_FAMILY_ABILITY_H
#define DC_FAMILY_ABILITY_H

#include "EventMap.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace DC::Rifts::Family
{
    // The kinds the AI builds (generate_family_ai.py BUILT_KINDS); anything else loads as Held and never runs.
    enum class Kind : std::uint8_t
    {
        MeleeSwing,
        MeleeHeavySlam,
        RangedBolt,
        ProjectileVolley,
        ChanneledBeam,
        ConeBreath,
        GroundHazardDot,
        GroundDetonation,
        ChargeRush,
        LeapSlam,
        SummonMinions,
        SuicideBomb,
        BuffRoar,
        CrowdControlTrap,
        Held
    };

    // generate_family_ai.py TRIGGERS: when an ability may start.
    enum class Trigger : std::uint8_t
    {
        Melee,
        Range,
        Gap,
        Proximity,
        Death,
        Combat,
        Hit,
        None
    };

    inline Kind ParseKind(std::string const& name)
    {
        static char const* const names[] = {
            "melee_swing",    "melee_heavy_slam",  "ranged_bolt",       "projectile_volley", "channeled_beam",
            "cone_breath",    "ground_hazard_dot", "ground_detonation", "charge_rush",       "leap_slam",
            "summon_minions", "suicide_bomb",      "buff_roar",         "crowd_control_trap"};
        for (std::size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i)
            if (name == names[i])
                return static_cast<Kind>(i);
        return Kind::Held;
    }

    inline Trigger ParseTrigger(std::string const& name)
    {
        static char const* const names[] = {"melee", "range", "gap", "proximity", "death", "combat", "hit"};
        for (std::size_t i = 0; i < sizeof(names) / sizeof(names[0]); ++i)
            if (name == names[i])
                return static_cast<Trigger>(i);
        return Trigger::None;
    }

    // The kind's name as the sheets spell it: the suffix of ability_damage_<kind> and ability_default_<kind>_<param>.
    inline char const* KindName(Kind kind)
    {
        static char const* const names[] = {
            "melee_swing",    "melee_heavy_slam",  "ranged_bolt",       "projectile_volley",  "channeled_beam",
            "cone_breath",    "ground_hazard_dot", "ground_detonation", "charge_rush",        "leap_slam",
            "summon_minions", "suicide_bomb",      "buff_roar",         "crowd_control_trap", "held"};
        return names[static_cast<std::size_t>(kind)];
    }

    // One layer of numbers (a cell, a tunable row, a kind default). A number is missing when it is not set.
    struct Layer
    {
        std::optional<double> cooldownS, windupS, rangeMinYd, rangeMaxYd, areaYd, arcDeg, durationS, tickS, speedXy,
            speedZ, count;
    };

    // Field by field, the first layer that has the number: the sheet's own cell, then the ability's tunable row, then
    // the kind's default. A number that is set always wins over the default.
    inline Layer FirstOf(Layer const& a, Layer const& b, Layer const& c)
    {
        auto pick = [](std::optional<double> const& x, std::optional<double> const& y, std::optional<double> const& z)
        { return x ? x : (y ? y : z); };
        return {pick(a.cooldownS, b.cooldownS, c.cooldownS),
                pick(a.windupS, b.windupS, c.windupS),
                pick(a.rangeMinYd, b.rangeMinYd, c.rangeMinYd),
                pick(a.rangeMaxYd, b.rangeMaxYd, c.rangeMaxYd),
                pick(a.areaYd, b.areaYd, c.areaYd),
                pick(a.arcDeg, b.arcDeg, c.arcDeg),
                pick(a.durationS, b.durationS, c.durationS),
                pick(a.tickS, b.tickS, c.tickS),
                pick(a.speedXy, b.speedXy, c.speedXy),
                pick(a.speedZ, b.speedZ, c.speedZ),
                pick(a.count, b.count, c.count)};
    }

    // What the donor spell says about itself (SpellInfo): its cast time and the reach of a direct cast.
    struct Donor
    {
        std::uint32_t spell = 0;
        std::uint32_t castMs = 0;
        double rangeMinYd = 0, rangeMaxYd = 0;
    };

    // One ability, ready to run: every number resolved, in the units the core wants.
    struct Ability
    {
        std::uint32_t seq = 0;
        std::string name;
        Kind kind = Kind::Held;
        Trigger trigger = Trigger::None;
        std::uint32_t spell = 0, summonEntry = 0;
        std::uint32_t cooldownMs = 0, windupMs = 0, durationMs = 0, tickMs = 0, count = 1;
        float minYd = 0, maxYd = 0, areaYd = 0, arcRad = 0, speedXy = 0, speedZ = 0;
        double damageMultiplier = 1.0; // ability_damage_<kind>
        bool direct = false;           // the donor is cast at the target itself, so its own reach limits the window
    };

    inline std::uint32_t Ms(std::optional<double> seconds)
    {
        return seconds && *seconds > 0 ? static_cast<std::uint32_t>(std::llround(*seconds * 1000.0)) : 0;
    }

    // Resolves one ability. `numbers` is FirstOf(cell, tunable, default). A wind-up the row leaves open is the donor's
    // cast time. A direct cast (a bolt, a trap, a channel) cannot start outside the donor's own reach, so its window is
    // clamped to it: the sheet says how far the monster means to shoot, the spell says how far it can.
    inline Ability Resolve(std::uint32_t seq, std::string name, Kind kind, Trigger trigger, Donor const& donor,
                           std::uint32_t summonEntry, std::optional<std::uint32_t> count, Layer const& numbers,
                           double damageMultiplier)
    {
        Ability a;
        a.seq = seq;
        a.name = std::move(name);
        a.kind = kind;
        a.trigger = trigger;
        a.spell = donor.spell;
        a.summonEntry = summonEntry;
        a.damageMultiplier = damageMultiplier;
        a.cooldownMs = Ms(numbers.cooldownS);
        a.windupMs = numbers.windupS ? Ms(numbers.windupS) : donor.castMs;
        a.minYd = static_cast<float>(numbers.rangeMinYd.value_or(0.0));
        a.maxYd = static_cast<float>(numbers.rangeMaxYd.value_or(0.0));
        a.areaYd = static_cast<float>(numbers.areaYd.value_or(0.0));
        a.arcRad = static_cast<float>(numbers.arcDeg.value_or(0.0) * 3.14159265358979323846 / 180.0);
        a.durationMs = Ms(numbers.durationS);
        a.tickMs = std::max<std::uint32_t>(1, Ms(numbers.tickS));
        a.speedXy = static_cast<float>(numbers.speedXy.value_or(0.0));
        a.speedZ = static_cast<float>(numbers.speedZ.value_or(0.0));
        a.count = count ? *count
                        : (numbers.count ? std::max<std::uint32_t>(1, static_cast<std::uint32_t>(*numbers.count)) : 1);
        a.direct = kind == Kind::RangedBolt || kind == Kind::ProjectileVolley || kind == Kind::ChanneledBeam ||
                   kind == Kind::CrowdControlTrap;
        if (a.direct && donor.spell)
        {
            a.minYd = std::max(a.minYd, static_cast<float>(donor.rangeMinYd));
            if (donor.rangeMaxYd > 0)
                a.maxYd = a.maxYd > 0 ? std::min(a.maxYd, static_cast<float>(donor.rangeMaxYd))
                                      : static_cast<float>(donor.rangeMaxYd);
        }
        return a;
    }

    inline bool InWindow(double distance, double minYd, double maxYd)
    {
        return distance >= minYd && (maxYd <= 0 || distance <= maxYd);
    }

    // The brain's timers run on stock EventMap (monster-families.md Part 3, 3.6 b). An ability's cooldown is the event
    // CooldownEvent(index): scheduled while it cools, gone when the ability is ready. EVENT_SCAN is the idle look for a
    // target and EVENT_PHASE the deadline of the wind-up, channel or flight in progress. Tick drains every due event in the
    // same call that advances the clock, so an event still on the map afterwards is in the future.
    constexpr std::uint32_t EVENT_SCAN = 1000, EVENT_PHASE = 1001;
    inline std::uint32_t CooldownEvent(std::size_t index)
    {
        return static_cast<std::uint32_t>(index) + 1;
    }
    inline bool IsReady(EventMap const& events, std::size_t index)
    {
        return !events.HasTimeUntilEvent(CooldownEvent(index));
    }
    inline void StartCooldown(EventMap& events, std::size_t index, std::uint32_t ms)
    {
        if (ms)
            events.RescheduleEvent(CooldownEvent(index), Milliseconds(ms));
        else
            events.CancelEvent(CooldownEvent(index));
    }
    // Advance by `diff` and hand every due event that is not a cooldown to `handle`; a due cooldown just ends.
    template<class Handle>
    void Tick(EventMap& events, std::uint32_t diff, Handle&& handle)
    {
        events.Update(diff);
        while (std::uint32_t const id = events.ExecuteEvent())
            if (id >= EVENT_SCAN)
                handle(id);
    }

    // The next ability to run, or -1. `canTarget(ability)` says whether a target stands where this ability can use it
    // (the world half: a player in the window, in line of sight). Abilities are tried in the sheet's order, so the
    // order of monster_abilities.csv is the priority. The plain swing, the death and hit triggers and the held
    // abilities never start from here.
    template<class CanTarget>
    int Choose(std::vector<Ability> const& abilities, EventMap const& events, CanTarget&& canTarget)
    {
        for (std::size_t i = 0; i < abilities.size(); ++i)
        {
            Ability const& a = abilities[i];
            if (a.kind == Kind::Held || a.kind == Kind::MeleeSwing)
                continue;
            if (a.trigger == Trigger::Death || a.trigger == Trigger::Hit || a.trigger == Trigger::None)
                continue;
            if (!IsReady(events, i))
                continue;
            if (canTarget(a))
                return static_cast<int>(i);
        }
        return -1;
    }

    // A monster's first use of an ability comes somewhere inside its cooldown, so a pack that engages together does not
    // fire in step: `roll` is 0..1.
    inline std::uint32_t FirstReadyAt(std::uint32_t now, std::uint32_t cooldownMs, double roll)
    {
        return now + static_cast<std::uint32_t>(std::clamp(roll, 0.0, 1.0) * cooldownMs);
    }

    // True when (px, py) is inside the cone from (sx, sy) facing `facing`: within `length` and within half of `arcRad`
    // either side of the facing. A zero arc is the whole circle.
    inline bool InCone(double sx, double sy, double facing, double px, double py, double length, double arcRad)
    {
        double const dx = px - sx, dy = py - sy;
        double const distance = std::sqrt(dx * dx + dy * dy);
        if (distance > length)
            return false;
        if (arcRad <= 0 || distance < 1e-6)
            return true;
        double turn = std::fmod(std::atan2(dy, dx) - facing, 2.0 * 3.14159265358979323846);
        if (turn > 3.14159265358979323846)
            turn -= 2.0 * 3.14159265358979323846;
        if (turn < -3.14159265358979323846)
            turn += 2.0 * 3.14159265358979323846;
        return std::fabs(turn) <= arcRad / 2.0 + 1e-9;
    }

    struct Spot
    {
        float x = 0, y = 0;
    };

    // Summon `index` of `count` on a ring of `radius` around (cx, cy), the first at `start` radians.
    inline Spot RingSpot(double cx, double cy, unsigned index, unsigned count, double radius, double start)
    {
        double const angle = start + 2.0 * 3.14159265358979323846 * index / std::max(1u, count);
        return {static_cast<float>(cx + std::cos(angle) * radius), static_cast<float>(cy + std::sin(angle) * radius)};
    }

    // Where a charge ends: on the line from the monster to the target, `reach` yards short of the target, and never
    // behind the start (a target already inside the reach is not charged at).
    inline Spot ChargeEnd(double sx, double sy, double tx, double ty, double reach)
    {
        double const dx = tx - sx, dy = ty - sy;
        double const distance = std::sqrt(dx * dx + dy * dy);
        if (distance <= reach || distance < 1e-6)
            return {static_cast<float>(sx), static_cast<float>(sy)};
        double const f = (distance - reach) / distance;
        return {static_cast<float>(sx + dx * f), static_cast<float>(sy + dy * f)};
    }

    // The monster's damage for an ability: its own swing times the kind's multiplier (monsters.csv
    // ability_damage_<kind>), never negative. The tier and party are already in the swing.
    inline double AbilityDamage(double swing, double multiplier)
    {
        return std::max(0.0, swing * multiplier);
    }

    // The one target picker (conformance C3, D8). Candidates are the valid players in the ability's window. `Victim`
    // is the AI's chase target when it is among them; `Random` any one of them; `Nearest` the closest.
    enum class Rule : std::uint8_t
    {
        Victim,
        Random,
        Nearest
    };

    struct Candidate
    {
        std::uint64_t guid = 0;
        double distance = 0;
        bool victim = false;
    };

    // The index of the pick, or -1 for no candidate. `roll` is 0..1 (only Random uses it); an empty list is -1 for
    // every rule and a Victim rule with the victim out of the list falls back to the nearest.
    inline int PickIndex(std::vector<Candidate> const& candidates, Rule rule, double roll)
    {
        if (candidates.empty())
            return -1;
        auto nearest = [&]()
        {
            std::size_t best = 0;
            for (std::size_t i = 1; i < candidates.size(); ++i)
                if (candidates[i].distance < candidates[best].distance)
                    best = i;
            return static_cast<int>(best);
        };
        switch (rule)
        {
            case Rule::Victim:
                for (std::size_t i = 0; i < candidates.size(); ++i)
                    if (candidates[i].victim)
                        return static_cast<int>(i);
                return nearest();
            case Rule::Random:
                return static_cast<int>(std::min<std::size_t>(
                    candidates.size() - 1, static_cast<std::size_t>(std::clamp(roll, 0.0, 1.0) * candidates.size())));
            case Rule::Nearest:
                return nearest();
        }
        return -1;
    }

    // What a donor spell's effect becomes when the AI casts it (a stock spell cast with our number, 3.1): a damage
    // effect takes the ability's damage if this cast carries it, else zero (a cast that only draws and times a
    // telegraph, or a rider whose hit is ours); any other effect stays the stock spell's own. DonorArgs applies it.
    enum class Carry : std::uint8_t
    {
        Keep,
        OurNumber,
        Zero
    };

    inline Carry CarryOf(bool damageEffect, bool carriesOurNumber)
    {
        return !damageEffect ? Carry::Keep : (carriesOurNumber ? Carry::OurNumber : Carry::Zero);
    }

    // Whether the wind-up cast of an ability carries our number in its damage effect: a bolt, a beam and a trap put the
    // damage in the cast itself. A volley casts each projectile separately with our number, and the rest (a slam, a breath,
    // a blast, a roar) cast the donor for its bar and its look, and the AI deals the damage when the wind-up ends or as a
    // ground effect. Brain::Begin asks this.
    inline bool WindupCarriesOurNumber(Ability const& ability)
    {
        return ability.direct && ability.kind != Kind::ProjectileVolley;
    }
} // namespace DC::Rifts::Family

#endif // DC_FAMILY_ABILITY_H
