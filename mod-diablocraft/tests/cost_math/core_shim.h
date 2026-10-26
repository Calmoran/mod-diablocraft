/*
 * The scaffolding the core's own spell-modifier arithmetic needs to compile
 * outside the server (spell rewrite step 5, PM correction 4).
 *
 * `scripts/tests/combat/test_cost_math.py` extracts four things verbatim from the core at
 * pin 9d9b604 - with `core-patches/0014` applied or not - and writes them
 * beside this header for it to include:
 *
 *     apply_spell_mod.inc   Player.cpp, Player::ApplySpellMod
 *     spell_mod_enums.inc   SpellDefines.h SpellModOp and MAX_SPELLMOD,
 *                           Player.h SpellModType and SpellModifier
 *     calculate_pct.inc     Util.h CalculatePct
 *
 * so the executable combine is the core's, not a model of it: mutate the
 * patch and the answers change. Everything here is the scaffolding that
 * function needs to link - a Player with the four members it calls, an aura
 * with no charges to drop, a spell manager that answers - plus the clamp a
 * cost goes through afterwards, quoted from SpellInfo::CalcPowerCost at the
 * pin:
 *
 *     // SpellInfo.cpp:2885-2886
 *     if (powerCost < 0)
 *         powerCost = 0;
 */

#ifndef DC_TEST_CORE_SHIM_H
#define DC_TEST_CORE_SHIM_H

#include "../../src/combat/dc_cost_math.h"

#include <cstdint>
#include <unordered_set>
#include <vector>

using int32 = std::int32_t;
using uint32 = std::uint32_t;
using uint8 = std::uint8_t;
#define AC_GAME_API

// The modifier's spell-family mask. The combine never reads it: what does is
// IsAffectedBySpellmod, and that is below.
struct flag96 { };

class Aura
{
public:
    bool IsUsingCharges() const { return false; }
    uint8 GetCharges() const { return 0; }
};

class Spell { };

class SpellInfo
{
public:
    int32 GetDuration() const { return -1; }
};

struct SpellManager
{
    SpellInfo const* GetSpellInfo(uint32) const
    {
        static SpellInfo const info;
        return &info;
    }
};
static SpellManager const* const sSpellMgr = new SpellManager();

#include "spell_mod_enums.inc"
#include "calculate_pct.inc"

class Player
{
public:
    template <class T>
    void ApplySpellMod(uint32 spellId, SpellModOp op, T& basevalue, Spell* spell = nullptr,
                       bool temporaryPet = false);

    // Every modifier these harnesses make is one the record is affected by,
    // on an aura with charges to spare: those two questions are about auras
    // and family masks, not about the arithmetic under test.
    bool IsAffectedBySpellmod(SpellInfo const*, SpellModifier*, Spell*) { return true; }
    bool HasSpellModApplied(SpellModifier*, Spell*) { return true; }
    void ApplyModToSpell(SpellModifier*, Spell*) { }

    Spell* m_spellModTakingSpell = nullptr;
    std::unordered_set<SpellModifier*> m_spellMods[MAX_SPELLMOD];
};

#include "apply_spell_mod.inc"

namespace DCTest
{
    inline SpellModifier* Modifier(SpellModOp op, SpellModType type, int32 value)
    {
        auto* mod = new SpellModifier(new Aura());
        mod->op = op;
        mod->type = type;
        mod->value = value;
        return mod;
    }

    // One cast through the core: the record's Rage units, the player's
    // SPELLMOD_COST auras as whole percent, then CalcPowerCost's clamp.
    inline int32 CostThroughCore(int32 rage, std::vector<double> const& percents)
    {
        Player player;
        for (double percent : percents)
            player.m_spellMods[SPELLMOD_COST].insert(
                Modifier(SPELLMOD_COST, SPELLMOD_PCT,
                         DC::Combat::CostMath::ModifierAmount(percent)));
        int32 cost = rage;
        player.ApplySpellMod(1, SPELLMOD_COST, cost);
        if (cost < 0)
            cost = 0;
        return cost;
    }

    // The same cast worked in ApplySpellMod's float form: the reduced cost before CalcPowerCost's integer drops its
    // part below a unit (the module's cost carry, dc_classes.cpp CostFraction, works it this way).
    inline float ExactCostThroughCore(int32 rage, std::vector<double> const& percents)
    {
        Player player;
        for (double percent : percents)
            player.m_spellMods[SPELLMOD_COST].insert(
                Modifier(SPELLMOD_COST, SPELLMOD_PCT,
                         DC::Combat::CostMath::ModifierAmount(percent)));
        float cost = float(rage);
        player.ApplySpellMod(1, SPELLMOD_COST, cost);
        return cost < 0 ? 0.0f : cost;
    }

    // One cast with a flat cost reduction beside a percentage one, as Prism and
    // Power of the Storm give a Wizard: D3 takes the percentage off first and
    // subtracts the flat amount after (docs/research/d3-cost-cooldown-math.md 2.2).
    inline int32 CostFlatThroughCore(int32 cost, int32 flat, double percent)
    {
        Player player;
        player.m_spellMods[SPELLMOD_COST].insert(Modifier(SPELLMOD_COST, SPELLMOD_FLAT, flat));
        player.m_spellMods[SPELLMOD_COST].insert(
            Modifier(SPELLMOD_COST, SPELLMOD_PCT, DC::Combat::CostMath::ModifierAmount(percent)));
        int32 value = cost;
        player.ApplySpellMod(1, SPELLMOD_COST, value);
        if (value < 0)
            value = 0;
        return value;
    }

    // What the module's CostReductionFactor reads back: the same probe cost
    // through the same modifiers.
    inline double FactorThroughCore(std::vector<double> const& percents)
    {
        return DC::Combat::CostMath::Factor(
            CostThroughCore(DC::Combat::CostMath::COST_PROBE, percents));
    }

    // One cooldown through the core: a flat reduction and a percentage one.
    inline int32 CooldownThroughCore(int32 milliseconds, int32 flat, double percent)
    {
        Player player;
        player.m_spellMods[SPELLMOD_COOLDOWN].insert(
            Modifier(SPELLMOD_COOLDOWN, SPELLMOD_FLAT, flat));
        player.m_spellMods[SPELLMOD_COOLDOWN].insert(
            Modifier(SPELLMOD_COOLDOWN, SPELLMOD_PCT,
                     DC::Combat::CostMath::ModifierAmount(percent)));
        int32 value = milliseconds;
        player.ApplySpellMod(1, SPELLMOD_COOLDOWN, value);
        return value;
    }

    // One duration through the core (step 8). The percentage is the record's
    // own amount and positive, because Inspiring Presence lengthens; nothing
    // is clamped on the way in, so a mutation of the record's base points
    // shows up here as a different answer.
    inline int32 DurationThroughCore(int32 milliseconds, int32 percent)
    {
        Player player;
        player.m_spellMods[SPELLMOD_DURATION].insert(
            Modifier(SPELLMOD_DURATION, SPELLMOD_PCT, percent));
        int32 value = milliseconds;
        player.ApplySpellMod(1, SPELLMOD_DURATION, value);
        return value;
    }
}

#endif // DC_TEST_CORE_SHIM_H
