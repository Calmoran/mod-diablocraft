// diablocraft-dupme: the real dc_resource_pulse.h over the generated dc_resource_data.h, no core.
// A pulse loop as dc_resource_pulse.cpp runs it: Units(RateFor(...)) plus Drain(flows), then Step.
// Every number comes from the registry or from argv (test_resource_pulse.py reads the sheets):
// argv[1] combat.resource_pulse_ms, argv[2] and argv[3] the timed decay's combat.csv rate and wait (seconds),
// argv[4..] the Monk's regen_per_second_resource values.
// Prints "cases=N" and exits 0, or names each failing case and exits 1.
#include "../../src/stats/dc_resource_pulse.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <vector>

using namespace DC;
using namespace DC::Stats;

static int failures = 0;
static int cases = 0;

static void expect(bool ok, char const* what, double a = 0, double b = 0)
{
    ++cases;
    if (!ok)
    {
        std::printf("FAIL %s (%g vs %g)\n", what, a, b);
        ++failures;
    }
}

struct Run
{
    std::uint32_t value;
    std::uint32_t biggestStep = 0;
    unsigned moves = 0;
};

// `ms` of pulses `every` apart on one row from `start`, with the row's rate and the flows handed in.
static Run Pulses(Pulse::Inputs const& in, std::uint32_t start, std::uint32_t maximum, double every, double ms,
                  std::vector<Pulse::Flow> flows = {})
{
    Run run{start};
    double fraction = 0;
    for (double done = 0; done + every <= ms + 1e-9; done += every)
    {
        double const units = Pulse::Units(Pulse::RateFor(in), every) + Pulse::Drain(flows, every);
        std::uint32_t const next = Pulse::Step(run.value, maximum, units, fraction);
        std::uint32_t const step = next > run.value ? next - run.value : run.value - next;
        run.biggestStep = std::max(run.biggestStep, step);
        run.moves += step != 0;
        run.value = next;
    }
    return run;
}

