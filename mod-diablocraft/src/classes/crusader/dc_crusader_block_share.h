#pragma once
// "Deals {damage_pct} weapon damage plus {block_chance_share_pct} of your shield Block Chance as damage": the rule that
// needs no core type, header-only so the harness of the skills that use it (tests/crusader_shield_bash) compiles this
// exact code. The production half is dc_crusader_block_share.cpp.
#include "../../combat/dc_damage_buckets.h"

#include <cstdint>

class Player;

namespace DC::Combat::Crusader::BlockShare
{
    // The weapon-damage percentage of a hit that adds a share of the Block Chance: a share of 300% of a 30% Block
    // Chance is 90 points of weapon damage on top of the skill's own.
    inline double Pct(double damagePct, double sharePct, double blockChancePct)
    {
        return damagePct + sharePct * blockChancePct / 100.0;
    }

    // The same as a multiplier of the hit the engine deals with `damagePct` alone.
    inline double Factor(double damagePct, double sharePct, double blockChancePct)
    {
        return damagePct > 0 ? Pct(damagePct, sharePct, blockChancePct) / damagePct : 1.0;
    }

    // The production half (dc_crusader_block_share.cpp).
    // The hit's own multiplier for a spell that states a share (ComputeHit, beside every class's other multipliers).
    void Multipliers(Player* player, std::uint32_t spellId, DC::Combat::Factors& out);
    // The percentage of a hit this class deals itself, with the share added now: `damagePct` and `sharePct` of the rune
    // that names them. Strikes made inside a Strike scope are not multiplied again.
    double PctNow(Player* player, double damagePct, double sharePct);
    // While one is alive the Crusader's own strikes carry their share in their percentage.
    class OwnStrikes
    {
    public:
        OwnStrikes();
        ~OwnStrikes();
        OwnStrikes(OwnStrikes const&) = delete;
        OwnStrikes& operator=(OwnStrikes const&) = delete;
    };
} // namespace DC::Combat::Crusader::BlockShare
