/*
 * World of DiabloCraft - the chance an on-hit effect procs.
 *
 * D3 rolls a proc at the proc coefficient of the skill (and rune) that landed
 * the hit: Bash 1.0 always, Whirlwind 0.13 about one hit in eight. The sheets
 * carry that number as `proc_coefficient` (*_skill_values.csv, read back with
 * Numbers::Get, so a rune answers with its own or its skill's).
 *
 * A hit whose spell states no coefficient - a pet's, an item's, a proc that
 * came from another proc - cannot proc. It is never treated as 1: an unknown
 * source must not be the strongest one (proc
 * coefficients). Only a spell that lists a coefficient rolls at all.
 *
 * A header with no core dependency, so scripts/tests/combat/test_proc_coefficients.py can
 * compile this exact function and drive it with the generated value.
 */

#ifndef DC_PROC_MATH_H
#define DC_PROC_MATH_H

#include <optional>

namespace DC::Combat::Proc
{
    // Percent chance for a hit whose skill states this coefficient. No
    // coefficient is no chance.
    inline float ChancePct(std::optional<double> coefficient)
    {
        if (!coefficient || *coefficient <= 0)
            return 0.0f;
        return float(*coefficient * 100.0);
    }

    // A gem's "N% chance on hit" (legendary gems): the stated chance, scaled by the coefficient of the
    // skill that landed the hit, like every chance-on-hit in D3. Same rule as above for a hit that states none.
    inline float ChancePct(std::optional<double> coefficient, double basePct)
    {
        if (!coefficient || *coefficient <= 0 || basePct <= 0)
            return 0.0f;
        return float(*coefficient * basePct);
    }

    template <typename Roll>
    inline bool Rolls(std::optional<double> coefficient, double basePct, Roll&& roll)
    {
        float chance = ChancePct(coefficient, basePct);
        return chance > 0.0f && roll(chance);
    }

    // `roll` takes a percent and answers whether it fell (the core's
    // roll_chance_f). A hit with no coefficient never reaches it.
    template <typename Roll>
    inline bool Rolls(std::optional<double> coefficient, Roll&& roll)
    {
        float chance = ChancePct(coefficient);
        return chance > 0.0f && roll(chance);
    }

    // The coefficient the hit landing now rolls: a pet's blow rolls its own melee attack's (a pet whose attack states none rolls none,
    // never its owner's skill's), every other hit its spell's.
    inline std::optional<double> Landing(bool petBlow, std::optional<double> petCoefficient, std::optional<double> spellCoefficient)
    {
        return petBlow ? petCoefficient : spellCoefficient;
    }

    // An amount a landed hit pays or heals every time (a rune's "attacks you make generate N of the resource", a heal "for up to
    // N% of Life"): the stated amount scaled by the coefficient of the skill that landed the hit, as D3 scales every effect on
    // hit. A hit that states none pays nothing, the same rule as the chance above.
    inline double Scaled(std::optional<double> coefficient, double amount)
    {
        if (!coefficient || *coefficient <= 0 || amount <= 0)
            return 0.0;
        return amount * *coefficient;
    }
}

#endif
