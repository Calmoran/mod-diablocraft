/*
 * VictimAdjustedTotal re-reads the victim's debuffs for a hit that is not fixed (a Rend tick, a splash retarget,
 * a DealHit with fixed == false) and swaps the bonus the hit snapshotted for the bonus now. ComputeHit snapshots
 * five terms in hit.targetBonus; the re-read must add the same five back, or the hit loses the one it forgot.
 *
 * REAL here, cut out of the module's own files by scripts/tests/combat/test_victim_adjusted_total.py and not
 * copied: Hit and VictimAdjustedTotal.
 *
 * DOUBLES: the units, and each term's reader (a settable number per term; the readers' own math has its tests).
 *
 * Not covered: that ComputeHit and the re-read name the same readers (the Python test compares the two lists in
 * the source), and the in-game hit (docs/test-diablocraft-mhqha.md).
 */

#include <cmath>
#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

class Player;
class Unit;

#include "../../src/combat/dc_damage_buckets.h"

namespace
{
    // One number per reader of a victim term.
    double g_primaries = 0, g_abilities = 0, g_wizard = 0, g_monk = 0, g_gem = 0;
} // namespace

namespace DC::Combat
{
    namespace Primaries
    {
        inline double TargetBonus(Unit*)
        {
            return g_primaries;
        }
    } // namespace Primaries
    namespace Abilities
    {
        inline double TargetBonus(Unit*)
        {
            return g_abilities;
        }
    } // namespace Abilities
    namespace Wizard
    {
        inline double TargetBonus(Player*, Unit*, unsigned)
        {
            return g_wizard;
        }
        inline double TargetFactor(Player*, Unit*)
        {
            return 1;
        }
    } // namespace Wizard
    namespace Monk
    {
        inline double TargetBonus(Player*, Unit*)
        {
            return g_monk;
        }
    } // namespace Monk
    namespace GemPowers
    {
        inline double TargetBonus(Unit*)
        {
            return g_gem;
        }
    } // namespace GemPowers
} // namespace DC::Combat

#include "dc_victim_adjusted_total_extract.h"

namespace
{
    using DC::Combat::Hit;

    int failures = 0;

    void Check(bool ok, std::string const& what)
    {
        if (!ok)
        {
            std::cerr << "FAIL: " << what << "\n";
            ++failures;
        }
    }

    bool Near(double a, double b)
    {
        return std::fabs(a - b) < 1e-9;
    }

    struct Term
    {
        char const* name;
        double* value;
    };

    void ClearTerms()
    {
        g_primaries = g_abilities = g_wizard = g_monk = g_gem = 0;
    }

    // The hit as ComputeHit leaves it: targetBonus the sum of the five readers, the pool 1 + (gear + targetBonus) /
    // 100.
    Hit Snapshot(double total, double gearPoolPct)
    {
        Hit hit;
        hit.targetBonus = g_primaries + g_abilities + g_wizard + g_monk + g_gem;
        hit.additive = DC::Combat::Additive(gearPoolPct + hit.targetBonus);
        hit.targetFactor = 1;
        hit.total = total;
        return hit;
    }
} // namespace

int main()
{
    Term const terms[] = {{"Primaries", &g_primaries},
                          {"Abilities", &g_abilities},
                          {"Wizard", &g_wizard},
                          {"Monk", &g_monk},
                          {"GemPowers", &g_gem}};
    double const total = 1000, gear = 50;

    for (Term const& term : terms)
    {
        // The victim is the same one the hit read: nothing changed, so the total is what the hit computed.
        ClearTerms();
        *term.value = 10;
        Hit hit = Snapshot(total, gear);
        Check(Near(DC::Combat::VictimAdjustedTotal(nullptr, nullptr, hit), total),
              std::string(term.name) + ": an unchanged victim keeps the hit's total");

        // The debuff lands after the snapshot: +10 points on the same pool.
        ClearTerms();
        hit = Snapshot(total, gear);
        *term.value = 10;
        Check(
            Near(DC::Combat::VictimAdjustedTotal(nullptr, nullptr, hit), total * (hit.additive + 0.10) / hit.additive),
            std::string(term.name) + ": a debuff that landed after the snapshot raises the total");

        // The debuff ended after the snapshot: the 10 points leave the pool.
        ClearTerms();
        *term.value = 10;
        hit = Snapshot(total, gear);
        ClearTerms();
        Check(
            Near(DC::Combat::VictimAdjustedTotal(nullptr, nullptr, hit), total * (hit.additive - 0.10) / hit.additive),
            std::string(term.name) + ": a debuff that ended after the snapshot lowers the total");
    }

    // All five at once, as a Toxin-poisoned, Mantra-marked elite would carry them.
    ClearTerms();
    g_primaries = 1;
    g_abilities = 2;
    g_wizard = 3;
    g_monk = 4;
    g_gem = 10;
    Hit const all = Snapshot(total, gear);
    Check(Near(DC::Combat::VictimAdjustedTotal(nullptr, nullptr, all), total),
          "all five terms: an unchanged victim keeps the total");

    if (failures)
        return 1;
    std::cout << "ok\n";
    return 0;
}
