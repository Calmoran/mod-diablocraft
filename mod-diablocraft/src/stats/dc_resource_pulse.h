#pragma once
// The resource pulse: resource power must not come back in chunks. In D3 it's a
// smooth flowing increase/decrease.
//
// The core moves Rage and Runic Power once every 2 seconds (Player::RegenerateAll,
// pinned core Player.cpp:1835-1847), so a resource stored there (class_resources.csv)
// stepped by two seconds' worth at a time, and the class passives and Mantras that
// regenerate one paid it a second at a time. Energy moves every update, but only
// reaches the client with the 2-second send (Player::Regenerate, Player.cpp:2017-2020).
// The module pays every resource the registry gives it (paid_by module) itself,
// every combat.resource_pulse_ms: rate x elapsed with the fraction carried, sent
// when the whole value moves, and a hidden record keeps the core's own tick off
// the slot (generate_spells.py REGENERATION_MASK). It also writes the rate into
// the slot's two regeneration fields, the ones a client reads to move a bar
// between server values. The arithmetic is here, with no core include, so
// tests/resource_pulse compiles it alone; dc_resource_pulse.cpp is the player hook
// around it.
#include "../classes/dc_resource_data.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

class Player;

namespace DC::Resources
{
    // A source that used to pay `points` at once (a passive's second, a Mantra's
    // pulse) hands them to the pulse instead, which pays them evenly over the next
    // `overMs`: the same points, as a flow. Only for a resource of the player's
    // own class that it shows, as the class code's own gains are. dc_resource_pulse.cpp.
    void Flow(Player* player, Data::Row const& r, double points, std::uint32_t overMs);
} // namespace DC::Resources

namespace DC::Stats::Pulse
{
    // The pinned core's Powers values (SharedDefines.h).
    constexpr std::uint8_t Rage = 1;
    constexpr std::uint8_t Energy = 3;
    constexpr std::uint8_t RunicPower = 6;
    // The rows the pulse pays: the registry's paid_by module.
    inline bool Pulsed(Resources::Data::Row const& r)
    {
        return r.modulePaid;
    }

    // What the slot's UNIT_FIELD_POWER_REGEN_FLAT_MODIFIER and _INTERRUPTED_ fields
    // hold for a rate of `unitsPerSecond` (negative while it decays): the rate in
    // slot units a second, less the native 10 Energy gains by itself, which the
    // core and the client add back to Energy's field (Player::UpdateEnergyRegen,
    // StatSystem.cpp; Player::Regenerate, Player.cpp:1950). The same in and out of
    // combat: D3 has no five-second rule.
    inline float RegenField(std::uint8_t power, double unitsPerSecond)
    {
        return static_cast<float>(power == Energy ? unitsPerSecond - 10.0 : unitsPerSecond);
    }

    // The slot's stock out-of-combat loss in points a second, before the
    // realm's Rate.Rage.Loss / Rate.RunicPower.Loss: the core's 20 Rage and 30
    // Runic Power per 2-second tick (Player.cpp:1937, :1956) at the core's ten
    // units a point, 1 and 1.5 a second; a row pays it at its own scale. Not a
    // tuning number.
    inline double StockLossPerSecond(std::uint8_t power)
    {
        return power == Rage ? 1.0 : power == RunicPower ? 1.5 : 0.0;
    }

    // Gains paid for and not yet handed out: each pays the same share of what it
    // has left for each millisecond it has left.
    struct Flow
    {
        double units;
        double ms;
    };

    // What the flows pay over `elapsedMs`; a flow whose time is up has paid all
    // of it and goes.
    inline double Drain(std::vector<Flow>& flows, double elapsedMs)
    {
        double paid = 0;
        for (Flow& flow : flows)
        {
            double const share = flow.ms <= elapsedMs ? flow.units : flow.units * elapsedMs / flow.ms;
            paid += share;
            flow.units -= share;
            flow.ms -= elapsedMs;
        }
        flows.erase(std::remove_if(flows.begin(), flows.end(), [](Flow const& flow) { return flow.ms <= 0; }),
                    flows.end());
        return paid;
    }

    // One resource's steady rate, in slot units: the core's own terms for the
    // slot, without its in-combat-only rule for Runic Power's aura share (D3
    // regenerates the same in and out of combat).
    struct Rate
    {
        double regenPerSecond = 0;  // the class's regen_per_second plus the sheet's, x scale
        double regenMultiplier = 1; // SPELL_AURA_MOD_POWER_REGEN_PERCENT on the slot but the class's own rate record
        double auraPerFive = 0;     // SPELL_AURA_MOD_POWER_REGEN on the slot, per 5 seconds as the core reads it
        double lossPerSecond = 0;   // the stock loss when the row decays and the player is out of combat, else 0
        double lossMultiplier = 1;  // SPELL_AURA_MOD_POWER_REGEN_PERCENT on the slot, which the core puts on the loss
    };

