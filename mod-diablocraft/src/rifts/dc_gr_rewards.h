/*
 * World of DiabloCraft - Greater Rift Guardian rewards by level.
 *
 * The decisions with no core in them: how many legendaries a Guardian of level N drops (curve A), the
 * gold and XP factors of a level, and which legendary gem drops. The numbers are rifts.csv rows, read
 * by dc_gr_rewards.cpp; this file is what the test compiles. Internal to the rifts folder.
 */

#ifndef DC_GR_REWARDS_H
#define DC_GR_REWARDS_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <string>
#include <vector>

namespace DC::Rifts::Gr
{
    // Curve A: the legendaries one Guardian kill pays on average,
    //   start + (cap - start) * ((level - 1) / (capLevel - 1)) ^ bend   below capLevel, cap from there on.
    // start is the general legendary rate times the Guardian's item count. A broken row (a cap level
    // of 1 or less, a start above the cap) never pays above the cap or below nothing.
    struct Curve
    {
        double start = 0, bend = 1, cap = 0;
        unsigned capLevel = 1;
    };

    inline double Legendaries(unsigned level, Curve const& curve)
    {
        if (level >= curve.capLevel || curve.capLevel <= 1)
            return std::max(0.0, curve.cap);
        double const reached =
            std::pow(static_cast<double>(std::max(level, 1u) - 1) / (curve.capLevel - 1), curve.bend);
        double const paid = curve.start + (curve.cap - curve.start) * reached;
        return std::clamp(paid, 0.0, std::max(0.0, curve.cap));
    }

    // The whole number of legendaries of one kill: the integer part, and the fraction is the chance of
    // one more (6.4 is 6, and a 40% chance of a 7th). `roll` is uniform in [0, 1). No guarantee.
    inline unsigned LegendaryCount(double average, double roll)
    {
        if (!(average > 0.0) || !std::isfinite(average))
            return 0;
        double const whole = std::floor(average);
        return static_cast<unsigned>(whole) + (roll < average - whole ? 1u : 0u);
    }

    // Gold rises by a fixed multiple per level above the first (greater_rifts.csv gold_gain_per_rank).
    // A multiple that is no number above nothing is no scaling.
    inline double GoldFactor(unsigned level, double perLevel)
    {
        if (level <= 1 || !(perLevel > 0.0) || !std::isfinite(perLevel))
            return 1.0;
        return std::pow(perLevel, static_cast<double>(level - 1));
    }

    // XP, as a multiple of a level 1 kill's (greater_rifts.csv xp_gain_per_rank): levels 2 to
    // `table.size()` + 1 are hand-picked and unpublished, so the table is hand-set (`table[k]` is level
    // k + 2; a blank, negative or broken row repeats the level before it); then x`perMid` per level up
    // to `midLast`, and x`perHigh` per level above it.
    inline double XpFactor(unsigned level, std::vector<double> const& table, unsigned midLast, double perMid,
                           double perHigh)
    {
        double factor = 1.0;
        unsigned const tableLast = static_cast<unsigned>(table.size()) + 1;
        for (unsigned at = 2; at <= std::min(level, tableLast); ++at)
        {
            double const row = table[at - 2];
            if (row > 0.0 && std::isfinite(row))
                factor = row;
        }
        for (unsigned at = tableLast + 1; at <= level; ++at)
        {
            double const per = at <= midLast ? perMid : perHigh;
            if (per > 0.0 && std::isfinite(per))
                factor *= per;
        }
        return factor;
    }

    // An XP amount times a level factor, floored; a factor that is no number above nothing leaves it.
    inline std::uint64_t ScaleXp(std::uint64_t amount, double factor)
    {
        if (!(factor > 0.0) || !std::isfinite(factor))
            return amount;
        double const scaled = std::floor(static_cast<double>(amount) * factor);
        return scaled >= 1.8446744073709552e19 ? UINT64_MAX : static_cast<std::uint64_t>(scaled);
    }

    // The gem a Guardian drops: one the character does not own yet, picked evenly; none when it owns
    // every one. `unowned` is the gem item entries still missing; `roll` is uniform in [0, 1).
    inline std::uint32_t PickGem(std::vector<std::uint32_t> const& unowned, double roll)
    {
        if (unowned.empty())
            return 0;
        std::size_t const at = static_cast<std::size_t>(std::clamp(roll, 0.0, 0.999999999) * unowned.size());
        return unowned[std::min(at, unowned.size() - 1)];
    }

    // Blood Shards of one Guardian kill: Greater (kadala.md 4.5) is D'3's `base + perLevel * level`, Nephalem a tier's row (perLevel 0)
    // (127 + 3 x 75 = 352). A row that is no number, or a result below nothing, pays nothing.
    inline std::uint64_t ShardsFor(double base, double perLevel, unsigned level)
    {
        double const paid = std::floor(base + perLevel * level);
        return std::isfinite(paid) && paid > 0.0 && paid < 1.8446744073709552e19 ? static_cast<std::uint64_t>(paid) : 0;
    }

    // The chat line of a shard credit (kadala.md 4.3 (a)): what arrived, and what the cap cut.
    // `credited` is the amount the Guardian paid; `lost` the part of it the cap refused.
    inline std::string ShardLine(std::uint64_t credited, std::uint64_t lost)
    {
        auto const shards = [](std::uint64_t count) { return std::to_string(count) + " Blood Shard" + (count == 1 ? "" : "s"); };
        std::uint64_t const received = credited - std::min(lost, credited);
        if (!lost)
            return "You receive " + shards(received) + ".";
        return (received ? "You receive " + shards(received) + ". " : std::string()) + shards(lost) +
               (lost == 1 ? " was" : " were") + std::string(" lost: you cannot hold more.");
    }
} // namespace DC::Rifts::Gr

#endif // DC_GR_REWARDS_H
