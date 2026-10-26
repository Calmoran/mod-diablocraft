#pragma once
// The rules of the Witch Doctor's passives that need no core type, header-only so tests/witch_doctor_passives compiles
// this exact code: Jungle Fortitude's reduction, Circle of Life's range and roll, Spiritual Attunement's pool and
// regeneration, Gruesome Feast's share of the pool, Blood Ritual's payment in Life and Bad Medicine's school. The
// production half is dc_witch_doctor_passives.cpp.
#include <algorithm>
#include <cstdint>

namespace DC::Combat::WitchDoctor::Passive
{
    // `pct` percent of `maximum`: a share of a pool (Gruesome Feast's Mana, Spiritual Attunement's regeneration, Blood
    // Ritual's Life a second). Nothing for no pool or a percent that is not positive.
    inline double Share(double maximum, double pct)
    {
        return maximum > 0 && pct > 0 ? maximum * pct / 100.0 : 0.0;
    }

    // Jungle Fortitude: "Reduce all damage taken ... by {damage_reduction_pct}": `damage` after the share, never below
    // nothing, and a share past a hundred takes all of it.
    inline double Reduced(double damage, double pct)
    {
        return damage > 0 ? damage * (1.0 - std::clamp(pct, 0.0, 100.0) / 100.0) : 0.0;
    }

    // Spiritual Attunement: "Maximum Mana is increased by {max_pool_pct}": the points the passive adds, a share of the
    // pool without its own bonus (`sheetMax` is the sheet's maximum with `applied` already in it).
    inline double PoolBonus(double sheetMax, double applied, double pct)
    {
        return Share(sheetMax - applied, pct);
    }

    // A chance in percent held by a roll in [0, 100): a chance of 0 never, of 100 always.
    inline bool Procs(double roll, double chancePct)
    {
        return roll < chancePct;
    }

    // Circle of Life: "When an enemy dies within {radius_yards} yards ... The range of this effect is increased by your
    // gold pickup radius": the distance from the Witch Doctor to the enemy that died, and the pickup radius as the
    // sheet has it.
    inline bool InRange(double distance, double radius, double pickup)
    {
        return radius > 0 && distance <= radius + std::max(0.0, pickup);
    }

    // Bad Medicine: "When you deal Poison damage": a spell record of the Poison school (the module's Poison is the
    // shadow mask).
    inline bool PoisonMask(std::uint32_t schoolMask)
    {
        return (schoolMask & 32u) != 0;
    }

    // Blood Ritual: "{resource_cost_share_pct} of Mana costs are paid with Life". What a cast of `costPoints` Mana
    // gives back in Mana and takes in Life.
    struct Payment
    {
        double manaBack = 0; // Mana returned to the pool
        double life = 0;     // Life taken
    };

    // The share of the cost is the same fraction of the Life pool as it is of the Mana pool (a cost's fraction is the
    // engine's way across pools), times `scale`; Life never goes below 1 for it, and what Life cannot pay stays a Mana
    // cost.
    inline Payment Sacrifice(double costPoints, double sharePct, double maxMana, double maxLife, double scale,
                             double health)
    {
        double const want = Share(costPoints, sharePct);
        if (want <= 0 || maxMana <= 0 || maxLife <= 0 || scale <= 0)
            return {};
        double const wanted = want / maxMana * maxLife * scale;
        double const paid = std::min(wanted, std::max(0.0, health - 1.0));
        return {want * (paid / wanted), paid};
    }
} // namespace DC::Combat::WitchDoctor::Passive
