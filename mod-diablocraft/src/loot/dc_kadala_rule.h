#ifndef DC_KADALA_RULE_H
#define DC_KADALA_RULE_H

#include <array>
#include <cstdint>
#include <string>
#include <vector>

// Kadala's purchase (docs/proposals/kadala.md 3.2 and 4.7): the decisions of the buy hook,
// free of the core so scripts/tests/items/test_kadala_purchase.py compiles this header and drives it with the sheets'
// numbers. The hook (dc_kadala.cpp) gathers the facts, asks here, and does what the answer says.
namespace DC::Kadala
{
    // What the entry stands for: the slot and, when the entry names kinds (Shield, Source...), those base types.
    // dc_kadala_entry, written by generate_kadala.py from kadala_entries.csv.
    struct SlotFilter
    {
        std::string slot;
        std::vector<std::string> types; // empty: any base of the slot

        bool Admits(std::string const& baseSlot, std::string const& baseType) const
        {
            if (baseSlot != slot)
                return false;
            if (types.empty())
                return true;
            for (std::string const& type : types)
                if (type == baseType)
                    return true;
            return false;
        }
    };

    // base_types as the sheet writes them: ';' between kinds, empty for none.
    inline std::vector<std::string> SplitTypes(std::string const& text)
    {
        std::vector<std::string> out;
        std::string token;
        for (char c : text + ";")
        {
            if (c != ';')
            {
                token += c;
                continue;
            }
            if (!token.empty())
                out.push_back(token);
            token.clear();
        }
        return out;
    }

    // 4.7: a flat chance for a legendary or set item, not raised by Magic Find or the tier. roll is uniform in [0, 1).
    inline bool RollsLegendary(double legendaryPct, double roll)
    {
        return roll * 100.0 < legendaryPct;
    }

    // 3.2 step 2: the price is what the server's own ItemExtendedCost row says, and only Blood Shards. A row that
    // also asks for honor, arena points, a rating or any other item is a data fault, not a price.
    struct CostRow
    {
        std::array<std::uint32_t, 5> item{}, count{};
        std::uint32_t honor = 0, arena = 0, arenaRating = 0;
    };
    inline bool ShardPrice(CostRow const& row, std::uint32_t shardEntry, std::uint64_t& price)
    {
        if (row.honor || row.arena || row.arenaRating)
            return false;
        std::uint64_t total = 0;
        for (std::size_t i = 0; i < row.item.size(); ++i)
        {
            if (!row.item[i])
                continue;
            if (row.item[i] != shardEntry)
                return false;
            total += row.count[i];
        }
        price = total;
        return total > 0;
    }

    // What the hook found. Everything the stock path checks that a purchase of ours still needs (3.2 step 1), the
    // price and the ledger (steps 2 and 3), and whether the roll found a base and a bag cell for it.
    struct Facts
    {
        bool alive = false, inReach = false, onList = false, classAllowed = false, priced = false;
        unsigned count = 0;
        std::uint64_t price = 0, held = 0;
        bool rolled = false, bagFree = false;
    };

    enum class Verdict
    {
        Buy,
        Dead,
        BadCount,
        TooFar,
        NotListed,
        WrongClass,
        NoPrice,
        TooFewShards,
        NothingToRoll,
        BagsFull
    };

    // The stock path's own order (Player.cpp:10946 onward), then ours. The first refusal wins, so a refusal before
    // the debit leaves everything as it was.
    inline Verdict Judge(Facts const& f)
    {
        if (!f.alive)
            return Verdict::Dead;
        if (f.count != 1)
            return Verdict::BadCount;
        if (!f.inReach)
            return Verdict::TooFar;
        if (!f.onList)
            return Verdict::NotListed;
        if (!f.classAllowed)
            return Verdict::WrongClass;
        if (!f.priced)
            return Verdict::NoPrice;
        if (f.held < f.price)
            return Verdict::TooFewShards;
        if (!f.rolled)
            return Verdict::NothingToRoll;
        if (!f.bagFree)
            return Verdict::BagsFull;
        return Verdict::Buy;
    }
} // namespace DC::Kadala

#endif
