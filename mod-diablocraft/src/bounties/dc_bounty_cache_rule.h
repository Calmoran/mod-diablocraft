/*
 * World of DiabloCraft - the Horadric Cache's rules, without the core (docs/research/bounties.md 5.5).
 *
 * A cache's amounts are the Torment XVI values (rifts tunables bounty_cache_*, maxroll) times the scale percent of the
 * tier it was earned on (bounty_cache_scale_pct_tier_NN). dc_bounty_cache.cpp reads the rows and the player, asks here,
 * and does what the answer says; scripts/tests/bounties/test_bounty_cache.py compiles this file as it is.
 */
#ifndef DC_BOUNTY_CACHE_RULE_H
#define DC_BOUNTY_CACHE_RULE_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <functional>
#include <string>

namespace DC::Bounties::Cache
{
    // Constant (account_economy.csv): Death's Breath's ledger identity, never a price.
    constexpr std::uint32_t DeathsBreathEntry = 102000;
    // Constant: D3's difficulty ladder, Normal to Torment XVI (difficulty_tiers.csv rows); the tier rows run 01 to 20.
    constexpr unsigned Tiers = 20;

    // The row of a per-tier tunable: "bounty_cache_scale_pct_tier_05". Empty for a tier off the ladder.
    inline std::string TierRow(char const* prefix, unsigned tier)
    {
        if (tier < 1 || tier > Tiers)
            return "";
        char row[64];
        std::snprintf(row, sizeof(row), "%s_tier_%02u", prefix, tier);
        return row;
    }

    // The Torment XVI amounts, as the rows hold them.
    struct Top
    {
        double gold = 0, shards = 0, reagent = 0, deathsBreath = 0, gemsMin = 0, gemsMax = 0, raresMin = 0,
               raresMax = 0, legendaries = 0;
    };

    // One cache's amounts once its tier's scale is applied.
    struct Amounts
    {
        std::uint64_t gold = 0, shards = 0, reagent = 0, deathsBreath = 0;
        unsigned gemsMin = 0, gemsMax = 0, raresMin = 0, raresMax = 0, legendaries = 0;
    };

    // top x pct / 100, to the nearest whole; a negative, blank or non-finite cell is nothing.
    inline std::uint64_t Scaled(double top, double pct)
    {
        double const value = top * pct / 100.0;
        if (!std::isfinite(value) || value <= 0)
            return 0;
        return static_cast<std::uint64_t>(std::llround(std::min(value, 1e15)));
    }

    // A count, capped so a stray row cannot ask for thousands of items.
    inline unsigned Count(double top, double pct)
    {
        return static_cast<unsigned>(std::min<std::uint64_t>(Scaled(top, pct), 1000));
    }

    inline Amounts Scale(Top const& top, double pct)
    {
        Amounts a;
        a.gold = Scaled(top.gold, pct);
        a.shards = Scaled(top.shards, pct);
        a.reagent = Scaled(top.reagent, pct);
        a.deathsBreath = Scaled(top.deathsBreath, pct);
        // A min and max set the wrong way round are swapped, as the board's draw does.
        a.gemsMin = Count(std::min(top.gemsMin, top.gemsMax), pct);
        a.gemsMax = Count(std::max(top.gemsMin, top.gemsMax), pct);
        a.raresMin = Count(std::min(top.raresMin, top.raresMax), pct);
        a.raresMax = Count(std::max(top.raresMin, top.raresMax), pct);
        a.legendaries = Count(top.legendaries, pct);
        return a;
    }

    // A uniform whole number in [lo, hi]; urand in the server, a fixed sequence in the test.
    using Rng = std::function<std::uint32_t(std::uint32_t lo, std::uint32_t hi)>;

    // How many items one opening rolls. An empty legendary pool rolls none (the sheet says so).
    struct Counts
    {
        unsigned gems = 0, rares = 0, legendaries = 0;
    };
    inline Counts Roll(Amounts const& a, bool poolEmpty, Rng const& rng)
    {
        return {rng(a.gemsMin, a.gemsMax), rng(a.raresMin, a.raresMax), poolEmpty ? 0u : a.legendaries};
    }

    // The cache's own slot is freed first, so its items need one free bag slot fewer than they are. Each gem counts as
    // a slot although gems stack: a refusal that was not needed costs a retry, a store that fails mid-open costs a
    // session reload.
    inline unsigned SlotsNeeded(unsigned items)
    {
        return items > 0 ? items - 1 : 0;
    }

    struct Facts
    {
        bool alive = false, inCombat = false, inTrade = false, ledger = false, earned = false, rows = false;
        unsigned items = 0, freeSlots = 0;
    };

    enum class Verdict
    {
        Open,
        Dead,
        InCombat,
        InTrade,
        NoLedger, // the account ledger is off: gold, shards and materials would have nowhere to go
        NoRecord, // no dc_bounties_cache_item row: not a cache a column delivered
        NoRows,   // the tier's scale or gem grade row is missing
        BagsShort
    };

    // The set cache's refusals in its order (dc_set_cache_rule.h), then ours. The first refusal wins, and every refusal
    // comes before anything is destroyed or staged.
    inline Verdict Judge(Facts const& f)
    {
        if (!f.alive)
            return Verdict::Dead;
        if (f.inCombat)
            return Verdict::InCombat;
        if (f.inTrade)
            return Verdict::InTrade;
        if (!f.ledger)
            return Verdict::NoLedger;
        if (!f.earned)
            return Verdict::NoRecord;
        if (!f.rows)
            return Verdict::NoRows;
        if (f.freeSlots < SlotsNeeded(f.items))
            return Verdict::BagsShort;
        return Verdict::Open;
    }

    // The chat line of a refusal, "" for an open.
    inline std::string Refusal(Verdict verdict, std::string const& name, unsigned items, unsigned freeSlots)
    {
        switch (verdict)
        {
            case Verdict::Dead:
                return "You cannot open a cache while dead.";
            case Verdict::InCombat:
                return "You cannot open a cache in combat.";
            case Verdict::InTrade:
                return "That cache is in a trade.";
            case Verdict::NoLedger:
            case Verdict::NoRecord:
            case Verdict::NoRows:
                return name + " cannot be opened. Report it.";
            case Verdict::BagsShort:
            {
                unsigned const needed = SlotsNeeded(items);
                return name + " needs " + std::to_string(needed) + " free bag slot" + (needed == 1 ? "" : "s") +
                       "; you have " + std::to_string(freeSlots) + ".";
            }
            case Verdict::Open:
                break;
        }
        return "";
    }

    // The delivery's chat lines (bags, else the stash, else lost with a line saying so). The bags
    // need none: the item-received line is the client's own.
    inline std::string StashLine(std::string const& name)
    {
        return "Your bags were full: " + name + " went to your Stash.";
    }
    inline std::string LostLine(std::string const& name)
    {
        return "Your bags and Stash were full: " + name + " was lost.";
    }
} // namespace DC::Bounties::Cache

#endif
