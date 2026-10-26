/*
 * Test double for the core's SpellInfo (step 3 harness only).
 *
 * The offline harness compiles the real dc_spell_numbers.cpp against these
 * headers so the accessor's own conversions are what gets tested. Only the
 * members the accessor touches exist here; the spell store is filled from the
 * generated SQL by the harness, not by a running server.
 */
#ifndef DC_TEST_SPELLINFO_H
#define DC_TEST_SPELLINFO_H

#include "DBCStructure.h"
#include <array>
#include <cstdint>

using uint8 = std::uint8_t;
using uint32 = std::uint32_t;
using int32 = std::int32_t;

constexpr std::size_t MAX_SPELL_EFFECTS = 3;

enum Powers { POWER_MANA = 0, POWER_RAGE = 1 };

struct SpellEffectInfo
{
    int32 BasePoints = 0;
    int32 DieSides = 0;
    uint32 Amplitude = 0;
    uint32 ChainTarget = 0;
    SpellRadiusEntry const* RadiusEntry = nullptr;
};

class SpellInfo
{
public:
    uint32 Id = 0;
    uint32 ProcChance = 0;
    uint32 ProcCharges = 0;
    uint32 StackAmount = 0;
    uint32 MaxAffectedTargets = 0;
    uint32 ManaCost = 0;            // Rage units: ten per Fury point (step 5)
    uint32 PowerType = 0;           // Rage divides by ten, Mana is one per point
    uint32 SpellFamilyName = 0;     // the record's SpellClassSet: which class's scale its cost reads at
    uint32 RecoveryTime = 0;          // the skill's own cooldown, ms (step 6)
    uint32 CategoryRecoveryTime = 0;  // the timer its runes share, ms (step 6)
    int32 Duration = 0;             // milliseconds, -1 for infinite
    std::array<SpellEffectInfo, MAX_SPELL_EFFECTS> Effects{};

    int32 GetDuration() const { return Duration; }
};

#endif
