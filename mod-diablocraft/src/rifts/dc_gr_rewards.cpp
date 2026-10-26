/*
 * World of DiabloCraft - Greater Rift Guardian rewards by level.
 *
 * What the Guardian of a Greater Rift pays on top of the Nephalem reward: the legendaries of the
 * level's curve, the gold and XP of the level, and one legendary gem the character does not own.
 * The arithmetic is dc_gr_rewards.h, which the test compiles; this file reads the rifts.csv rows
 * and the character. RewardGuardian hands the result to the loot roller, GreaterRiftXp to the XP.
 * GuardianShards is the Blood Shards either kind of Guardian pays (Kadala part 2).
 */

#include "dc_gr_rewards.h"

#include "dc_rifts_internal.h"
#include "../common/dc_tunables.h"
#include "../items/dc_items.h"

#include <cstdio>

namespace DC::Rifts
{
    namespace
    {
        double Row(char const* name)
        {
            return Tunables::Get("rifts", name);
        }
    } // namespace

    DC::Loot::GreaterReward GuardianReward(Player* member, Rift const& rift)
    {
        Gr::Curve curve;
        curve.start = Row("gr_legendary_start");
        curve.bend = Row("gr_legendary_bend");
        curve.cap = Row("gr_legendary_cap");
        curve.capLevel = static_cast<unsigned>(Row("gr_legendary_cap_level"));
        DC::Loot::GreaterReward reward;
        reward.legendaries = Gr::Legendaries(rift.grRank, curve);
        reward.goldFactor = Gr::GoldFactor(rift.grRank, Row("gr_gold_per_level"));
        reward.gems = DC::Items::UnownedLegendaryGems(member);
        return reward;
    }

    std::uint64_t GuardianShards(Rift const& rift)
    {
        if (rift.mode == "gr")
            return Gr::ShardsFor(Row("blood_shards_gr_base"), Row("blood_shards_gr_per_level"), rift.grRank);
        // Nephalem: one row per tier (kadala.md 4.4 (a)); a tier with no row or no number pays nothing.
        char name[32];
        std::snprintf(name, sizeof name, "blood_shards_nr_tier_%02u", rift.tier);
        return Tunables::Has("rifts", name) ? Gr::ShardsFor(Row(name), 0, 0) : 0;
    }

    double GuardianXpFactor(unsigned level)
    {
        // Levels 2 to gr_xp_table_last_level are a hand-set table, one row each; a blank row is a 0 here,
        // which XpFactor reads as "the level before".
        unsigned const last = static_cast<unsigned>(Row("gr_xp_table_last_level"));
        std::vector<double> table;
        for (unsigned at = 2; at <= last; ++at)
        {
            char name[32];
            std::snprintf(name, sizeof name, "gr_xp_level_%02u", at);
            table.push_back(Tunables::Has("rifts", name) ? Row(name) : 0.0);
        }
        return Gr::XpFactor(level, table, static_cast<unsigned>(Row("gr_xp_mid_last_level")),
                            Row("gr_xp_per_level_mid"), Row("gr_xp_per_level_high"));
    }
} // namespace DC::Rifts
