#pragma once
// Crippling Wave's rules that need no core type, header-only so
// tests/monk_crippling_wave compiles this exact code. The combo is Fists of Thunder's (dc_monk_fists.h Combo,
// one counter per skill and its runes); what is here is the geometry numbers and the Spirit.
#include <cmath>
#include <cstdint>
#include <optional>
#include <vector>

class Player;
class Unit;

namespace DC::Combat::Monk::Wave
{
    // "Every third hit also dazes enemies within {radius_yards} yards": the stage that carries the daze, the freeze and
    // the rune's longer reach.
    inline bool IsThird(unsigned stage)
    {
        return stage == 3;
    }

    // How far the wave reaches at `stage`: the targeting sheet's `baseYards` (11), and for the third attack Tsunami's
    // own radius_yards (17), when the rune states one. A rune that states none (runeYards 0) keeps the base.
    inline double Reach(unsigned stage, double baseYards, double runeYards)
    {
        return IsThird(stage) && runeYards > baseYards ? runeYards : baseYards;
    }

    // The front arc, in the radians the core's HasInArc takes, from degrees (Power/Monk_CripplingWave.pow SF_6 180).
    inline double ArcRadians(double degrees)
    {
        return degrees * 3.14159265358979323846 / 180.0;
    }

    // Rising Tide: "Each enemy hit generates {generated_resource} additional Spirit", on top of the attack's own pay.
    inline double RisingTideSpirit(double perEnemy, unsigned enemiesHit)
    {
        return perEnemy > 0 ? perEnemy * enemiesHit : 0.0;
    }

    // The core's aura amount for a slow of `pct` percent (negative: it slows).
    inline int SlowAmount(double pct)
    {
        return -static_cast<int>(std::lround(pct));
    }

    // The production half (dc_monk_crippling_wave.cpp), called from dc_monk.cpp beside Fists of Thunder's.
    bool Is(std::uint32_t spellId);
    // The Spirit one attack pays: the skill's own number, which Rising Tide's "additional" row does not replace.
    std::optional<double> PerAttack(std::uint32_t spellId);
    // One swing of the skill or a rune, decided before it hits: the combo advances, the stage (1 to 3) comes back.
    unsigned Begin(Player* player, std::uint32_t spellId);
    // The swing resolved: `targets` are the enemies its cone struck.
    void Cast(Player* player, std::uint32_t spellId, std::vector<Unit*> const& targets, unsigned stage);
} // namespace DC::Combat::Monk::Wave