int main(int argc, char** argv)
{
    if (argc < 5)
        return 2;
    double const every = std::atof(argv[1]);
    if (every <= 0 || 1000.0 / every != std::floor(1000.0 / every))
        return 2;
    double const pulsesPerSecond = 1000.0 / every;

    // Which rows the pulse pays: the registry's paid_by module, every Rage and Runic Power row among them (the core
    // moves those only every 2 seconds), and an Energy row at its own rate (Wrath, Arcane Power).
    unsigned pulsed = 0;
    Resources::Data::Row const* rage = nullptr;
    Resources::Data::Row const* runic = nullptr;
    Resources::Data::Row const* energy = nullptr;
    for (auto const& row : Resources::Data::Rows)
    {
        expect(Pulse::Pulsed(row) == row.modulePaid, "pulsed exactly the module-paid rows", row.power);
        if (row.power == 1 || row.power == 6)
            expect(Pulse::Pulsed(row), "every Rage and Runic Power row is pulsed", row.power);
        pulsed += Pulse::Pulsed(row);
        if (row.power == 1 && row.decay == Resources::Data::Decay::Stock)
            rage = &row;
        if (row.power == 6 && row.regenPerSecond == 0 && !runic)
            runic = &row;
        if (row.power == Pulse::Energy && Pulse::Pulsed(row) && row.regenPerSecond > 0)
            energy = &row;
    }
    expect(pulsed >= 3 && rage && runic && energy, "a decaying Rage row, a still Runic Power row, a pulsed Energy row");
    if (!rage || !runic || !energy)
        return 1;

    // A Runic Power row with no regeneration and no decay (Spirit, Essence): its maximum is its pool in slot units,
    // a full bar holds and an empty one stays empty.
    std::uint32_t const wholeMax = std::uint32_t(runic->pool * runic->scale);
    expect(Pulses(Pulse::Inputs{runic}, wholeMax, wholeMax, every, 10000).value == wholeMax, "a full bar holds");
    expect(Pulses(Pulse::Inputs{runic}, 0, wholeMax, every, 10000).value == 0, "an empty bar stays empty");

    // Every pulsed row that regenerates (Wrath's 2.5 on Energy; under test_resource_pulse.py's rehearsal the Demon
    // Hunter's Hatred on Energy and Discipline, its second, in Focus): ten seconds from empty pay ten seconds of the
    // sheet's rate, in steps as fine as the pulse allows (a unit at a time while the rate is at most one unit a pulse, the Witch
    // Doctor's Mana at 50 a second a whole share of units a pulse), the same in combat, and it stops at its maximum; its field is the
    // rate, less the native 10 on Energy.
    unsigned regenerators = 0;
    unsigned seconds = 0;
    for (auto const& row : Resources::Data::Rows)
    {
        if (!Pulse::Pulsed(row) || row.regenPerSecond <= 0)
            continue;
        ++regenerators;
        seconds += row.role == Resources::Data::Role::Second;
        std::uint32_t const rowMax = std::uint32_t(row.pool * row.scale);
        double const perSecond = row.regenPerSecond * row.scale;
        Run const filling = Pulses(Pulse::Inputs{&row}, 0, rowMax, every, 10000);
        expect(filling.value == std::uint32_t(10 * perSecond), "ten seconds pay the sheet's rate", filling.value,
               10 * perSecond);
        double const perPulse = perSecond / pulsesPerSecond;
        std::uint32_t const finest = std::uint32_t(std::ceil(perPulse - 1e-9));
        expect(filling.biggestStep == std::max(1u, finest), "a unit at a time, or the whole units a pulse owes", filling.biggestStep, finest);
        expect(filling.moves == (perPulse <= 1.0 ? std::uint32_t(10 * perSecond) : std::uint32_t(10 * pulsesPerSecond)),
               "every pulse moves, a unit at least", filling.moves);
        Pulse::Inputs fightingRow{&row};
        fightingRow.inCombat = true;
        expect(Pulses(fightingRow, 0, rowMax, every, 10000).value == filling.value, "the same in combat");
        expect(Pulses(Pulse::Inputs{&row}, 0, rowMax, every, 1000 * row.pool / row.regenPerSecond + 5000).value == rowMax,
               "it stops at the maximum");
        float const field = Pulse::RegenField(row.power, Pulse::Units(Pulse::RateFor(Pulse::Inputs{&row}), 1000.0));
        expect(field == float(row.power == Pulse::Energy ? perSecond - 10.0 : perSecond),
               "the field is the rate, less Energy's native 10", field, perSecond);
    }
    std::uint32_t const energyMax = std::uint32_t(energy->pool * energy->scale);
    double const energyPerSecond = energy->regenPerSecond * energy->scale;
    expect(Pulses(Pulse::Inputs{energy}, 0, energyMax, every, 10000).value == std::uint32_t(10 * energyPerSecond),
           "the Energy row pays its own rate, not the native 10");
    // The regeneration fields: the rate less Energy's native 10, which the client and the core add back; any
    // other slot the rate itself, negative while it decays.
    expect(Pulse::RegenField(Pulse::Energy, energyPerSecond) == float(energyPerSecond - 10.0),
           "Energy's field is the rate less the native 10", Pulse::RegenField(Pulse::Energy, energyPerSecond));
    expect(Pulse::RegenField(Pulse::Rage, -10.0) == -10.0f, "a decaying Rage field is the loss",
           Pulse::RegenField(Pulse::Rage, -10.0));
    expect(Pulse::RegenField(Pulse::RunicPower, 0.0) == 0.0f, "a still Runic Power field is 0");
    std::uint32_t const rageMax = std::uint32_t(rage->pool * rage->scale);
    std::uint32_t const runicMax = std::uint32_t(runic->pool * runic->scale);

    // The stock loss, out of combat: the core's 20 Rage units per 2 s at its ten units a point, 1 Fury a second,
    // at the row's own scale; each unit its own step.
    double const lossPerSecond = 1.0 * rage->scale;
    Pulse::Inputs out{rage};
    Run const decay = Pulses(out, rageMax, rageMax, every, 4000);
    expect(decay.value == rageMax - std::uint32_t(4 * lossPerSecond), "4 s out of combat lose 4 Fury", decay.value,
           rageMax - 4 * lossPerSecond);
    expect(decay.biggestStep == 1 && decay.moves == std::uint32_t(4 * lossPerSecond), "a unit at a time",
           decay.biggestStep, decay.moves);
    // The loss is a point a second whatever the scale: a row stored ten units a point loses ten units a second.
    Resources::Data::Row tens = *rage;
    tens.scale = 10.0;
    expect(Pulses(Pulse::Inputs{&tens}, 1000, 1000, every, 2000).value == 980, "at ten a point, 20 units in 2 s",
           Pulses(Pulse::Inputs{&tens}, 1000, 1000, every, 2000).value, 980);
    // A realm loss rate carries its fraction: 0.75 is 3 Fury over 4 s, though a pulse is under a unit.
    Pulse::Inputs slow{rage};
    slow.realmLossRate = 0.75;
    Run const slowDecay = Pulses(slow, rageMax, rageMax, every, 4000);
    expect(slowDecay.value == rageMax - std::uint32_t(3 * rage->scale), "a pulse under a unit still adds up",
           slowDecay.value, rageMax - 3 * rage->scale);
    // The core's rule stays: no loss in combat or under an interrupt-regen aura.
    Pulse::Inputs fighting{rage};
    fighting.inCombat = true;
    expect(Pulses(fighting, rageMax, rageMax, every, 4000).value == rageMax, "no loss in combat");
    Pulse::Inputs held{rage};
    held.interrupted = true;
    expect(Pulses(held, rageMax, rageMax, every, 4000).value == rageMax, "no loss under interrupt-regen");
    // The core puts the regen-percent aura on the loss.
    Pulse::Inputs halved{rage};
    halved.auraMultiplier = 0.5;
    expect(Pulses(halved, rageMax, rageMax, every, 4000).value == rageMax - std::uint32_t(2 * rage->scale),
           "the percent aura halves the loss");
    // The timed decay (the Shaman's Maelstrom): the row's own rate, but only once the wait out of combat has passed, and
    // the clock restarts whenever the player is in combat. A pulse loop as dc_resource_pulse.cpp runs it: the clock
    // first (OutOfCombatAfter), then the rate, then Step.
    Resources::Data::Row const* timedRow = nullptr;
    for (auto const& row : Resources::Data::Rows)
        if (row.decay == Resources::Data::Decay::Timed)
            timedRow = &row;
    expect(timedRow && timedRow->power == Pulse::Rage && Pulse::Pulsed(*timedRow), "a timed row, on Rage, paid by the pulse");
    if (!timedRow)
        return 1;
    double const timedPerSecond = std::atof(argv[2]);
    double const timedWaitMs = std::atof(argv[3]) * 1000.0;
    expect(timedPerSecond > 0 && timedWaitMs > 0, "the timed decay has a rate and a wait", timedPerSecond, timedWaitMs);
    std::uint32_t const timedMax = std::uint32_t(timedRow->pool * timedRow->scale);
    // `ms` of pulses from `start`, in combat until `combatMs` has gone by; `mutate` adjusts the inputs of each pulse.
    auto timedRun = [&](double combatMs, double ms, bool interrupted = false, double realmRate = 1.0, double auraMultiplier = 1.0)
    {
        std::uint32_t value = timedMax;
        double fraction = 0, clock = 0, outOfCombat = 0;
        for (double done = 0; done + every <= ms + 1e-9; done += every)
        {
            bool const fightingNow = done < combatMs;
            outOfCombat = Pulse::OutOfCombatAfter(outOfCombat, fightingNow, every);
            Pulse::Inputs in{timedRow};
            in.inCombat = fightingNow;
            in.interrupted = interrupted;
            in.realmLossRate = realmRate;
            in.auraMultiplier = auraMultiplier;
            in.timedPerSecond = timedPerSecond;
            in.timedWaitMs = timedWaitMs;
            in.outOfCombatMs = outOfCombat;
            value = Pulse::Step(value, timedMax, Pulse::Units(Pulse::RateFor(in), every), fraction);
            clock += every;
        }
        return value;
    };
    double const loss = timedPerSecond * timedRow->scale; // slot units a second
    // The wait comes first: a bar left alone for just under the wait is untouched.
    expect(timedRun(0, timedWaitMs - every) == timedMax, "no loss before the wait is over", timedRun(0, timedWaitMs - every), timedMax);
    // Then the rate, a unit at a time: the pulse that ends the wait is the first to pay.
    double const paying = 4000.0;
    std::uint32_t const afterFour = timedRun(0, timedWaitMs + paying);
    std::uint32_t const owed = std::uint32_t(loss * (paying + every) / 1000.0 + 1e-9);
    expect(afterFour == timedMax - owed, "the rate pays from the end of the wait", afterFour, timedMax - owed);
    // In combat the whole time: nothing, however long.
    expect(timedRun(1e9, timedWaitMs + 20000) == timedMax, "no loss in combat");
    // A fight ends: the wait starts over from then, not from the start of the run.
    double const fightMs = 3000.0;
    expect(timedRun(fightMs, fightMs + timedWaitMs - every) == timedMax, "the wait restarts when combat ends",
           timedRun(fightMs, fightMs + timedWaitMs - every), timedMax);
    expect(timedRun(fightMs, fightMs + timedWaitMs + paying) == timedMax - owed, "and the rate pays after it",
           timedRun(fightMs, fightMs + timedWaitMs + paying), timedMax - owed);
    // The core's interrupt-regen aura holds it, as it holds the stock loss.
    expect(timedRun(0, timedWaitMs + paying, true) == timedMax, "no loss under interrupt-regen");
    // The realm's Rage loss rate is the core's own decay's; the timed rate is the row's.
    expect(timedRun(0, timedWaitMs + paying, false, 0.25) == afterFour, "the realm loss rate does not scale it");
    // A drained bar stops at 0.
    expect(timedRun(0, timedWaitMs + 1000.0 * (timedRow->pool / timedPerSecond) + 5000) == 0, "it stops at 0");
    // The field the client moves the bar by is the loss, negative, once it pays; the other rows keep their rate.
    {
        Pulse::Inputs in{timedRow};
        in.timedPerSecond = timedPerSecond;
        in.timedWaitMs = timedWaitMs;
        in.outOfCombatMs = timedWaitMs;
        float const field = Pulse::RegenField(timedRow->power, Pulse::Units(Pulse::RateFor(in), 1000.0));
        expect(field == float(-loss), "the field is the loss once it pays", field, -loss);
    }
    // The rate itself refuses in combat even if a clock past the wait were handed in.
    {
        Pulse::Inputs in{timedRow};
        in.inCombat = true;
        in.timedPerSecond = timedPerSecond;
        in.timedWaitMs = timedWaitMs;
        in.outOfCombatMs = timedWaitMs + 1000;
        expect(Pulse::Units(Pulse::RateFor(in), 1000.0) == 0, "no loss in combat whatever the clock says");
    }
    // The clock itself: in combat it is 0, out of combat it adds up.
    expect(Pulse::OutOfCombatAfter(1234, true, 100) == 0 && Pulse::OutOfCombatAfter(1234, false, 100) == 1334,
           "the out-of-combat clock restarts in combat and adds up out of it");

    // A row that does not decay loses nothing.
    expect(Pulses(Pulse::Inputs{runic}, runicMax, runicMax, every, 2000).value == runicMax, "no decay, no loss");
    // The loss stops at 0 and drops its carry.
    double fraction = -0.5;
    expect(Pulse::Step(0, rageMax, -1.0, fraction) == 0, "nothing below 0");
    expect(Pulse::Step(1, rageMax, -3.0, fraction) == 0 && fraction == 0, "0 is reached and the carry dropped",
           fraction);

    // Regeneration is the same in and out of combat (the core paid Runic Power's aura share only in combat).
    Resources::Data::Row regenerating = *runic;
    regenerating.regenPerSecond = 2.5;
    Pulse::Inputs calm{&regenerating};
    calm.auraPerFive = 50;
    Pulse::Inputs busy = calm;
    busy.inCombat = true;
    Run const calmRun = Pulses(calm, 0, runicMax, every, 2000);
    Run const busyRun = Pulses(busy, 0, runicMax, every, 2000);
    std::uint32_t const calmWanted = std::uint32_t(2 * (2.5 * runic->scale + 50 / 5.0));
    expect(calmRun.value == calmWanted, "regen_per_second x scale and the aura's per-5 s share, out of combat",
           calmRun.value, calmWanted);
    expect(busyRun.value == calmRun.value, "the same in combat", busyRun.value, calmRun.value);
    expect(calmRun.moves == 2 * pulsesPerSecond, "it climbs every pulse", calmRun.moves, 2 * pulsesPerSecond);

    // The regeneration percent auras on the slot but the class's own rate record (the Empowered Shrine's +100) move
    // the regeneration as the core moves Energy's native gain; the record's own share (auraMultiplier only) does not.
    std::uint32_t const energyMaxAll = std::uint32_t(energy->pool * energy->scale);
    Pulse::Inputs shrine{energy};
    shrine.regenAuraMultiplier = 2.0;
    std::uint32_t const doubled = std::uint32_t(2 * 2 * energy->regenPerSecond * energy->scale);
    expect(Pulses(shrine, 0, energyMaxAll, every, 2000).value == std::min(doubled, energyMaxAll),
           "the shrine doubles the regeneration", Pulses(shrine, 0, energyMaxAll, every, 2000).value, doubled);
    Pulse::Inputs ownRecord{energy};
    ownRecord.auraMultiplier = 0.25;
    expect(Pulses(ownRecord, 0, energyMaxAll, every, 2000).value ==
               std::uint32_t(2 * energy->regenPerSecond * energy->scale),
           "the class's own rate record does not slow the row's rate");

    // When each unit lands: Step's whole-unit tolerance must neither hold a unit a pulse late (a share that is no
    // exact binary fraction, 0.1 a pulse, adds up a hair short) nor pay one early. For a rate in milli-units a
    // second, unit k lands on the first pulse n with n x share >= k, worked in integers here; filling and
    // draining both.
    long const everyMs = std::lround(every);
    for (long milliPerSecond : {100L, 300L, 700L, 995L, 1000L, 1500L, 2500L, 3300L, 5000L, 9995L, 10000L})
        for (int sign : {1, -1})
        {
            Resources::Data::Row timed = *runic;
            timed.scale = 1.0;
            timed.regenPerSecond = sign * milliPerSecond / 1000.0;
            std::uint32_t const top = 100000; // far above what 40 s can move, so no bound is reached
            std::uint32_t value = sign > 0 ? 0 : top;
            double carry = 0;
            long const perPulse = milliPerSecond * everyMs; // milli-units x ms: a unit is 1,000,000
            long const pulses = 40L * 1000 / everyMs;
            bool onTime = true;
            long landed = 0;
            for (long n = 1; n <= pulses; ++n)
            {
                std::uint32_t const next =
                    Pulse::Step(value, top, Pulse::Units(Pulse::RateFor(Pulse::Inputs{&timed}), every), carry);
                long const due = n * perPulse / 1000000 - (n - 1) * perPulse / 1000000;
                long const moved = sign > 0 ? long(next) - long(value) : long(value) - long(next);
                onTime &= moved == due;
                landed += moved;
                value = next;
            }
            expect(onTime && landed == pulses * perPulse / 1000000, sign > 0 ? "each unit fills on its own pulse" : "each unit drains on its own pulse",
                   milliPerSecond, landed);
        }

    // The sources' Spirit, handed over as flows: each per-second number pays exactly its units over the
    // second, a pulse's share at a time, and back-to-back seconds climb without a gap.
    for (int i = 4; i < argc; ++i)
    {
        double const perSecond = std::atof(argv[i]);
        double const units = perSecond * runic->scale;
        Run const second = Pulses(Pulse::Inputs{runic}, 0, runicMax, every, 1000, {{units, 1000}});
        expect(second.value == std::uint32_t(units), "a second's flow pays the second's units", second.value, units);
        expect(second.biggestStep <= std::ceil(units / pulsesPerSecond), "a pulse's share at a time",
               second.biggestStep, units / pulsesPerSecond);
        expect(second.moves == pulsesPerSecond || units < pulsesPerSecond, "it climbs every pulse", second.moves);
        Run const two = Pulses(Pulse::Inputs{runic}, 0, runicMax, every, 2000, {{units, 1000}, {units, 2000}});
        expect(two.value == std::uint32_t(2 * units), "overlapping flows each pay all their own", two.value,
               2 * units);
    }
    // A fraction of a unit a pulse carries: 25 units a second at ten pulses is 2.5 a pulse.
    Run const half = Pulses(Pulse::Inputs{runic}, 0, runicMax, every, 1000, {{25, 1000}});
    expect(half.value == 25, "the remainder carries", half.value, 25);
    // A flow stops at the maximum and drops its carry.
    Run const full = Pulses(Pulse::Inputs{runic}, runicMax - 3, runicMax, every, 1000, {{100, 1000}});
    expect(full.value == runicMax, "the maximum holds", full.value, runicMax);
    std::vector<Pulse::Flow> spent{{10, 100}};
    Pulse::Drain(spent, 100);
    expect(spent.empty(), "a paid flow goes", double(spent.size()));

    std::printf("cases=%d failures=%d regenerating=%u second=%u\n", cases, failures, regenerators, seconds);
    return failures ? 1 : 0;
}