    // What the player's state gives the rate. The loss is the core's rule (out of
    // combat, no interrupt-regen aura) for a row whose decay is the slot's stock
    // one, or the row's own rate after its wait for a timed one; the regeneration
    // has no combat rule at all.
    struct Inputs
    {
        Resources::Data::Row const* row = nullptr;
        double auraPerFive = 0;    // GetTotalAuraModifierByMiscValue(SPELL_AURA_MOD_POWER_REGEN, slot)
        double auraMultiplier = 1; // GetTotalAuraMultiplierByMiscValue(SPELL_AURA_MOD_POWER_REGEN_PERCENT, slot)
        // The same without the class's energy-rate record (Combat::Shells::EnergyRateFor), which sets the core's
        // native Energy gain to the row's rate; the pulse pays the row's rate itself, so only the other percent auras
        // (the Empowered Shrine's) move it, as they move the core's native gain (Player::UpdateEnergyRegen).
        double regenAuraMultiplier = 1;
        bool inCombat = false;
        bool interrupted = false;  // HasInterruptRegenAura()
        double realmLossRate = 1;  // Rate.Rage.Loss or Rate.RunicPower.Loss
        double sheetPerSecond = 0; // points a second the sheet adds to this resource (Readers::RegenPerSecond: spiritregen, manaregen)
        // A timed decay (Decay::Timed): the row's two combat.csv tunables, and how long the player has been out of combat.
        double timedPerSecond = 0;
        double timedWaitMs = 0;
        double outOfCombatMs = 0;
    };

    // Milliseconds out of combat after a pulse of `elapsedMs`: the clock restarts whenever the player is in combat.
    inline double OutOfCombatAfter(double previousMs, bool inCombat, double elapsedMs)
    {
        return inCombat ? 0.0 : previousMs + elapsedMs;
    }
    inline Rate RateFor(Inputs const& in)
    {
        Rate rate;
        rate.regenPerSecond = (in.row->regenPerSecond + in.sheetPerSecond) * in.row->scale;
        rate.regenMultiplier = in.regenAuraMultiplier;
        rate.auraPerFive = in.auraPerFive;
        rate.lossMultiplier = in.auraMultiplier;
        if (in.row->decay == Resources::Data::Decay::Stock && !in.inCombat && !in.interrupted)
            rate.lossPerSecond = StockLossPerSecond(in.row->power) * in.row->scale * in.realmLossRate;
        // A timed decay is the row's own rate, from the moment the wait out of combat has passed; the realm's loss rate
        // is the core's rule for its own decay and does not scale it.
        if (in.row->decay == Resources::Data::Decay::Timed && !in.inCombat && !in.interrupted &&
            in.outOfCombatMs >= in.timedWaitMs)
            rate.lossPerSecond = in.timedPerSecond * in.row->scale;
        return rate;
    }

    // Units over `elapsedMs` (negative while it decays).
    inline double Units(Rate const& rate, double elapsedMs)
    {
        return (rate.regenPerSecond * rate.regenMultiplier + rate.auraPerFive / 5.0 -
                rate.lossPerSecond * rate.lossMultiplier) *
               elapsedMs / 1000.0;
    }

    // The core's m_powerFraction step (Player::Regenerate, Player.cpp:1980-2020):
    // whole units move, the rest carries to the next pulse; at 0 or the maximum
    // the carry is dropped, and nothing moves toward a bound already reached.
    inline std::uint32_t Step(std::uint32_t current, std::uint32_t maximum, double units, double& fraction)
    {
        if (units == 0 || (units < 0 && current == 0) || (units > 0 && current >= maximum))
            return current;
        double const total = units + fraction;
        // A rate whose pulse share is no exact binary fraction (1/s at 100 ms is 0.1 a pulse) adds up a hair short of
        // the whole unit it has paid; the tolerance, far under a unit, keeps that unit from coming a pulse late.
        auto const whole = static_cast<std::uint32_t>(std::fabs(total) + 1e-9);
        if (total < 0)
        {
            if (current > whole)
            {
                fraction = total + whole;
                return current - whole;
            }
            fraction = 0;
            return 0;
        }
        if (current + whole >= maximum)
        {
            fraction = 0;
            return maximum;
        }
        fraction = total - whole;
        return current + whole;
    }
} // namespace DC::Stats::Pulse
