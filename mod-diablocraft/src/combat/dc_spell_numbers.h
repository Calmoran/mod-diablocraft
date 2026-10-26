/*
 * World of DiabloCraft - the numbers, read out of the spell records.
 *
 * Every number the barbarian sheets name lives in a spell record: a base
 * point, a duration row, a radius row, a proc chance, a stack count. This is
 * the one way to read one back. `dc_spell_values.h` says, for each (spell,
 * token), which record holds it and how; this turns that into a value.
 *
 * The handful of numbers no record field can hold exactly - the cooldown
 * numbers, Whirlwind's per-tick Fury cost, five radii with no
 * stock SpellRadius row, two fractions - are the exceptions, and only those
 * come from the dc_spell_values table.
 *
 * A rune is its base skill plus its change, so a
 * rune answers for the numbers its skill states and it does not restate.
 * `Get` gives that effective value; `Own` and `Inherited` keep the two apart
 * where a call site means one and not the other, which is what the positional
 * tables' `r->n[k]` and `b->n[k]` used to say.
 */

#ifndef DC_SPELL_NUMBERS_H
#define DC_SPELL_NUMBERS_H

#include <cstddef>
#include <cstdint>
#include <optional>
#include <string_view>

namespace DC::Combat::Numbers
{
    // The value this spell answers with: its own if it states the token,
    // otherwise the one it inherits from its base skill.
    std::optional<double> Get(uint32_t spell, std::string_view token,
                              std::string_view qualifier = {});

    // Only what this row states itself.
    std::optional<double> Own(uint32_t spell, std::string_view token,
                              std::string_view qualifier = {});

    // Only what it takes from its base skill.
    std::optional<double> Inherited(uint32_t spell, std::string_view token,
                                    std::string_view qualifier = {});

    // Get() or zero, for a call site that has already proven the token is
    // there. A miss is logged once per (spell, token) rather than every tick.
    double Num(uint32_t spell, std::string_view token, std::string_view qualifier = {});

    bool Has(uint32_t spell, std::string_view token, std::string_view qualifier = {});

    // The exact-value table. Loaded on first use; call this from a startup
    // hook once a call site needs it before the first read.
    void Load();
    std::size_t ExactCount();
}

#endif
